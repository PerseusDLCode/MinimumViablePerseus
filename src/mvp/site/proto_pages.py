"""Compiling corpus TEI documents into the proto-page tree."""

import multiprocessing
from functools import partial
from pathlib import Path

from perseus_cts.chunker import Chunker
from perseus_cts.cts_resolver import auto_chunk_units, available_refsDecl_ids
from perseus_cts.models import Corpus, CTSCatalog

from mvp.site import config
from mvp.site_map import SiteMap


def _scheme_slug(refsDecl_id: str) -> str:
    """Return the subdirectory name for a non-default citeStructure scheme.

    The default scheme (xml:id="CTS") compiles directly into the version
    directory (slug ""); any additional scheme (e.g. "CTS-card") compiles
    into a same-named subdirectory (e.g. "card")."""
    if refsDecl_id == "CTS":
        return ""
    return refsDecl_id.removeprefix("CTS-") or refsDecl_id.lower()


def _compile_proto_page(
    xml_path: Path, proto_dir: Path, catalog: CTSCatalog | None = None
) -> tuple[str, str | None]:
    """Parse, urn/skip-check, and compile one TEI document.

    Runs in a worker process (see generate_proto_pages) — must never raise,
    since an uncaught exception here would abort the whole pool instead of
    just skipping this one document, unlike the previous sequential loop.

    Takes the source XML *path* rather than an already-constructed
    TEIDocument: a TEIDocument holds a parsed lxml ElementTree, which can't
    be pickled through Pool.imap_unordered's task queue, and re-parsing here
    (instead of once in the caller, then again in the worker) avoids paying
    for the parse twice.

    ``catalog`` (built from the same corpora's __cts__.xml files) is passed
    to each Chunker so metadata.json's document.title/about are populated
    from the catalog rather than left at their document-only fallbacks —
    document.about in particular is what lets a commentary's sibling
    editions/translations be found later (see mvp.site.siblings).
    """
    from perseus_cts.models.document import TEIDocument

    site_map = SiteMap(proto_dir)
    try:
        doc = TEIDocument.from_path(xml_path)
        if not doc.metadata.urn:
            return "skipped", None
        if site_map.manifest_path(doc.metadata.urn).exists():
            return "skipped", None
        compilers: list[tuple[str, Chunker]] = []
        for refsDecl_id in available_refsDecl_ids(doc):
            scheme = _scheme_slug(refsDecl_id)
            compilers.append(
                (scheme, Chunker(doc, refsDecl_id=refsDecl_id, catalog=catalog))
            )

        # A document whose default citeStructure nests three or more levels
        # deep (e.g. book/chapter/section) gets an extra scheme for free at
        # the adjacent level (e.g. book/chapter), skipped when a corpus has
        # already hand-declared it under its own refsDecl (see
        # auto_chunk_units) so this never compiles the same scheme twice.
        compiled_schemes = {scheme for scheme, _ in compilers}
        for chunk_unit in auto_chunk_units(doc):
            if chunk_unit in compiled_schemes:
                continue
            compilers.append(
                (chunk_unit, Chunker(doc, chunk_unit=chunk_unit, catalog=catalog))
            )
            compiled_schemes.add(chunk_unit)

        if not compilers:
            # No declared or inferable citeStructure, so there's nothing to
            # compile. Deliberately not writing a manifest here: doing so
            # would make the skip-check above treat this document as
            # permanently handled, silently masking the case where a corpus
            # is later fixed to declare a citeStructure.
            return "no-schema", str(xml_path)

        # A document's refsDecls are compiled independently, and one being
        # misconfigured (e.g. a citeStructure with no reachable n="chunk"
        # level -- see CTSResolver._find_chunk_cs) must not take the whole
        # document down with it: accessing citation_chunks is what
        # actually triggers that resolution, so it's done per-compiler,
        # up front, with failures skipped rather than left to propagate
        # out of the dict comprehension below and abort every other
        # (perfectly fine) scheme for this same document.
        usable_compilers: list[tuple[str, Chunker]] = []
        for scheme, compiler in compilers:
            try:
                compiler.citation_chunks
            except Exception as exc:
                print(f"  SCHEME-FAILED: {xml_path} [{scheme or 'default'}]: {exc}")
                continue
            usable_compilers.append((scheme, compiler))

        if not usable_compilers:
            return "failed", f"{xml_path}: no citeStructure scheme compiled"

        # unit -> scheme slug, shared across every scheme's own TOC so a
        # reader can jump directly to any other *hierarchically nested*
        # paginated level (e.g. chapter <-> section) from the left nav, not
        # just the level currently being read (see CTSResolver.toc). A
        # scheme unrelated to this tree (e.g. tragedy's card scheme) simply
        # never appears while walking any of these trees, so including it
        # here is harmless.
        unit_scheme_map = {
            compiler.cts_resolver.target_unit: scheme
            for scheme, compiler in usable_compilers
        }

        for scheme, compiler in usable_compilers:
            compiler.compile(
                site_map.chunk_dir(doc.metadata.urn, scheme or None),
                unit_scheme_map=unit_scheme_map,
            )

        return "ok", None
    except Exception as exc:
        return "failed", f"{xml_path}: {exc}"


def generate_proto_pages(
    proto_dir: Path,
    corpora: list[Corpus],
    catalog: CTSCatalog | None = None,
) -> None:
    """Generate proto-page XML for all corpus documents.

    A document may declare more than one citeStructure scheme (see
    perseus_cts.cts_resolver.available_refsDecl_ids); each is compiled
    separately (see _scheme_slug for the output layout).

    Skips documents whose index.json already exists in proto_dir so the
    function is safe to call on every startup without re-doing prior work.

    Parsing, the skip check, and compilation are all fanned out across
    BUILD_WORKERS processes (see _compile_proto_page) — only the cheap,
    parse-free directory walk (mirroring Corpus.documents()'s file
    discovery) stays single-threaded here.

    ``catalog``, when given, is threaded down to each Chunker so
    metadata.json's document.title/about are populated from __cts__.xml
    (see _compile_proto_page). It's passed once here as a plain function
    argument to Pool.imap_unordered, which pickles it to each worker.
    """
    work = []
    for corpus in corpora:
        for xml_path in sorted(corpus.root.rglob("*.xml")):
            if xml_path.name == "__cts__.xml":
                continue
            work.append(xml_path)

    generated = skipped = no_schema = failed = 0
    total = len(work)
    ctx = multiprocessing.get_context("fork")
    with ctx.Pool(config.BUILD_WORKERS) as pool:
        results = pool.imap_unordered(
            partial(_compile_proto_page, proto_dir=proto_dir, catalog=catalog), work
        )
        for i, (status, error) in enumerate(results, 1):
            if status == "ok":
                generated += 1
            elif status == "skipped":
                skipped += 1
            elif status == "no-schema":
                no_schema += 1
                print(f"  NO-SCHEMA: {error}")
            else:
                failed += 1
                print(f"  FAILED:    {error}")
            if i % 500 == 0 or i == total:
                print(f"  proto-pages: {i}/{total} processed")

    print(
        f"Proto-pages: {generated} generated, {skipped} skipped, "
        f"{no_schema} no-schema, {failed} failed."
    )

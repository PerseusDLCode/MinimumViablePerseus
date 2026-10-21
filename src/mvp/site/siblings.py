"""Aligning sibling edition/translation chunks to the currently-read passage."""

from dataclasses import dataclass

from perseus_cts.models import CTSCatalog, CTSVersion

from mvp.site import config
from mvp.site.chunks import (
    _chunk_start_line,
    _find_nearest_chunk,
    _load_index_chunks,
    _work_urn_of,
)


@dataclass
class _SiblingPassage:
    """The sibling chunk(s) aligned to the currently-read passage, by
    reference rather than by content.

    The reading page used to inline each sibling's parsed text, which
    copies every sibling chunk into every base chunk it aligns to — a
    sibling chunked by whole book (see Strategy 2 in _build_sibling_data)
    was repeated in full on every line-group page of that book, roughly
    quadratic in a work's chunk count and the bulk of the frozen site's
    size. Instead, each sibling chunk's text is frozen once, on its own
    _text/ fragment page (see get_text_fragment in create_app), and
    reading.html.jinja fetches ``fragment_urls`` in order when the reader
    opens that sibling.

    cts_urn is the *first* aligned piece's — a valid, resolvable passage
    for the sibling's "focus" link and its displayed citation.
    """

    cts_urn: str
    fragment_urls: list[str]


def _reading_view_url(
    corpus: str,
    textgroup: str,
    work: str,
    version: str,
    chunk: str,
    scheme: str | None = None,
) -> str:
    """Return the reading-view path for a chunk, built without url_for.

    Called once per chunk per sibling/prev/next/scheme-link during a full
    site freeze (thousands of chunks x multiple lookups each), so this
    mirrors the route patterns directly instead of paying url_for's
    per-call routing-table lookup at that volume. Keep in sync with the
    reading_view/reading_view_scheme route rules in create_app.
    """
    base_path = f"/urn:cts:{corpus}:{textgroup}.{work}.{version}"
    if scheme:
        base_path += f"/{scheme}"
    return f"{base_path}:{chunk}/"


def _text_fragment_url(
    corpus: str,
    textgroup: str,
    work: str,
    version: str,
    chunk: str,
    scheme: str | None = None,
) -> str:
    """Return the path of a chunk's bare-text fragment page (its rendered
    elements only, no page chrome or siblings). Keep in sync with the
    get_text_fragment/get_text_fragment_scheme route rules in create_app."""
    return (
        _reading_view_url(corpus, textgroup, work, version, chunk, scheme) + "_text/"
    )


def _starts_within_range(
    start: tuple[int, ...],
    current_line: tuple[int, ...],
    current_end: tuple[int, ...],
) -> bool:
    """True when a sibling chunk's start falls within the base chunk's own
    citation range, extended to treat a finer-grained sibling start as
    "within" a single-point, coarser base range too.

    The base chunk's own citation is usually a real range at the same
    depth as any candidate start, so the plain tuple comparison covers
    it. But a base chunk that's itself a leaf at a coarser unit than its
    own citeStructure normally reaches -- e.g. one of Livy's periochae, a
    book-level summary with no chapter/section subdivisions (see
    perseus_cts.cts_resolver's leaf fallback in _collect_cs_elements) --
    has current_line == current_end: a single point with no depth
    information about how far "its own range" extends. Without this
    extra check, a finer-grained sibling (e.g. a fully chaptered edition
    of the same book) can never register as "in range" here (a deeper
    start is never <= a shallower current_end), so a reader on a leaf
    passage would only ever see the sibling's single nearest chapter
    (Strategy 2 in _build_sibling_data) instead of its whole
    corresponding book.
    """
    if current_line <= start <= current_end:
        return True
    return (
        current_line == current_end
        and len(current_line) < len(start)
        and start[: len(current_line)] == current_line
    )


def _corpus_textgroup_work(work_urn: str) -> tuple[str, str, str]:
    """Split a work-level urn (``urn:cts:namespace:textgroup.work``) into its parts.

    Used to locate a sibling's own proto-page directory/URL by its actual
    work, rather than assuming it shares the currently-displayed document's
    textgroup/work — true for ordinary editions/translations of the same
    work, but false for a commentary's siblings, which live under the work
    named by its ``<ti:about>`` urn, not under the commentary's own
    (nonexistent) work family.
    """
    _, _, corpus, workpart = work_urn.split(":", 3)
    textgroup, work = workpart.split(".", 1)
    return corpus, textgroup, work


def _build_sibling_data(
    corpus: str,
    textgroup: str,
    work: str,
    version: str,
    chunk: str,
    current_line: tuple[int, ...],
    current_end: tuple[int, ...],
    catalog: CTSCatalog,
    base_urn: str,
    scheme: str | None = None,
    about_urn: str | None = None,
) -> dict:
    """Build sibling edition/translation chunk data using catalog + citation value.

    For each sibling version, loads its index.json and finds the chunk(s)
    covering the same citation range as the currently-displayed base chunk
    (``current_line``-``current_end``):
      Strategy 1 — every one of the sibling's own chunks whose start falls
        within that range, in citation order (see
        _starts_within_range for how this extends to a coarser, single-point
        base range, e.g. one of Livy's periochae, against a finer-grained
        sibling -- the sibling's whole corresponding book, not just its
        first chapter)
      Strategy 2 — if none fall inside the range (the base chunk is entirely
        contained within one coarser sibling chunk, or granularities are
        otherwise offset), the nearest chunk to the range's start

    Chunk boundaries can differ in granularity between sibling versions (e.g.
    a card-chunked edition against a scene-chunked translation), so without
    this, siblings would show whatever arbitrary span their own chunking
    happens to produce instead of the same passage the reader is looking at
    in the base text. This lookup runs symmetrically for both edition_chunks
    and translation_chunks regardless of which version is currently displayed
    (base_urn), so alignment is consistent in both directions: reading an
    edition aligns sibling translations, and reading a translation aligns
    sibling editions, to the same passage range.

    ``about_urn`` is the currently-displayed version's ``<ti:about>`` urn
    (recorded in metadata.json's ``document.about`` by perseus_cts's
    Chunker), set on commentary versions to name the work/passage they
    comment on. A commentary has no work family of its own to align
    siblings against, so when present this is used instead of ``base_urn``
    to find the work whose editions/translations should be shown alongside
    the commentary.

    Returns dict with keys:
      current_version: CTSVersion | None
      edition_chunks: list[(CTSVersion, _SiblingPassage | None, str | None)]
      translation_chunks: list[(CTSVersion, _SiblingPassage | None, str | None)]
    The third tuple element is the sibling's "focus" URL — its first page
    when no corresponding chunk could be loaded, and None only when the
    sibling has no pages at all — already routed through the sibling's own scheme
    when the chunk was read from a scheme subdirectory — see _focus_url.
    """
    work_urn = _work_urn_of(about_urn) if about_urn else base_urn.rsplit(".", 1)[0]

    def _focus_url(
        sib_corpus: str,
        sib_textgroup: str,
        sib_work: str,
        sib_id: str,
        sib_scheme: str | None,
        sib_chunk: _SiblingPassage,
    ) -> str:
        # The sibling chunk may have been read from a scheme subdirectory
        # (see sib_scheme below), whose index.json chunks passages
        # differently than the sibling's default index. A bare cts_urn
        # href would route through reading_view (no scheme), resolve
        # against the *default* index, and either 404 or land on the
        # wrong-bounded chunk. Route through the same scheme the chunk was
        # actually read under, matching how NavigationItem.html.jinja and
        # _redirect_to_first_chunk build reading-view links.
        passage = sib_chunk.cts_urn.rsplit(":", 1)[-1]
        return _reading_view_url(
            sib_corpus, sib_textgroup, sib_work, sib_id, passage, sib_scheme
        )

    def _lookup(
        sib: CTSVersion,
    ) -> tuple[CTSVersion, _SiblingPassage | None, str | None] | None:
        sib_id = sib.urn.split(":")[3].split(".")[-1]
        if sib_id == version:
            return sib, None, None

        # A sibling found via about_urn belongs to a different work than the
        # currently-displayed document (e.g. a commentary's siblings are the
        # editions/translations of the work it comments on), so its
        # proto-page directory and reading-view URL must be built from its
        # own work urn rather than the outer corpus/textgroup/work — which
        # only happen to match for ordinary same-work siblings.
        sib_corpus, sib_textgroup, sib_work = _corpus_textgroup_work(sib.work_urn)

        # Match the base text's own citeStructure scheme when the sibling
        # offers it too (e.g. base is viewed "by card" — align siblings at
        # the same card granularity, not their default/scene-level chunks,
        # or a coarser sibling chunk would swallow far more than the base
        # chunk's own range). Falls back to the sibling's default scheme
        # when it has no same-named scheme subdirectory.
        sib_dir = config.PROTO_DIR / sib_corpus / sib_textgroup / sib_work / sib_id
        sib_scheme = scheme if scheme and (sib_dir / scheme).is_dir() else None
        data_dir = sib_dir / sib_scheme if sib_scheme else sib_dir

        index_file = data_dir / "index.json"
        sib_chunks = _load_index_chunks(index_file)
        if not sib_chunks:
            return sib, None, None

        # Fallback "focus" target when no corresponding passage can be
        # shown: the sibling's own first page, so the reader can still
        # jump into that version.
        first_page_url = _reading_view_url(
            sib_corpus,
            sib_textgroup,
            sib_work,
            sib_id,
            sib_chunks[0]["cts_urn"].rsplit(":", 1)[-1],
            sib_scheme,
        )

        # A partial version (e.g. a translation covering only a few chapters
        # of a work) shouldn't be shown as a sibling of every chunk in the
        # full text — only of chunks actually within its own citation range.
        # Outside that range there is no meaningful "nearest" passage, so
        # exclude the sibling entirely rather than clamping to an edge chunk.
        starts = [_chunk_start_line(c["cts_urn"]) for c in sib_chunks]
        if current_line < min(starts) or current_line > max(starts):
            return None

        # Strategy 1: every sibling chunk whose start lies within the base
        # chunk's own citation range, so the sibling's content spans exactly
        # the same passage regardless of the sibling's own chunk_unit.
        in_range = [
            c
            for c in sib_chunks
            if _starts_within_range(
                _chunk_start_line(c["cts_urn"]), current_line, current_end
            )
        ]
        entries = in_range
        # Strategy 2: nearest chunk to the same citation value, before or after.
        if not entries:
            nearest = _find_nearest_chunk(sib_chunks, current_line) or sib_chunks[0]
            entries = [nearest] if nearest else []
        if not entries:
            return sib, None, first_page_url

        # Only pieces whose chunk file exists: their _text/ fragment pages
        # are frozen from these same files, so a missing one would 404.
        present = [e for e in entries if (data_dir / e["file"]).exists()]
        if not present:
            return sib, None, first_page_url

        sib_chunk = _SiblingPassage(
            cts_urn=present[0]["cts_urn"],
            fragment_urls=[
                _text_fragment_url(
                    sib_corpus,
                    sib_textgroup,
                    sib_work,
                    sib_id,
                    entry["cts_urn"].rsplit(":", 1)[-1],
                    sib_scheme,
                )
                for entry in present
            ],
        )
        return sib, sib_chunk, _focus_url(
            sib_corpus, sib_textgroup, sib_work, sib_id, sib_scheme, sib_chunk
        )

    return {
        "current_version": catalog.version_for(base_urn),
        "edition_chunks": [
            result
            for sib in catalog.editions_of(work_urn)
            if sib.urn != base_urn and (result := _lookup(sib)) is not None
        ],
        "translation_chunks": [
            result
            for sib in catalog.translations_of(work_urn)
            if sib.urn != base_urn and (result := _lookup(sib)) is not None
        ],
    }

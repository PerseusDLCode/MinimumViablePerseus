#!/usr/bin/env python3
"""Perseus6 static site builder.

Normal build (one or more corpora, unified catalog):
    python src/tools/run_build.py CORPUS_ROOT [CORPUS_ROOT ...] OUTPUT_ROOT

Catalog-only rebuild (no recompilation; reads existing index.json files):
    python src/tools/run_build.py --catalog-only OUTPUT_ROOT

Examples:
    # Single corpus
    python src/tools/run_build.py data/canonical-latinLit/data /tmp/out

    # Both corpora in one pass → unified catalog
    python src/tools/run_build.py \\
        data/canonical-latinLit/data \\
        data/canonical-greekLit/data \\
        /tmp/out

    # Rebuild catalog after a bug fix, no recompile
    python src/tools/run_build.py --catalog-only /tmp/out

Serve the result:
    cd /tmp/out && python -m http.server 8000
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Allow running directly without installing the package
sys.path.insert(0, str(Path(__file__).parent.parent / "python"))

from mvp.compilers import CatalogCompiler
from mvp.corpus import Corpus
from mvp.models import TEIMetadata
from mvp.pipeline import BuildPipeline
from mvp.site_map import SiteMap

_DEFAULT_XSLT_ROOT = Path(__file__).parent.parent / "xslt"


def _resolve_corpus_path(p: Path) -> Path:
    """Auto-detect the data/ subdirectory used by canonical-*Lit repos."""
    data_subdir = p / "data"
    return data_subdir if data_subdir.is_dir() else p


def _rebuild_catalog(output_root: Path) -> None:
    """Rebuild catalog pages from existing index.json manifests.

    Scans output_root recursively for index.json files, reads the author
    and language fields injected by PageCompiler, and rewrites all catalog
    pages.  No corpus or XSLT required.
    """
    site_map = SiteMap(output_root)
    entries: list[TEIMetadata] = []

    for manifest_path in sorted(output_root.rglob("index.json")):
        try:
            data = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        urn = data.get("base_urn", "")
        if not urn:
            continue
        entries.append(TEIMetadata(
            urn=urn,
            title=data.get("title", ""),
            author=data.get("author", ""),
            language=data.get("language", ""),
            text_type="",
            chunk_unit="",
            source_path=manifest_path,
        ))

    if not entries:
        print("No compiled manifests found; nothing to do.")
        return

    catalog_compiler = CatalogCompiler(site_map=site_map)
    languages: dict[str, list[TEIMetadata]] = {}
    for entry in entries:
        languages.setdefault(entry.language, []).append(entry)

    for language, lang_entries in languages.items():
        catalog_compiler.compile(lang_entries, site_map.catalog_path(language))

    catalog_compiler.compile_index(languages, site_map.root / "index.html")
    print(f"Catalog rebuilt: {len(entries)} works across "
          f"{len(languages)} language(s).")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Perseus6 static site builder",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--catalog-only",
        action="store_true",
        help="Rebuild catalog from existing index.json files; skip compilation",
    )
    parser.add_argument(
        "--xslt-root",
        type=Path,
        default=_DEFAULT_XSLT_ROOT,
        help=f"Directory containing XSLT stylesheets (default: {_DEFAULT_XSLT_ROOT})",
    )
    parser.add_argument(
        "--morph-url",
        default="",
        metavar="URL",
        help=(
            "Base URL of the morphological server (e.g. http://localhost:5000). "
            "When set, every word in the output is linked to /morph?form=...&lang=... "
            "on that server.  Omit for a plain static build."
        ),
    )
    parser.add_argument(
        "paths",
        nargs="+",
        type=Path,
        metavar="PATH",
        help=(
            "Normal build: CORPUS_ROOT [CORPUS_ROOT ...] OUTPUT_ROOT. "
            "Catalog-only: OUTPUT_ROOT."
        ),
    )
    args = parser.parse_args()

    if args.catalog_only:
        if len(args.paths) != 1:
            parser.error("--catalog-only takes exactly one argument: OUTPUT_ROOT")
        print(f"Rebuilding catalog in: {args.paths[0]}")
        _rebuild_catalog(args.paths[0])
        return

    if len(args.paths) < 2:
        parser.error("Normal build requires at least CORPUS_ROOT and OUTPUT_ROOT")

    *corpus_roots, output_root = args.paths
    corpus_paths = [_resolve_corpus_path(p) for p in corpus_roots]

    for cp in corpus_paths:
        print(f"Corpus:  {cp}")
    print(f"Output:  {output_root}")
    print(f"XSLT:    {args.xslt_root}")
    print()

    pipeline = BuildPipeline(
        corpora=[Corpus(cp) for cp in corpus_paths],
        site_map=SiteMap(output_root),
        xslt_root=args.xslt_root,
        morph_url=args.morph_url,
    )
    pipeline.run()


if __name__ == "__main__":
    main()

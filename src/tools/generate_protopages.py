#!/usr/bin/env python3
"""generate_protopages.py — Step 1: TEI → proto-page XML.

Runs generate_protopages.xsl via Saxon to produce one proto-page XML
file per chapter plus an index.json manifest.  Output is suitable for
inspection or as input to render_protopages.py (step 2).

Usage:
  python src/tools/generate_protopages.py TEI_FILE PROTO_DIR

  python src/tools/generate_protopages.py \\
      data/tlg0003.tlg001.perseus-grc2.xml /tmp/thucydides-proto

  # Custom XSLT root:
  python src/tools/generate_protopages.py \\
      data/tlg0003.tlg001.perseus-grc2.xml /tmp/thucydides-proto \\
      --xslt-root path/to/xslt/
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "python"))

from mvp.corpus.document import TEIDocument
from mvp.site.compilers import ProtopageCompiler

_DEFAULT_XSLT_ROOT = Path(__file__).parent.parent / "xslt"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Step 1: TEI → proto-page XML (generate_protopages.xsl via Saxon)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("tei_file", type=Path, help="TEI XML input file")
    parser.add_argument("proto_dir", type=Path,
                        help="Directory to write proto-page XML files and index.json")
    parser.add_argument(
        "--xslt-root", type=Path, default=_DEFAULT_XSLT_ROOT, metavar="DIR",
        help=f"XSLT root directory (default: {_DEFAULT_XSLT_ROOT})",
    )
    args = parser.parse_args()

    tei_file: Path = args.tei_file
    proto_dir: Path = args.proto_dir
    xsl_file: Path = args.xslt_root / "html" / "generate_protopages.xsl"

    if not tei_file.exists():
        parser.error(f"TEI file not found: {tei_file}")
    if not xsl_file.exists():
        parser.error(f"Stylesheet not found: {xsl_file}\n"
                     f"Check --xslt-root or run from the project root.")

    print(f"source : {tei_file}")
    print(f"output : {proto_dir}")
    t0 = time.perf_counter()

    doc = TEIDocument.from_path(tei_file)
    ProtopageCompiler(xsl_file=xsl_file).compile(doc, proto_dir)

    elapsed = time.perf_counter() - t0
    n_chunks = sum(1 for _ in proto_dir.glob("chunk_*.xml"))
    print(f"wrote  : {n_chunks} proto-page files + index.json  ({elapsed:.1f}s)")


if __name__ == "__main__":
    main()

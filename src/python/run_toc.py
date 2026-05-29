"""run-toc — generate toc.json from a proto-page output directory.

Usage:
    run-toc PROTO_DIR

PROTO_DIR must contain an index.json produced by generate-protopages (Step 1
of the proto-page pipeline).  toc.json is written alongside index.json.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from mvp.corpus.toc_generator import TOCGenerator


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate toc.json from a proto-page output directory."
    )
    parser.add_argument(
        "proto_dir",
        type=Path,
        help="Directory containing index.json (proto-page output from Step 1).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output path for toc.json.  Defaults to PROTO_DIR/toc.json.",
    )
    args = parser.parse_args()

    if not (args.proto_dir / "index.json").exists():
        print(f"error: {args.proto_dir}/index.json not found", file=sys.stderr)
        sys.exit(1)

    gen = TOCGenerator(args.proto_dir)
    gen.write(args.output)
    out = args.output or args.proto_dir / "toc.json"
    print(f"wrote {out}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""render_protopages.py — Step 2: proto-page XML → HTML.

Reads the proto-page directory produced by generate_protopages.py and
renders each XML file to an HTML reading page via Jinja2.

Usage:
  python src/tools/render_protopages.py PROTO_DIR HTML_DIR

  python src/tools/render_protopages.py \\
      /tmp/thucydides-proto /tmp/thucydides-html

  # Custom Jinja2 template:
  python src/tools/render_protopages.py \\
      /tmp/thucydides-proto /tmp/thucydides-html \\
      --templates path/to/my/templates/ --template my_chunk.html

Serve the result:
  cd /tmp/thucydides-html && python -m http.server 8000
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "python"))

from mvp.site.compilers import ProtopageRenderer


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Step 2: proto-page XML → HTML (Jinja2)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("proto_dir", type=Path,
                        help="Directory containing proto-page XML files and index.json")
    parser.add_argument("html_dir", type=Path,
                        help="Directory to write HTML reading pages")
    parser.add_argument(
        "--templates", type=Path, default=None, metavar="DIR",
        help="Jinja2 template directory (default: built-in templates)",
    )
    parser.add_argument(
        "--template", default=None, metavar="FILE",
        help="Template filename within the template directory (default: chunk.html)",
    )
    args = parser.parse_args()

    proto_dir: Path = args.proto_dir
    html_dir: Path = args.html_dir

    if not (proto_dir / "index.json").exists():
        parser.error(
            f"No index.json found in {proto_dir}.\n"
            f"Run generate_protopages.py first."
        )

    renderer_kwargs = {}
    if args.templates:
        if not args.templates.is_dir():
            parser.error(f"Template directory not found: {args.templates}")
        renderer_kwargs["template_dir"] = args.templates
    if args.template:
        renderer_kwargs["template_name"] = args.template

    print(f"source : {proto_dir}")
    print(f"output : {html_dir}")
    t0 = time.perf_counter()

    ProtopageRenderer(**renderer_kwargs).compile(proto_dir, html_dir)

    elapsed = time.perf_counter() - t0
    n_html = sum(1 for _ in html_dir.glob("chunk_*.html"))
    print(f"wrote  : {n_html} HTML pages  ({elapsed:.1f}s)")


if __name__ == "__main__":
    main()

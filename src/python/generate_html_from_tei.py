#!/usr/bin/env python3
"""
generate_html_from_tei.py — Transform a TEI document to HTML using an XSL driver.

Usage:
  generate-html-from-tei TEI_FILE XSL_FILE --output-dir DIR [--param NAME=VALUE ...]

XSL_FILE should be a driver stylesheet (e.g. src/xslt/html/driver.xsl), not a
chunker directly.  The driver imports the appropriate chunker, owns the page
shell, and declares all enrichment parameters (morph-url, citation-table, etc.).

Runs the XSLT transformation via SaxonC (saxonche) and writes all output
files to the specified output directory, which is created if absent.

The output directory is passed to the stylesheet as both the Saxon base
output URI (governing xsl:result-document output) and the `output-dir`
XSLT parameter.  Additional stylesheet parameters can be supplied with
repeated --param options.

Examples:
  generate-html-from-tei my-argonautica.xml src/xslt/html/driver.xsl \\
      --output-dir /tmp/argo --param chunk-unit=card

  generate-html-from-tei poetics.xml src/xslt/html/driver.xsl \\
      --output-dir /tmp/poetics \\
      --param chunk-unit=chapter \\
      --param chunk-strategy=div

  generate-html-from-tei my-argonautica.xml src/xslt/html/driver.xsl \\
      --output-dir /tmp/argo-morph \\
      --param chunk-unit=card \\
      --param morph-url=http://localhost:5000
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from mvp.compilers import XSLTCompiler


def _parse_params(raw: list[str]) -> dict[str, str]:
    result: dict[str, str] = {}
    for item in raw:
        if "=" not in item:
            raise argparse.ArgumentTypeError(
                f"--param must be in NAME=VALUE form, got: {item!r}"
            )
        name, _, value = item.partition("=")
        result[name.strip()] = value
    return result


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("tei_file", type=Path, metavar="TEI_FILE",
                        help="Path to the TEI XML source document.")
    parser.add_argument("xsl_file", type=Path, metavar="XSL_FILE",
                        help="Path to the XSLT driver stylesheet.")
    parser.add_argument("--output-dir", type=Path, required=True, metavar="DIR",
                        help="Directory for generated HTML files (created if absent).")
    parser.add_argument(
        "--param", dest="params", action="append", default=[], metavar="NAME=VALUE",
        help="Additional XSLT parameter (may be repeated).",
    )
    args = parser.parse_args()

    if not args.tei_file.is_file():
        print(f"ERROR: TEI file not found: {args.tei_file}", file=sys.stderr)
        return 1
    if not args.xsl_file.is_file():
        print(f"ERROR: XSL file not found: {args.xsl_file}", file=sys.stderr)
        return 1

    try:
        extra = _parse_params(args.params)
    except argparse.ArgumentTypeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    params = {"output-dir": str(args.output_dir.resolve()), **extra}
    compiler = XSLTCompiler(args.xsl_file)
    try:
        compiler.compile(args.tei_file, args.output_dir, params)
    except Exception as exc:
        print(f"ERROR: transformation failed: {exc}", file=sys.stderr)
        return 1

    print(f"Output written to {args.output_dir}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())

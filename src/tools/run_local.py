#!/usr/bin/env python3
"""Start a local Perseus development environment.

Launches two servers concurrently:
  1. The morphological analysis server (FastAPI/uvicorn) on --morph-port.
  2. A static HTTP server for the compiled site on --site-port.

The site must already be built with --morph-url pointing at the morph server:

    python src/tools/run_build.py \\
        --morph-url http://localhost:5000 \\
        data/canonical-latinLit/data /tmp/out

    python src/tools/run_local.py /tmp/out

Prerequisites:
    pip install fastapi "uvicorn[standard]"
  (or: pip install -r src/morph-server/requirements.txt)

Press Ctrl+C to stop both servers.
"""
from __future__ import annotations

import argparse
import signal
import subprocess
import sys
import time
from pathlib import Path

_MORPH_SERVER_DIR = Path(__file__).parent.parent / "morph-server"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Start the Perseus local dev environment (morph server + static site)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "output_dir",
        type=Path,
        metavar="OUTPUT_DIR",
        help="Directory containing the compiled static site",
    )
    parser.add_argument(
        "--site-port",
        type=int,
        default=8000,
        metavar="PORT",
        help="Port for the static HTTP server (default: 8000)",
    )
    parser.add_argument(
        "--morph-port",
        type=int,
        default=5000,
        metavar="PORT",
        help="Port for the morphological server (default: 5000)",
    )
    args = parser.parse_args()

    if not args.output_dir.is_dir():
        sys.exit(f"error: output directory does not exist: {args.output_dir}")

    morph_proc = subprocess.Popen(
        [
            sys.executable, "-m", "uvicorn", "main:app",
            "--host", "127.0.0.1",
            "--port", str(args.morph_port),
        ],
        cwd=str(_MORPH_SERVER_DIR),
    )

    site_proc = subprocess.Popen(
        [sys.executable, "-m", "http.server", str(args.site_port)],
        cwd=str(args.output_dir),
    )

    print(f"Static site : http://localhost:{args.site_port}/")
    print(f"Morph API   : http://localhost:{args.morph_port}/")
    print()
    print("Note: the morph server indexes take 30–60 s to load on first start.")
    print("Press Ctrl+C to stop.")

    def _shutdown(signum, frame):
        morph_proc.terminate()
        site_proc.terminate()
        sys.exit(0)

    signal.signal(signal.SIGINT,  _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    morph_proc.wait()
    site_proc.wait()


if __name__ == "__main__":
    main()

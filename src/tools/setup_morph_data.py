#!/usr/bin/env python3
"""Download Morpheus morphology data files required by the morph server.

The two XML files are too large to store in the repository (~380 MB total).
This script fetches them from Tufts Box and writes them to src/morph-server/.

Usage:
    python src/tools/setup_morph_data.py

Re-running is safe: existing files are skipped unless --force is given.

Sources:
    Greek data  — derived from the Perseus Morpheus project
                  https://github.com/PerseusDL/morpheus
    Latin data  — same source
"""
from __future__ import annotations

import argparse
import sys
import urllib.request
from pathlib import Path

_MORPH_DIR = Path(__file__).parent.parent / "morph-server"

_FILES = {
    "greek.morph.xml": "https://tufts.box.com/shared/static/bs8vl2vohxyqlzxppy8ii9o319k5l8xa.xml",
    "latin.morph.xml": "https://tufts.box.com/shared/static/053m59lsapbcq2eleks2nmz1t1xpnhcm.xml",
}


def _download(url: str, dest: Path) -> None:
    print(f"  Downloading {dest.name} ...", flush=True)
    tmp = dest.with_suffix(".tmp")
    try:
        def _progress(block_count, block_size, total_size):
            if total_size > 0:
                pct = min(100, block_count * block_size * 100 // total_size)
                print(f"\r  {pct:3d}%", end="", flush=True)

        urllib.request.urlretrieve(url, tmp, reporthook=_progress)
        print()
        tmp.rename(dest)
        mb = dest.stat().st_size / 1_048_576
        print(f"  Saved {dest.name} ({mb:.0f} MB)")
    except Exception:
        tmp.unlink(missing_ok=True)
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description="Download Morpheus data files")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-download even if the file already exists",
    )
    args = parser.parse_args()

    all_present = True
    for name, url in _FILES.items():
        dest = _MORPH_DIR / name
        if dest.exists() and not args.force:
            print(f"  Already present: {dest.name} — skipping (use --force to re-download)")
        else:
            all_present = False
            try:
                _download(url, dest)
            except Exception as exc:
                sys.exit(f"error: failed to download {name}: {exc}")

    if all_present:
        print("All morphology data files are present.")
    else:
        print("\nDone. Run 'python src/tools/run_local.py <output_dir>' to start the servers.")


if __name__ == "__main__":
    main()

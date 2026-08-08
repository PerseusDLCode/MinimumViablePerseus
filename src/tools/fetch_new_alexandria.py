#!/usr/bin/env python3
"""Fetch New Alexandria Commentaries Markdown from opencommentaries.org.

Pulls the curated, hard-coded set of GitHub repos in
mvp.site.new_alexandria.SOURCES into a local directory tree that
mvp.site.new_alexandria.build_new_alexandria_index reads at
app-construction time (see NEW_ALEXANDRIA_DIR in config.py). This script
is the only place in the build that touches the network for New
Alexandria data — create_app() only ever reads local files.

Usage:
    uv run python src/tools/fetch_new_alexandria.py --out-dir new-alexandria

Always re-fetches (no skip-if-exists): this is ~15 small text files, not
worth an idempotency layer, and the content changes frequently upstream.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

from mvp.site.new_alexandria import SOURCES, _Source

_USER_AGENT = "MinimumViablePerseus-fetch-new-alexandria"


def _get_json(url: str) -> list[dict]:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": _USER_AGENT, "Accept": "application/vnd.github+json"},
    )
    with urllib.request.urlopen(req, timeout=30.0) as resp:
        return json.loads(resp.read())


def _get_text(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    with urllib.request.urlopen(req, timeout=30.0) as resp:
        return resp.read().decode("utf-8")


def _fetch_source(source: _Source, out_dir: Path) -> int:
    listing_url = (
        f"https://api.github.com/repos/{source.repo}/contents/{source.dir_path}"
    )
    entries = _get_json(listing_url)
    repo_name = source.repo.rsplit("/", 1)[-1]
    dest_dir = out_dir / repo_name
    dest_dir.mkdir(parents=True, exist_ok=True)

    count = 0
    for entry in entries:
        if entry.get("type") != "file" or not entry.get("name", "").endswith(".md"):
            continue
        text = _get_text(entry["download_url"])
        (dest_dir / entry["name"]).write_text(text, encoding="utf-8")
        count += 1
    return count


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fetch New Alexandria Commentaries Markdown from opencommentaries.org"
    )
    parser.add_argument(
        "--out-dir",
        required=True,
        type=Path,
        help="Directory to write fetched Markdown into (matches NEW_ALEXANDRIA_DIR)",
    )
    args = parser.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)

    total = 0
    for source in SOURCES:
        try:
            count = _fetch_source(source, args.out_dir)
        except (urllib.error.URLError, urllib.error.HTTPError) as exc:
            print(f"  ERROR fetching {source.repo}: {exc}", file=sys.stderr)
            sys.exit(1)
        print(f"  {source.repo}: {count} files")
        total += count

    print(f"New Alexandria: {total} files fetched into {args.out_dir}")


if __name__ == "__main__":
    main()

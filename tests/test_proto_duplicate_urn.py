# tests/test_proto_duplicate_urn.py
#
# Every document compiles into a directory named for its URN, so two files
# declaring the same URN (grcnewxml had six copies of the Blass Eumenides
# commentary) used to be compiled concurrently into the same directory,
# leaving chunk files with another copy's tail still on the end of them.
# Only one file per URN may be compiled.

from __future__ import annotations

import shutil
from pathlib import Path

from perseus_cts.models import Corpus
from perseus_cts.models.document import TEIDocument

from mvp.site import proto_pages
from mvp.site.proto_pages import (
    _dedupe_by_urn,
    _pick_canonical,
    _scan_urn,
    generate_proto_pages,
)

DATA = Path(__file__).parent / "data"
GOOD = DATA / "tlg0003.tlg001.perseus-grc2.xml"
URN = "urn:cts:greekLit:tlg0003.tlg001.perseus-grc2"


def test_scan_urn_matches_tei_document():
    assert _scan_urn(GOOD) == TEIDocument.from_path(GOOD).metadata.urn == URN


def test_scan_urn_unparseable_is_none(tmp_path):
    bad = tmp_path / "bad.xml"
    bad.write_text("<TEI><teiHeader>", encoding="utf-8")
    assert _scan_urn(bad) is None


def test_pick_canonical_prefers_conventional_name():
    paths = [
        Path("a/tlg0003.tlg001.perseus-grc2.corrected.xml"),
        Path("z/tlg0003.tlg001.perseus-grc2.xml"),
    ]
    assert _pick_canonical(URN, paths) == paths[1]


def test_pick_canonical_falls_back_to_sorted_order():
    paths = [Path("b/copy.xml"), Path("a/copy.xml")]
    assert _pick_canonical(URN, paths) == Path("a/copy.xml")


def test_dedupe_keeps_one_per_urn_and_unscanned_files():
    work = [
        (Path("x/one.xml"), "repo", "one"),
        (Path("x/two.xml"), "repo", "two"),
        (Path("x/other.xml"), "repo", "other"),
        (Path("x/broken.xml"), "repo", "broken"),
    ]
    urns = [URN, URN, "urn:cts:greekLit:tlg0003.tlg002.perseus-grc2", None]
    kept, dropped = _dedupe_by_urn(work, urns)
    assert dropped == 1
    assert [p.name for p, _, _ in kept] == ["one.xml", "other.xml", "broken.xml"]


def test_generate_compiles_duplicate_urn_once(tmp_path, monkeypatch):
    corpus_root = tmp_path / "repo" / "data"
    work_dir = corpus_root / "tlg0003" / "tlg001"
    work_dir.mkdir(parents=True)
    shutil.copy(GOOD, work_dir / GOOD.name)
    (work_dir / "bak").mkdir()
    shutil.copy(GOOD, work_dir / "bak" / "tlg0003.tlg001.perseus-grc2.old.xml")

    compiled: list[Path] = []
    real_compile = proto_pages._compile_proto_page

    def recording_compile(work_item, *args, **kwargs):
        compiled.append(work_item[0])
        return real_compile(work_item, *args, **kwargs)

    # Run the pool inline so the calls are recorded in this process rather
    # than in forked workers.
    monkeypatch.setattr(proto_pages, "_compile_proto_page", recording_compile)
    monkeypatch.setattr(
        proto_pages.multiprocessing, "get_context", lambda _: _InlineContext()
    )

    generate_proto_pages(tmp_path / "proto", [Corpus(corpus_root)])
    assert compiled == [work_dir / GOOD.name]
    assert list((tmp_path / "proto").rglob("index.json"))


class _InlinePool:
    def __init__(self, _workers):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def map(self, func, items):
        return [func(item) for item in items]

    def imap_unordered(self, func, items):
        return (func(item) for item in items)


class _InlineContext:
    Pool = _InlinePool

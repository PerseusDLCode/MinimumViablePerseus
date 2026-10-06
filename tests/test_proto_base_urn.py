# tests/test_proto_base_urn.py
#
# A TEI file whose <body xml:base> isn't a CTS URN (canonical-latinLit had
# six Cicero files with the filename there) must be reported as a failed
# document, not compiled into a version dir whose metadata.json base_urn
# breaks the build.

from __future__ import annotations

from pathlib import Path

from mvp.site.proto_pages import _compile_proto_page, _is_cts_urn

DATA = Path(__file__).parent / "data"
GOOD = DATA / "tlg0003.tlg001.perseus-grc2.xml"


def test_is_cts_urn():
    assert _is_cts_urn("urn:cts:latinLit:phi0474.phi043.perseus-lat2")
    assert _is_cts_urn("urn:cts:latinLit:phi0474.phi043.perseus-lat2:1.1")
    assert not _is_cts_urn("phi0474.phi043.perseus-lat2.xml")
    assert not _is_cts_urn(None)


def test_filename_xml_base_fails_that_document(tmp_path):
    # Like the Cicero files: body/@xml:base is the filename, while a wrapper
    # div's @n still names the work -- so doc.metadata.urn (and the version
    # dir) look right, but the chunks' base URN doesn't.
    urn = "urn:cts:greekLit:tlg0003.tlg001.perseus-grc2"
    body = f'<body n="{urn}" xml:base="{urn}">'
    source = GOOD.read_text(encoding="utf-8")
    assert source.count(body) == 1
    bad = tmp_path / GOOD.name
    bad.write_text(
        source.replace(
            body, f'<body xml:base="{GOOD.name}"><div type="edition" n="{urn}">'
        ).replace("</body>", "</div></body>"),
        encoding="utf-8",
    )
    proto = tmp_path / "proto"
    status, error = _compile_proto_page((bad, "canonical-greekLit", "x"), proto)
    assert status == "failed"
    assert "not a CTS URN" in error
    assert not list(proto.rglob("metadata.json"))


def test_good_document_still_compiles(tmp_path):
    proto = tmp_path / "proto"
    status, _ = _compile_proto_page((GOOD, "canonical-greekLit", "x"), proto)
    assert status == "ok"

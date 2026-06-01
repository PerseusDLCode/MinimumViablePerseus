"""Smoke tests for the kompilers proof-of-concept compiler/transformer."""
from __future__ import annotations

import textwrap
from pathlib import Path

import pytest
from lxml import etree

from mvp.corpus.tei_document import LenientTEIDocument
from mvp.compilers.kompilers import (
    Family1ProseTransformer,
    ProtopageChunk,
    ProtopageCompiler,
    SchemaRegistry,
    Transformer,
    TransformerFactory,
)

TEI_NS = "http://www.tei-c.org/ns/1.0"
BASE = "urn:cts:greekLit:tlg0003.tlg001.perseus-grc2"


def _doc(tmp_path: Path, xml: str) -> LenientTEIDocument:
    p = tmp_path / "test.xml"
    p.write_text(textwrap.dedent(xml), encoding="utf-8")
    return LenientTEIDocument(p)


PROSE_XML = f"""\
    <?xml version="1.0" encoding="UTF-8"?>
    <TEI xmlns="http://www.tei-c.org/ns/1.0">
      <teiHeader>
        <encodingDesc>
          <refsDecl default="true">
            <citeStructure match="/tei:TEI/tei:text/tei:body" use="@xml:base">
              <citeStructure unit="book" delim=":" match="tei:div[@type='book']" use="@n">
                <citeStructure unit="chapter" delim="." match="tei:div[@type='chapter']" use="@n" n="chunk"/>
              </citeStructure>
            </citeStructure>
          </refsDecl>
        </encodingDesc>
      </teiHeader>
      <text>
        <body xml:base="{BASE}">
          <div type="book" n="1">
            <div type="chapter" n="1">
              <p>First <persName key="Thuc">Thucydides</persName>.</p>
              <p>Second <placeName key="Athens">Athens</placeName>.</p>
            </div>
            <div type="chapter" n="2">
              <p>Text with <milestone unit="page" n="5"/> a milestone <note>a note</note> end.</p>
              <p>Gap: <gap/>.</p>
              <p><del>deleted</del> and <add>added</add>.</p>
            </div>
          </div>
        </body>
      </text>
    </TEI>"""


@pytest.fixture
def prose_doc(tmp_path):
    return _doc(tmp_path, PROSE_XML)


@pytest.fixture
def compiler(prose_doc):
    return ProtopageCompiler(prose_doc)


# ---------------------------------------------------------------------------
# Transformer dispatch
# ---------------------------------------------------------------------------


class TestTransformerDispatch:

    def test_default_descend_returns_children(self, prose_doc):
        t = Family1ProseTransformer(prose_doc)
        # A <div> with two <p> children — default handler descends
        div = etree.fromstring(
            f'<div xmlns="{TEI_NS}"><p>A</p><p>B</p></div>'
        )
        result = t.apply(div)
        assert len(result) == 2
        assert all(el.tag == "p" for el in result)

    def test_p_maps_to_p(self, prose_doc):
        t = Family1ProseTransformer(prose_doc)
        p = etree.fromstring(f'<p xmlns="{TEI_NS}">hello</p>')
        result = t.apply(p)
        assert len(result) == 1
        assert result[0].tag == "p"
        assert result[0].text == "hello"

    def test_persName_maps_to_person(self, prose_doc):
        t = Family1ProseTransformer(prose_doc)
        el = etree.fromstring(f'<persName xmlns="{TEI_NS}" key="X">Name</persName>')
        result = t.apply(el)
        assert result[0].tag == "person"
        assert result[0].get("key") == "X"

    def test_placeName_maps_to_place(self, prose_doc):
        t = Family1ProseTransformer(prose_doc)
        el = etree.fromstring(f'<placeName xmlns="{TEI_NS}" key="Y">City</placeName>')
        result = t.apply(el)
        assert result[0].tag == "place"
        assert result[0].get("key") == "Y"

    def test_milestone_suppressed(self, prose_doc):
        t = Family1ProseTransformer(prose_doc)
        ms = etree.fromstring(f'<milestone xmlns="{TEI_NS}" unit="page" n="1"/>')
        assert t.apply(ms) == []

    def test_note_suppressed(self, prose_doc):
        t = Family1ProseTransformer(prose_doc)
        note = etree.fromstring(f'<note xmlns="{TEI_NS}">footnote</note>')
        assert t.apply(note) == []

    def test_gap_maps_to_empty_gap(self, prose_doc):
        t = Family1ProseTransformer(prose_doc)
        gap = etree.fromstring(f'<gap xmlns="{TEI_NS}"/>')
        result = t.apply(gap)
        assert result[0].tag == "gap"
        assert list(result[0]) == []

    def test_del_and_add(self, prose_doc):
        t = Family1ProseTransformer(prose_doc)
        for tag in ("del", "add"):
            el = etree.fromstring(f'<{tag} xmlns="{TEI_NS}">text</{tag}>')
            result = t.apply(el)
            assert result[0].tag == tag

    def test_q_and_quote_map_to_q(self, prose_doc):
        t = Family1ProseTransformer(prose_doc)
        for tei_tag in ("q", "quote"):
            el = etree.fromstring(f'<{tei_tag} xmlns="{TEI_NS}">text</{tei_tag}>')
            result = t.apply(el)
            assert result[0].tag == "q"

    def test_subclass_can_override_handler(self, prose_doc):
        class MyTransformer(Family1ProseTransformer):
            def __init__(self, doc):
                super().__init__(doc)
                self.register("p", lambda _t, _el: [etree.Element("para")])

        t = MyTransformer(prose_doc)
        p = etree.fromstring(f'<p xmlns="{TEI_NS}">text</p>')
        result = t.apply(p)
        assert result[0].tag == "para"


# ---------------------------------------------------------------------------
# ProtopageCompiler
# ---------------------------------------------------------------------------


class TestProtopageCompiler:

    def test_chunks_count(self, compiler):
        assert len(compiler.chunks) == 2   # two chapters

    def test_compiled_chunks_are_protopage_chunks(self, compiler):
        assert all(isinstance(c, ProtopageChunk) for c in compiler.compiled_chunks)

    def test_chunk_root_tag(self, compiler):
        for chunk in compiler.compiled_chunks:
            assert chunk.content.tag == "protopage"

    def test_chunk_cts_urn_attr(self, compiler):
        urns = [c.content.get("cts-urn") for c in compiler.compiled_chunks]
        assert urns[0] == f"{BASE}:1.1"
        assert urns[1] == f"{BASE}:1.2"

    def test_prev_next_attrs(self, compiler):
        chunks = compiler.compiled_chunks
        assert chunks[0].content.get("prev-urn") is None
        assert chunks[0].content.get("next-urn") == f"{BASE}:1.2"
        assert chunks[1].content.get("prev-urn") == f"{BASE}:1.1"
        assert chunks[1].content.get("next-urn") is None

    def test_content_element_present(self, compiler):
        for chunk in compiler.compiled_chunks:
            content = chunk.content.find("content")
            assert content is not None

    def test_persName_transformed_in_output(self, compiler):
        chunk1 = compiler.compiled_chunks[0]
        content_xml = etree.tostring(chunk1.content).decode()
        assert "<person" in content_xml
        assert "Thucydides" in content_xml

    def test_milestone_absent_from_output(self, compiler):
        chunk2 = compiler.compiled_chunks[1]
        content_xml = etree.tostring(chunk2.content).decode()
        assert "<milestone" not in content_xml

    def test_note_absent_from_output(self, compiler):
        chunk2 = compiler.compiled_chunks[1]
        content_xml = etree.tostring(chunk2.content).decode()
        assert "<note" not in content_xml

    def test_meta_element_present(self, compiler):
        chunk = compiler.compiled_chunks[0]
        meta = chunk.content.find("meta")
        assert meta is not None

    def test_meta_contains_base_urn(self, compiler):
        meta = compiler.compiled_chunks[0].content.find("meta")
        assert meta.findtext("base-urn") == BASE

    def test_meta_contains_ctsurn(self, compiler):
        meta = compiler.compiled_chunks[0].content.find("meta")
        assert meta.findtext("ctsurn") == f"{BASE}:1.1"

    def test_meta_contains_pub_info(self, compiler):
        meta = compiler.compiled_chunks[0].content.find("meta")
        assert meta.find("pubInfo") is not None


class TestProtopageCompilerFileIO:

    def test_compile_creates_xml_files(self, compiler, tmp_path):
        compiler.compile(compiler.tei_doc, tmp_path)
        files = sorted(tmp_path.glob("protopage_*.xml"))
        assert len(files) == 2

    def test_compile_creates_index_json(self, compiler, tmp_path):
        compiler.compile(compiler.tei_doc, tmp_path)
        index_path = tmp_path / "index.json"
        assert index_path.exists()

    def test_index_json_lists_both_chunks(self, compiler, tmp_path):
        import json
        compiler.compile(compiler.tei_doc, tmp_path)
        index = json.loads((tmp_path / "index.json").read_text())
        assert len(index["chunks"]) == 2

    def test_index_json_chunk_urns(self, compiler, tmp_path):
        import json
        compiler.compile(compiler.tei_doc, tmp_path)
        index = json.loads((tmp_path / "index.json").read_text())
        urns = [e["cts_urn"] for e in index["chunks"]]
        assert urns[0] == f"{BASE}:1.1"
        assert urns[1] == f"{BASE}:1.2"

    def test_xml_file_is_parseable(self, compiler, tmp_path):
        compiler.compile(compiler.tei_doc, tmp_path)
        for f in tmp_path.glob("protopage_*.xml"):
            root = etree.parse(f).getroot()
            assert root.tag == "protopage"
            assert root.find("meta") is not None
            assert root.find("content") is not None

    def test_protopage_filenames_use_passage(self, compiler, tmp_path):
        compiler.compile(compiler.tei_doc, tmp_path)
        names = {f.name for f in tmp_path.glob("protopage_*.xml")}
        assert "protopage_1.1.xml" in names
        assert "protopage_1.2.xml" in names

    def test_output_dir_created_if_absent(self, compiler, tmp_path):
        out = tmp_path / "new" / "subdir"
        compiler.compile(compiler.tei_doc, out)
        assert out.is_dir()
        assert any(out.glob("protopage_*.xml"))

    def test_compile_creates_toc_json(self, compiler, tmp_path):
        compiler.compile(compiler.tei_doc, tmp_path)
        assert (tmp_path / "toc.json").exists()

    def test_toc_json_top_level_entries(self, compiler, tmp_path):
        import json
        compiler.compile(compiler.tei_doc, tmp_path)
        toc = json.loads((tmp_path / "toc.json").read_text())
        # PROSE_XML has one book with two chapters
        assert len(toc) == 1
        assert toc[0]["subtype"] == "book"
        assert toc[0]["label"] == "Book 1"
        assert len(toc[0]["subpassages"]) == 2

    def test_toc_json_chapter_entries(self, compiler, tmp_path):
        import json
        compiler.compile(compiler.tei_doc, tmp_path)
        toc = json.loads((tmp_path / "toc.json").read_text())
        chapters = toc[0]["subpassages"]
        assert chapters[0]["urn"].endswith(":1.1")
        assert chapters[0]["label"] == "Chapter 1"
        assert chapters[1]["urn"].endswith(":1.2")

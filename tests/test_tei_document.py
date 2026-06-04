# tests/test_tei_document.py
#
# Tests for TEIDocument metadata extraction.
#
# Three layers:
#   1. Unit tests against minimal synthetic XML fixtures
#   2. Integration tests against known corpus files in tests/data/
#   3. Invariant assertions (to be extended into a corpus smoke test)

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest
from mvp.models.document import TEIDocument
from mvp.models import TEIMetadata

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

DATA_DIR = Path(__file__).parent / "data"

def make_tei(body: str, header_extras: str = "",
             text_lang: str = "") -> str:
    """Return a minimal TEI document as a string."""
    lang_attr = f' xml:lang="{text_lang}"' if text_lang else ""
    return textwrap.dedent(f"""\
        <?xml version="1.0" encoding="UTF-8"?>
        <TEI xmlns="http://www.tei-c.org/ns/1.0">
          <teiHeader>
            <fileDesc>
              <titleStmt>
                <title>Test Title</title>
                <author>Test Author</author>
              </titleStmt>
              <publicationStmt><p>Test</p></publicationStmt>
              <sourceDesc><p>Test</p></sourceDesc>
            </fileDesc>
            {header_extras}
          </teiHeader>
          <text{lang_attr}>
            <body>
              {body}
            </body>
          </text>
        </TEI>
    """)


def write_tei(tmp_path: Path, xml: str) -> Path:
    """Write xml string to a temp file and return its path."""
    p = tmp_path / "test.xml"
    p.write_text(xml, encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# Layer 1: Unit tests against synthetic fixtures
# ---------------------------------------------------------------------------

class TestTEIDocumentLoading:

    def test_loads_valid_file(self, tmp_path):
        path = write_tei(tmp_path, make_tei("<p>Hello</p>"))
        doc = TEIDocument.from_path(path)
        assert doc.path == path

    def test_raises_on_missing_file(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            TEIDocument.from_path(tmp_path / "nonexistent.xml")

    def test_does_not_raise_on_malformed_xml(self, tmp_path):
        # The lenient parser recovers from malformed XML rather than raising.
        # Downstream stages (CTSResolver) raise ConfigurationError if the
        # document structure is unusable.
        p = tmp_path / "bad.xml"
        p.write_text("<unclosed>", encoding="utf-8")
        doc = TEIDocument.from_path(p)
        assert doc is not None

    def test_metadata_is_tei_metadata_instance(self, tmp_path):
        path = write_tei(tmp_path, make_tei("<p>Hello</p>"))
        doc = TEIDocument.from_path(path)
        assert isinstance(doc.metadata, TEIMetadata)


class TestURNExtraction:

    def test_extracts_urn_from_edition_div(self, tmp_path):
        body = """
            <div type="edition" n="urn:cts:latinLit:phi1017.phi007.perseus-lat2">
              <p>text</p>
            </div>
        """
        path = write_tei(tmp_path, make_tei(body))
        doc = TEIDocument.from_path(path)
        assert doc.metadata.urn == "urn:cts:latinLit:phi1017.phi007.perseus-lat2"

    def test_extracts_urn_from_translation_div(self, tmp_path):
        """Translation files use type='translation', not type='edition'."""
        body = """
            <div type="translation" n="urn:cts:latinLit:phi0119.phi001.perseus-eng2">
              <p>text</p>
            </div>
        """
        path = write_tei(tmp_path, make_tei(body))
        doc = TEIDocument.from_path(path)
        assert doc.metadata.urn == "urn:cts:latinLit:phi0119.phi001.perseus-eng2"

    def test_does_not_return_cts_sentinel_from_refs_decl(self, tmp_path):
        """refsDecl[@n='CTS'] must not produce the string 'CTS' as a URN."""
        xml = textwrap.dedent("""\
            <?xml version="1.0" encoding="UTF-8"?>
            <TEI xmlns="http://www.tei-c.org/ns/1.0">
              <teiHeader>
                <fileDesc>
                  <titleStmt>
                    <title>Test</title><author>Author</author>
                  </titleStmt>
                  <publicationStmt><p>Test</p></publicationStmt>
                  <sourceDesc><p>Test</p></sourceDesc>
                </fileDesc>
                <encodingDesc>
                  <refsDecl n="CTS">
                    <cRefPattern n="line" matchPattern="(\\w+)"
                      replacementPattern="#xpath(//l[@n='$1'])"/>
                  </refsDecl>
                </encodingDesc>
              </teiHeader>
              <text><body><p>text</p></body></text>
            </TEI>
        """)
        path = write_tei(tmp_path, xml)
        doc = TEIDocument.from_path(path)
        assert doc.metadata.urn != "CTS"

    def test_empty_urn_when_no_cts_div(self, tmp_path):
        path = write_tei(tmp_path, make_tei("<p>text</p>"))
        doc = TEIDocument.from_path(path)
        assert doc.metadata.urn == ""


class TestTitleExtraction:

    def test_extracts_title(self, tmp_path):
        path = write_tei(tmp_path, make_tei("<p>text</p>"))
        doc = TEIDocument.from_path(path)
        assert doc.metadata.title == "Test Title"

    def test_extracts_title_with_xml_lang(self, tmp_path):
        xml = textwrap.dedent("""\
            <?xml version="1.0" encoding="UTF-8"?>
            <TEI xmlns="http://www.tei-c.org/ns/1.0">
              <teiHeader>
                <fileDesc>
                  <titleStmt>
                    <title xml:lang="lat">Agamemnon</title>
                    <author>Seneca</author>
                  </titleStmt>
                  <publicationStmt><p>Test</p></publicationStmt>
                  <sourceDesc><p>Test</p></sourceDesc>
                </fileDesc>
              </teiHeader>
              <text><body><p>text</p></body></text>
            </TEI>
        """)
        path = write_tei(tmp_path, xml)
        doc = TEIDocument.from_path(path)
        assert doc.metadata.title == "Agamemnon"


class TestAuthorExtraction:

    def test_extracts_author(self, tmp_path):
        path = write_tei(tmp_path, make_tei("<p>text</p>"))
        doc = TEIDocument.from_path(path)
        assert doc.metadata.author == "Test Author"

    def test_empty_author_when_element_is_empty(self, tmp_path):
        xml = textwrap.dedent("""\
            <?xml version="1.0" encoding="UTF-8"?>
            <TEI xmlns="http://www.tei-c.org/ns/1.0">
              <teiHeader>
                <fileDesc>
                  <titleStmt>
                    <title>Some Title</title>
                    <author xml:lang="lat"></author>
                  </titleStmt>
                  <publicationStmt><p>Test</p></publicationStmt>
                  <sourceDesc><p>Test</p></sourceDesc>
                </fileDesc>
              </teiHeader>
              <text><body><p>text</p></body></text>
            </TEI>
        """)
        path = write_tei(tmp_path, xml)
        doc = TEIDocument.from_path(path)
        assert doc.metadata.author == ""


class TestLanguageExtraction:

    def test_extracts_language_from_text_element(self, tmp_path):
        path = write_tei(tmp_path, make_tei("<p>text</p>", text_lang="grc"))
        doc = TEIDocument.from_path(path)
        assert doc.metadata.language == "grc"

    def test_extracts_latin(self, tmp_path):
        path = write_tei(tmp_path, make_tei("<p>text</p>", text_lang="lat"))
        doc = TEIDocument.from_path(path)
        assert doc.metadata.language == "lat"

    def test_falls_back_to_lang_usage(self, tmp_path):
        """When text/@xml:lang is absent, fall back to langUsage."""
        header_extras = """
            <profileDesc>
              <langUsage>
                <language ident="lat">Latin</language>
              </langUsage>
            </profileDesc>
        """
        path = write_tei(tmp_path, make_tei("<p>text</p>",
                                             header_extras=header_extras))
        doc = TEIDocument.from_path(path)
        assert doc.metadata.language == "lat"

    def test_empty_language_when_absent(self, tmp_path):
        """Documents with no language declaration return empty string."""
        path = write_tei(tmp_path, make_tei("<p>text</p>"))
        doc = TEIDocument.from_path(path)
        assert doc.metadata.language == ""


class TestTextTypeExtraction:

    def test_drama_when_sp_present(self, tmp_path):
        body = "<sp><speaker>Actor</speaker><p>line</p></sp>"
        path = write_tei(tmp_path, make_tei(body))
        doc = TEIDocument.from_path(path)
        assert doc.metadata.text_type == "drama"

    def test_verse_when_l_present_but_no_sp(self, tmp_path):
        body = "<lg><l>A line of verse</l></lg>"
        path = write_tei(tmp_path, make_tei(body))
        doc = TEIDocument.from_path(path)
        assert doc.metadata.text_type == "verse"

    def test_prose_when_only_p(self, tmp_path):
        body = "<p>A paragraph of prose.</p>"
        path = write_tei(tmp_path, make_tei(body))
        doc = TEIDocument.from_path(path)
        assert doc.metadata.text_type == "prose"

    def test_drama_takes_precedence_over_verse(self, tmp_path):
        """Drama texts contain both <sp> and <l>; drama should win."""
        body = "<sp><speaker>Actor</speaker><l>A line</l></sp>"
        path = write_tei(tmp_path, make_tei(body))
        doc = TEIDocument.from_path(path)
        assert doc.metadata.text_type == "drama"



# ---------------------------------------------------------------------------
# Layer 2: Integration tests against known corpus files
# ---------------------------------------------------------------------------

class TestSenecaAgamemnon:
    """phi1017.phi007.perseus-lat2.xml — Latin drama, card milestones."""

    @pytest.fixture(scope="class")
    def doc(self):
        return TEIDocument.from_path(
            DATA_DIR / "phi1017.phi007.perseus-lat2.xml"
        )

    def test_urn(self, doc):
        assert doc.metadata.urn == "urn:cts:latinLit:phi1017.phi007.perseus-lat2"

    def test_title(self, doc):
        assert doc.metadata.title == "Agamemnon"

    def test_author(self, doc):
        assert "Seneca" in doc.metadata.author

    def test_language(self, doc):
        # Known issue: this file has no xml:lang on <text>.
        # Permissive assertion documents current behaviour.
        assert doc.metadata.language in ("lat", "")

    def test_text_type(self, doc):
        assert doc.metadata.text_type == "drama"


class TestSophoclesTrachiniae:
    """tlg0011.tlg001.perseus-grc2.xml — Greek drama, card milestones."""

    @pytest.fixture(scope="class")
    def doc(self):
        return TEIDocument.from_path(
            DATA_DIR / "tlg0011.tlg001.perseus-grc2.xml"
        )

    def test_urn(self, doc):
        assert doc.metadata.urn == "urn:cts:greekLit:tlg0011.tlg001.perseus-grc2"

    def test_title(self, doc):
        assert doc.metadata.title == "Τραχίνιαι"

    def test_author(self, doc):
        assert doc.metadata.author == "Sophocles"

    def test_language(self, doc):
        assert doc.metadata.language == "grc"

    def test_text_type(self, doc):
        assert doc.metadata.text_type == "drama"


class TestGalenDeVenaeSectione:
    """tlg0057.tlg069.1st1K-grc1.xml — Greek prose, ed2page milestones,
    empty author element."""

    @pytest.fixture(scope="class")
    def doc(self):
        return TEIDocument.from_path(
            DATA_DIR / "tlg0057.tlg069.1st1K-grc1.xml"
        )

    def test_urn(self, doc):
        assert doc.metadata.urn == "urn:cts:greekLit:tlg0057.tlg069.1st1K-grc1"

    def test_author_is_empty_string(self, doc):
        """Galen file has an empty <author> element; should not crash."""
        assert doc.metadata.author == ""

    def test_language(self, doc):
        # Known issue: no xml:lang on <text> in this file either.
        assert doc.metadata.language in ("grc", "")

    def test_text_type(self, doc):
        assert doc.metadata.text_type == "prose"


# ---------------------------------------------------------------------------
# Layer 3: Invariants (smoke assertions on known corpus files)
# ---------------------------------------------------------------------------

class TestCorpusFileInvariants:
    """Assert basic invariants hold for all files in tests/data/.

    These tests are deliberately lenient — they check that extraction
    does not crash and that returned values are of the right type.
    Stricter assertions belong in the per-file integration tests above.
    """

    @pytest.fixture(params=list(DATA_DIR.glob("*.xml")),
                    ids=lambda p: p.name)
    def doc(self, request):
        return TEIDocument.from_path(request.param)

    def test_metadata_fields_are_strings(self, doc):
        m = doc.metadata
        assert isinstance(m.urn, str)
        assert isinstance(m.title, str)
        assert isinstance(m.author, str)
        assert isinstance(m.language, str)
        assert isinstance(m.text_type, str)

    def test_text_type_is_known_value(self, doc):
        assert doc.metadata.text_type in ("prose", "verse", "drama")

    def test_source_path_matches(self, doc):
        assert doc.metadata.source_path == doc.path


# ---------------------------------------------------------------------------
# DTD parse robustness
# ---------------------------------------------------------------------------

class TestDTDDocument:
    """Documents with DOCTYPE declarations (external SYSTEM identifiers)
    must parse without raising, even when the referenced DTD file does
    not exist on disk."""

    DTD_FIXTURE = DATA_DIR / "dtd_entity_test.xml"

    def test_loads_without_raising(self):
        doc = TEIDocument.from_path(self.DTD_FIXTURE)
        assert doc is not None

    def test_metadata_fields_are_strings(self):
        doc = TEIDocument.from_path(self.DTD_FIXTURE)
        m = doc.metadata
        assert isinstance(m.urn, str)
        assert isinstance(m.title, str)
        assert isinstance(m.author, str)
        assert isinstance(m.language, str)
        assert isinstance(m.text_type, str)

    def test_extracts_expected_metadata(self):
        doc = TEIDocument.from_path(self.DTD_FIXTURE)
        assert doc.metadata.title == "Epistulae ad Atticum"
        assert doc.metadata.author == "Cicero"
        assert doc.metadata.language == "lat"
        assert doc.metadata.urn == "urn:cts:latinLit:phi0474.phi057.perseus-lat2"


# ---------------------------------------------------------------------------
# LenientTEIDocument alias
# ---------------------------------------------------------------------------

class TestLenientTEIDocumentAlias:
    """LenientTEIDocument is a backward-compatible alias for TEIDocument."""

    def test_alias_is_same_class(self):
        from mvp.models.document import LenientTEIDocument
        assert LenientTEIDocument is TEIDocument

    def test_alias_constructs_tei_document(self, tmp_path):
        from mvp.models.document import LenientTEIDocument
        path = write_tei(tmp_path, make_tei("<p>text</p>"))
        doc = LenientTEIDocument(path)
        assert isinstance(doc, TEIDocument)
        assert doc.root is not None

    def test_root_property_exposed(self, tmp_path):
        path = write_tei(tmp_path, make_tei("<p>text</p>"))
        doc = TEIDocument.from_path(path)
        assert doc.root is not None

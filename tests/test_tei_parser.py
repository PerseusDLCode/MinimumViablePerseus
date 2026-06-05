"""Tests for TEIParser in mvp.site.tei_parser."""
from __future__ import annotations

from lxml import etree

from mvp.site.tei_parser import TEIParser


BASE_URN = "urn:cts:greekLit:tlg0001.tlg001.perseus-grc2"


def _parse(xml: str) -> TEIParser:
    root = etree.fromstring(xml)
    return TEIParser(root, BASE_URN, "div")


def _text_runs(elements: list[dict]) -> list[dict]:
    """Recursively collect all text_run nodes from an element list."""
    runs = []
    for el in elements:
        if el["tagname"] == "text_run":
            runs.append(el)
        runs.extend(_text_runs(el.get("children", [])))
    return runs


class TestOffsetTracking:

    def test_single_run_starts_at_zero(self):
        parser = _parse("<p>hello</p>")
        run = _text_runs(parser.elements)[0]
        assert run["start"] == 0

    def test_single_run_end_equals_content_length(self):
        parser = _parse("<p>hello</p>")
        run = _text_runs(parser.elements)[0]
        assert run["end"] == len("hello")

    def test_span_length_equals_raw_content_length(self):
        # end - start reflects the unstripped SAX content, not text_run["content"]
        parser = _parse("<p>  word  </p>")
        run = _text_runs(parser.elements)[0]
        assert run["end"] - run["start"] == len("  word  ")

    def test_slice_recovers_content_for_unpadded_text(self):
        # primary_text[start:end] == content when content has no leading/trailing whitespace
        parser = _parse("<p>ἄνδρα μοι ἔννεπε</p>")
        run = _text_runs(parser.elements)[0]
        assert parser.primary_text[run["start"]:run["end"]] == run["content"]

    def test_sequential_runs_are_non_overlapping(self):
        parser = _parse("<div><p>first </p><p>second</p></div>")
        runs = _text_runs(parser.elements)
        assert len(runs) == 2
        assert runs[0]["end"] <= runs[1]["start"]

    def test_contiguous_runs_when_no_injection_needed(self):
        # "first " ends with whitespace — no space injected; second run abuts first
        parser = _parse("<div><p>first </p><p>second</p></div>")
        runs = _text_runs(parser.elements)
        assert runs[1]["start"] == runs[0]["end"]


class TestSpaceInjection:

    def test_space_injected_at_whitespace_free_boundary(self):
        # <l>word<unclear>more</unclear></l> — adjacent text nodes with no whitespace
        parser = _parse("<l>word<unclear>more</unclear></l>")
        assert parser.primary_text == "word more"

    def test_injected_space_creates_gap_in_offsets(self):
        parser = _parse("<l>word<unclear>more</unclear></l>")
        runs = _text_runs(parser.elements)
        assert runs[0]["start"] == 0
        assert runs[0]["end"] == 4
        assert runs[1]["start"] == 5   # injected space occupies index 4
        assert runs[1]["end"] == 9

    def test_multiple_adjacent_elements_each_get_a_space(self):
        parser = _parse("<l>ἄνδρα<unclear>μοι</unclear>ἔννεπε</l>")
        assert parser.primary_text == "ἄνδρα μοι ἔννεπε"

    def test_no_injection_when_second_content_starts_with_whitespace(self):
        parser = _parse("<div><p>word</p><p> more</p></div>")
        runs = _text_runs(parser.elements)
        assert runs[1]["start"] == runs[0]["end"]

    def test_no_injection_when_first_content_ends_with_whitespace(self):
        parser = _parse("<div><p>word </p><p>more</p></div>")
        runs = _text_runs(parser.elements)
        assert runs[1]["start"] == runs[0]["end"]

    def test_no_injection_before_punctuation(self):
        # Tail punctuation after an inline element must not get a leading space
        parser = _parse("<p><placeName>Sicily</placeName>.</p>")
        assert parser.primary_text == "Sicily."

    def test_single_text_node_unchanged(self):
        parser = _parse("<p>simple text</p>")
        assert parser.primary_text == "simple text"


class TestParatextExclusion:

    def test_note_content_excluded_from_primary_text(self):
        parser = _parse("<div><p>visible</p><note>hidden</note></div>")
        assert "hidden" not in parser.primary_text
        assert "visible" in parser.primary_text

    def test_paratext_text_run_has_no_start(self):
        parser = _parse("<div><note>a note</note></div>")
        run = _text_runs(parser.elements)[0]
        assert "start" not in run

    def test_paratext_text_run_has_no_end(self):
        parser = _parse("<div><note>a note</note></div>")
        run = _text_runs(parser.elements)[0]
        assert "end" not in run

    def test_primary_text_empty_when_all_content_is_paratext(self):
        parser = _parse("<div><note>all hidden</note></div>")
        assert parser.primary_text == ""

    def test_speaker_name_excluded_from_primary_text(self):
        parser = _parse("<sp><speaker>Chorus</speaker><p>spoken line</p></sp>")
        assert "Chorus" not in parser.primary_text

    def test_non_paratext_inside_sp_included_in_primary_text(self):
        # <p> resets inside_paratext when it starts, so spoken lines are included
        parser = _parse("<sp><speaker>Chorus</speaker><p>spoken line</p></sp>")
        assert "spoken line" in parser.primary_text

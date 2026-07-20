# tests/test_chunking.py
#
# Tests for the chunk-alignment logic in mvp.site.app: given a passage
# citation from one chunking scheme (e.g. Perseus "card" numbers), find the
# corresponding chunk in a sibling version that may be chunked at a
# different granularity (e.g. scene-based line ranges).
#
# _chunk_start_line and _find_chunk_for_line are private but are the core
# logic fixed by the card/translation-alignment bug: card chunking used to
# fall back to raw positional indexing across chunk lists of very different
# density, landing on unrelated passages (see _build_sibling_data).

from __future__ import annotations

from mvp.site.app import _chunk_start_line, _find_chunk_for_line


# ---------------------------------------------------------------------------
# _chunk_start_line
# ---------------------------------------------------------------------------

class TestChunkStartLine:
    """Parsing a chunk's passage citation into a sortable key."""

    def test_card_level_single_line_number(self):
        urn = "urn:cts:greekLit:tlg0011.tlg001.perseus-grc2:94"
        assert _chunk_start_line(urn) == (94,)

    def test_scene_level_line_range_uses_start(self):
        """A range citation ("94-140") contributes only its start line."""
        urn = "urn:cts:greekLit:tlg0011.tlg001.perseus-grc2:94-140"
        assert _chunk_start_line(urn) == (94,)

    def test_dotted_book_and_line_citation(self):
        """Each dot-separated component contributes its own leading integer,
        so book/line citations sort correctly across book rollovers."""
        urn = "urn:cts:latinLit:phi0448.phi001.perseus-lat1:2.1"
        assert _chunk_start_line(urn) == (2, 1)

    def test_letter_suffix_is_ignored(self):
        urn = "urn:cts:greekLit:tlg0011.tlg001.perseus-grc2:1a"
        assert _chunk_start_line(urn) == (1,)

    def test_non_integer_citation_does_not_raise(self):
        """Unexpected input (no leading digits) contributes 0 rather than
        raising, per the _chunk_start_line docstring."""
        urn = "urn:cts:greekLit:tlg0011.tlg001.perseus-grc2:pr"
        assert _chunk_start_line(urn) == (0,)

    def test_book_rollover_sorts_correctly(self):
        """"2.1" must sort after "1.93", unlike naive whole-string parsing."""
        end_of_book_one = _chunk_start_line("urn:...:1.93")
        start_of_book_two = _chunk_start_line("urn:...:2.1")
        assert end_of_book_one < start_of_book_two


# ---------------------------------------------------------------------------
# _find_chunk_for_line
# ---------------------------------------------------------------------------

def _chunk(urn: str) -> dict:
    return {"cts_urn": urn, "file": f"{urn.rsplit(':', 1)[-1]}.html"}


class TestFindChunkForLine:
    """Finding the chunk with the greatest start line at or before a target."""

    SCENE_CHUNKS = [
        _chunk("urn:cts:greekLit:tlg0011.tlg001.perseus-eng3:1-93"),
        _chunk("urn:cts:greekLit:tlg0011.tlg001.perseus-eng3:94-140"),
        _chunk("urn:cts:greekLit:tlg0011.tlg001.perseus-eng3:141-495"),
        _chunk("urn:cts:greekLit:tlg0011.tlg001.perseus-eng3:497-530"),
    ]

    CARD_CHUNKS = [_chunk(f"urn:cts:greekLit:tlg0011.tlg001.perseus-grc2:{n}") for n in (1, 90, 94, 95, 100)]

    def test_card_number_lands_in_containing_scene(self):
        """The bug this guards against: a card-94 citation must resolve to
        the scene chunk starting at line 94, not one far downstream."""
        target = _chunk_start_line("urn:...:94")
        result = _find_chunk_for_line(self.SCENE_CHUNKS, target)
        assert result["cts_urn"].endswith(":94-140")

    def test_line_mid_scene_lands_in_containing_scene(self):
        target = _chunk_start_line("urn:...:200")
        result = _find_chunk_for_line(self.SCENE_CHUNKS, target)
        assert result["cts_urn"].endswith(":141-495")

    def test_exact_start_line_match(self):
        target = _chunk_start_line("urn:...:497")
        result = _find_chunk_for_line(self.SCENE_CHUNKS, target)
        assert result["cts_urn"].endswith(":497-530")

    def test_line_before_first_chunk_returns_none(self):
        target = _chunk_start_line("urn:...:0")
        assert _find_chunk_for_line(self.SCENE_CHUNKS, target) is None

    def test_card_level_chunks_match_by_exact_line(self):
        """Card chunks are dense (one line per chunk), so the nearest
        at-or-before match should be exact when the line itself is a chunk."""
        target = _chunk_start_line("urn:...:94")
        result = _find_chunk_for_line(self.CARD_CHUNKS, target)
        assert result["cts_urn"].endswith(":94")

    def test_card_level_chunk_between_cards_falls_back(self):
        target = _chunk_start_line("urn:...:92")
        result = _find_chunk_for_line(self.CARD_CHUNKS, target)
        assert result["cts_urn"].endswith(":90")

    def test_empty_chunk_list_returns_none(self):
        assert _find_chunk_for_line([], _chunk_start_line("urn:...:1")) is None

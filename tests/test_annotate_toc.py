# tests/test_annotate_toc.py
#
# _annotate_toc stamps endpoint/route_kwargs onto TOC entries so
# NavigationItem.html.jinja can build hrefs via
# url_for(item.endpoint, **item.route_kwargs). A leaf entry (no
# subpassages) built from a unit_scheme_map-driven toc() carries its own
# "scheme" key, which is None whenever its unit isn't in the map (e.g. a
# "section" nested under chapter/section that isn't independently
# paginated). That leaf still needs a link — it just routes within the
# ambient scheme — but a prior bug skipped annotating it entirely,
# leaving the entry without endpoint/route_kwargs and crashing the
# template's unconditional url_for() call for leaves.

from __future__ import annotations

from mvp.site.app import _annotate_toc


def test_leaf_with_none_scheme_still_gets_route_kwargs():
    entries = [
        {
            "urn": "urn:cts:greekLit:tlg0058.tlg001.perseus-grc2:1",
            "label": "Chapter 1",
            "subtype": "chapter",
            "scheme": "",
            "subpassages": [
                {
                    "urn": "urn:cts:greekLit:tlg0058.tlg001.perseus-grc2:1.1",
                    "label": "Section 1",
                    "subtype": "section",
                    "scheme": None,
                    "subpassages": [],
                }
            ],
        }
    ]

    _annotate_toc(entries, "greekLit", "tlg0058", "tlg001", "perseus-grc2")

    leaf = entries[0]["subpassages"][0]
    assert leaf["endpoint"] == "reading_view"
    assert leaf["route_kwargs"] == {
        "corpus": "greekLit",
        "textgroup": "tlg0058",
        "work": "tlg001",
        "version": "perseus-grc2",
        "chunk": "1.1",
    }


def test_intermediate_level_with_none_scheme_is_left_unlinked():
    """An entry with subpassages and no own scheme (e.g. "book") stays a
    plain, non-clickable span — it isn't independently paginated."""
    entries = [
        {
            "urn": "urn:cts:greekLit:tlg0058.tlg001.perseus-grc2:1",
            "label": "Book 1",
            "subtype": "book",
            "scheme": None,
            "subpassages": [
                {
                    "urn": "urn:cts:greekLit:tlg0058.tlg001.perseus-grc2:1.1",
                    "label": "Chapter 1",
                    "subtype": "chapter",
                    "scheme": "",
                    "subpassages": [],
                }
            ],
        }
    ]

    _annotate_toc(entries, "greekLit", "tlg0058", "tlg001", "perseus-grc2")

    book_entry = entries[0]
    assert "endpoint" not in book_entry
    assert "route_kwargs" not in book_entry

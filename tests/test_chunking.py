"""Tests for copy_before and elements_between in mvp.cts_resolver."""
from __future__ import annotations

from lxml import etree

from mvp.cts_resolver import copy_before, elements_between


def _xml(text: str) -> etree._Element:
    return etree.fromstring(text)


class TestCopyBefore:

    def test_stop_none_returns_full_deep_copy(self):
        el = _xml("<p>hello <em>world</em> end</p>")
        copy = copy_before(el, None)
        assert etree.tostring(copy) == etree.tostring(el)
        assert copy is not el

    def test_stop_is_direct_child_truncates_before_it(self):
        el = _xml("<div><p>first</p><p>second</p><p>third</p></div>")
        stop = el[1]   # second <p>
        copy = copy_before(el, stop)
        children = list(copy)
        assert len(children) == 1
        assert children[0].text == "first"

    def test_stop_is_nested_truncates_inside_parent(self):
        # stop is inside the second <p> — first <p> should be whole,
        # second <p> should be copied up to but not including stop.
        root = _xml("<div><p>A</p><p>B<em>C</em>D</p><p>E</p></div>")
        em = root[1][0]   # the <em> inside second <p>
        copy = copy_before(root, em)
        assert len(list(copy)) == 2       # first <p> + truncated second <p>
        second = list(copy)[1]
        assert list(second) == []         # <em> removed
        assert second.text == "B"

    def test_preserves_attributes(self):
        el = _xml('<div n="1"><p class="x">text</p></div>')
        copy = copy_before(el, None)
        assert copy.get("n") == "1"
        assert list(copy)[0].get("class") == "x"


class TestElementsBetween:

    def _make_doc(self):
        """
        <body>
          <milestone n="1"/>
          <div><p>first div</p></div>
          <milestone n="2"/>
          <div><p>second div</p></div>
          <milestone n="3"/>
        </body>
        """
        body = etree.Element("body")
        m1 = etree.SubElement(body, "milestone", n="1")
        d1 = etree.SubElement(body, "div")
        etree.SubElement(d1, "p").text = "first div"
        m2 = etree.SubElement(body, "milestone", n="2")
        d2 = etree.SubElement(body, "div")
        etree.SubElement(d2, "p").text = "second div"
        m3 = etree.SubElement(body, "milestone", n="3")
        return body, m1, m2, m3

    def test_returns_elements_between_two_milestones(self):
        body, m1, m2, _ = self._make_doc()
        result = elements_between(body, m1, m2)
        assert len(result) == 1
        assert result[0].tag == "div"
        assert result[0][0].text == "first div"

    def test_end_none_collects_to_end(self):
        body, _, m2, _ = self._make_doc()
        result = elements_between(body, m2, None)
        # d2 + m3 are both top-level siblings after m2; milestones are not
        # filtered here — the caller (Transformer) suppresses them.
        divs = [e for e in result if e.tag == "div"]
        assert len(divs) == 1
        assert divs[0][0].text == "second div"

    def test_results_are_copies_not_originals(self):
        body, m1, m2, _ = self._make_doc()
        result = elements_between(body, m1, m2)
        originals = [e for e in body if e.tag == "div"]
        assert result[0] is not originals[0]

    def test_milestone_inside_element_truncates_at_boundary(self):
        """Milestone falls inside a <p>; the copy should be truncated there."""
        body = etree.Element("body")
        m1 = etree.SubElement(body, "milestone", n="1")
        p = etree.SubElement(body, "p")
        p.text = "before"
        m2 = etree.SubElement(p, "milestone", n="2")
        m2.tail = "after"
        etree.SubElement(body, "milestone", n="3")

        result = elements_between(body, m1, m2)
        # Should return the truncated <p>
        assert len(result) == 1
        assert result[0].tag == "p"
        assert result[0].text == "before"
        assert list(result[0]) == []     # m2 was truncated out

    def test_no_elements_between_adjacent_milestones(self):
        body = etree.Element("body")
        m1 = etree.SubElement(body, "milestone", n="1")
        m2 = etree.SubElement(body, "milestone", n="2")
        result = elements_between(body, m1, m2)
        assert result == []

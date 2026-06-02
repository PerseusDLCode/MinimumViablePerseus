"""Tree-surgery utilities for extracting content between milestone elements.

These functions implement the least-common-ancestor (LCA) extraction
strategy: given two boundary milestone elements in a document, collect
the top-level elements strictly between them, truncating any element that
spans a boundary.

Ported from tei-tagger/src/tei_tagger/between_milestones.py, stripped of
all HTML-generation logic.
"""
from __future__ import annotations

from copy import deepcopy

from lxml import etree


def copy_before(
    element: etree._Element,
    stop: etree._Element | None,
) -> etree._Element:
    """Return a deep copy of element with all content at or after stop removed.

    If stop is None the element is deep-copied in full.  Walks children in
    document order; as soon as a child is (or contains) the stop node it
    truncates there.
    """
    if stop is None:
        return deepcopy(element)

    new = etree.Element(element.tag, attrib=element.attrib)
    new.text = element.text
    for child in element:
        if child is stop:
            break
        if any(desc is stop for desc in child.iter()):
            new.append(copy_before(child, stop))
            break
        new.append(deepcopy(child))
    return new


def elements_between(
    root: etree._Element,
    start_ms: etree._Element,
    end_ms: etree._Element | None,
) -> list[etree._Element]:
    """Return top-level elements between two milestones in document order.

    Elements are returned as copies, truncated at end_ms when end_ms falls
    inside a containing element.  Passing end_ms=None collects everything
    after start_ms to the end of the tree.

    "Top-level" means no ancestor of the element is also in the result set
    (LCA policy): when a parent and a descendant both fall between the
    milestones, only the parent is returned.
    """
    all_elements = list(root.iter())
    pos = {id(e): i for i, e in enumerate(all_elements)}

    start = pos[id(start_ms)]
    end = pos[id(end_ms)] if end_ms is not None else len(all_elements)

    hits = [e for e in all_elements if start < pos[id(e)] < end]
    hit_ids = {id(e) for e in hits}
    top = [e for e in hits if not any(id(a) in hit_ids for a in e.iterancestors())]

    return [copy_before(el, end_ms) for el in top]

"""Transformer base class for TEI → Protopage element conversion.

Subclasses register (matcher, handler) pairs in their __init__.  The first
matching handler is called; register() prepends so the last registration wins,
allowing subclasses to override base-class rules.
"""
from __future__ import annotations

from typing import Callable

from lxml import etree

from mvp.corpus.tei_document import LenientTEIDocument

# A handler receives (transformer, element) and returns a list of output
# elements.  Returning [] suppresses the element.
Handler = Callable[["Transformer", etree._Element], list[etree._Element]]
Matcher = Callable[[etree._Element], bool]


def _localname(element: etree._Element) -> str:
    return etree.QName(element.tag).localname


def _tag_matcher(localname: str) -> Matcher:
    return lambda el: _localname(el) == localname


def _tag_attr_matcher(localname: str, attr: str, value: str) -> Matcher:
    return lambda el: _localname(el) == localname and el.get(attr) == value


def _rescue_tail(
    suppressed: etree._Element,
    parent_out: etree._Element,
) -> None:
    """Append the tail of a suppressed element to sibling or parent text."""
    tail = suppressed.tail
    if not tail:
        return
    siblings = list(parent_out)
    if siblings:
        last = siblings[-1]
        last.tail = (last.tail or "") + tail
    else:
        parent_out.text = (parent_out.text or "") + tail


class Transformer:
    """Base class for TEI → Protopage element transformers.

    Subclasses register handlers in __init__.  Each handler is a callable
    (transformer, element) -> list[etree._Element].  The first registered
    handler whose matcher returns True is used; register() prepends, so the
    last call to register() wins.
    """

    def __init__(self, tei_doc: LenientTEIDocument) -> None:
        self.tei_doc = tei_doc
        self._handlers: list[tuple[Matcher, Handler]] = []
        self._register_defaults()

    def _register_defaults(self) -> None:
        """Register the built-in catch-all: descend without wrapping."""
        self._handlers.append((lambda el: True, Transformer._descend))

    def register(self, matcher: Matcher | str, handler: Handler) -> None:
        """Prepend a (matcher, handler) pair.

        matcher may be a tag-localname string as shorthand for a tag matcher.
        """
        if isinstance(matcher, str):
            matcher = _tag_matcher(matcher)
        self._handlers.insert(0, (matcher, handler))

    def apply(self, element: etree._Element) -> list[etree._Element]:
        """Dispatch element to its handler; return list of output elements."""
        for matcher, handler in self._handlers:
            if matcher(element):
                return handler(self, element)
        return []   # unreachable: default catch-all always matches

    def apply_all(self, elements: list[etree._Element]) -> list[etree._Element]:
        """Apply to every element in the list, flattening results."""
        out: list[etree._Element] = []
        for el in elements:
            out.extend(self.apply(el))
        return out

    @staticmethod
    def _descend(t: Transformer, element: etree._Element) -> list[etree._Element]:
        """Default handler: recurse into children, no wrapper element."""
        return t.apply_all(list(element))

    @staticmethod
    def _suppress(_t: Transformer, _el: etree._Element) -> list[etree._Element]:
        return []

    @staticmethod
    def _copy_inline(
        t: Transformer,
        element: etree._Element,
        out_tag: str,
        copy_attrs: list[str] | None = None,
    ) -> list[etree._Element]:
        """Wrap element's children (recursively transformed) in out_tag.

        Preserves element.text directly; tail text is handled by the caller
        via _rescue_tail.
        """
        out = etree.Element(out_tag)
        out.text = element.text
        for child in element:
            children_out = t.apply(child)
            if children_out:
                out.extend(children_out)
            else:
                _rescue_tail(child, out)
        if copy_attrs:
            for attr in copy_attrs:
                val = element.get(attr)
                if val is not None:
                    out.set(attr, val)
        return [out]

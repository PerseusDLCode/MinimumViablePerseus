import logging
import re
import string

from pathlib import Path
from xml.sax import xmlreader
from xml.sax.handler import ContentHandler

import lxml.sax  # ty: ignore

from lxml import etree

from mvp.constants import NS

PARATEXTUAL_ELEMENTS = frozenset({"note", "noteGrp", "speaker", "sp"})

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)

formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")

console_handler.setFormatter(formatter)

logger.addHandler(console_handler)


def remove_ns_from_attrs(attrs: xmlreader.AttributesNSImpl):
    a = {}

    for k, v in attrs.items():
        _ns, localname = k

        a[localname] = v

    return a


class TEIParserError(Exception):
    pass


class TEIParser(ContentHandler):
    def __init__(self, root: etree._Element, base_urn: str, chunk_unit: str):
        self.root = root
        self.base_urn = base_urn
        self.chunk_unit = chunk_unit

        self.citable_parts = []
        self.citable_stack = []
        self.current_urn = None
        self.elements = []
        self.element_set = set()
        self.element_stack = []
        self.global_element_index = 0
        self.inside_paratext = False
        self.primary_text = ""
        self._pending_speaker = None

        lxml.sax.saxify(self.root, self)

    def characters(self, content: str) -> None:
        if len(self.element_stack) == 0:
            if content.strip() != "":
                logger.warning(
                    "\t\tCharacters must belong to an element, but no elements are available."
                )
                logger.warning(content)
            return

        if content.strip() == "":
            return

        parent_element = self.element_stack[-1]

        if not self.inside_paratext:
            self.primary_text += content

        text_run = {"tagname": "text_run", "content": content.strip()}

        if text_run:
            parent_element["children"].append(text_run)

    def endElementNS(self, name: tuple[str | None, str], qname: str | None) -> None:
        _uri, localname = name

        el = self.element_stack.pop()

        if el.get("tagname") == "speaker":
            self._pending_speaker = el

        if el.get("type") is not None and el.get("n") is not None:
            self.citable_stack.pop()

        # Don't append the element if it
        # is part of another element's children — it will
        # be appended with that element
        if len(self.element_stack) > 0:
            if (
                len(
                    [
                        x
                        for x in self.element_stack[-1]["children"]
                        if x.get("index") == el["index"]
                    ]
                )
                == 0
            ):
                self.elements.append(el)
        else:
            self.elements.append(el)

    def handle_element(self, tagname: str, attrs: dict):
        element_index = self.global_element_index

        self.global_element_index += 1

        if tagname == "speaker":
            self._pending_speaker = None

        if attrs.get("type") is not None and attrs.get("n") is not None:
            self.citable_stack.append(attrs)

            location = [c["n"] for c in self.citable_stack if c.get("n")]

            self.current_urn = f"{self.base_urn}:{'.'.join(location)}"

        attrs.update(
            {
                "children": [],
                "index": element_index,
                "tagname": tagname,
                "urn": self.current_urn,
            }
        )

        if len(self.element_stack) > 0:
            self.element_stack[-1]["children"].append(attrs)

        self.element_stack.append(attrs)

        self.maybe_toggle_inside_paratext(tagname)

    def maybe_toggle_inside_paratext(self, tagname: str):
        if tagname in PARATEXTUAL_ELEMENTS:
            self.inside_paratext = True
        else:
            self.inside_paratext = False

    def startElementNS(
        self,
        name: tuple[str | None, str],
        qname: str | None,
        attrs: xmlreader.AttributesNSImpl,
    ) -> None:
        _uri, localname = name
        clean_attrs = remove_ns_from_attrs(attrs)

        self.element_set.add(localname)
        self.handle_element(localname, clean_attrs)

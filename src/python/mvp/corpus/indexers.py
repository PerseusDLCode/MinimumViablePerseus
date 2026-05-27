from __future__ import annotations

import re
from pathlib import Path

from lxml import etree

from mvp.corpus.models import ChunkIndex, ChunkOccurrence, WordIndex, WordOccurrence
from mvp.corpus.tei_constants import NS


class TEIIndexer:
    excluded_tags: list[str] = []

    def __init__(self, doc: Path | str) -> None:
        self.doc = doc
        self.exclusions = {f"{{http://www.tei-c.org/ns/1.0}}{tag}" for tag in self.excluded_tags}
        self._tree = None

    @property
    def tree(self):
        if self._tree is None:
            parser = etree.XMLParser(remove_blank_text=True)
            self._tree = etree.parse(self.doc, parser)
        return self._tree

    @property
    def root(self):
        return self.tree.getroot()

    def xpath_for(self, elem) -> str:
        """Return a readable XPath string for elem using tei: prefixes."""
        path_parts = []
        for node in elem.xpath('ancestor-or-self::*'):
            name = etree.QName(node).localname
            siblings = node.xpath(f'preceding-sibling::tei:{name}', namespaces=NS)
            index = len(siblings) + 1
            path_parts.append(f"tei:{name}[{index}]")
        return "/" + "/".join(path_parts)


class WordIndexer(TEIIndexer):
    excluded_tags = ["teiHeader", "del", "note", "cit", "bibl", "rdg", "head"]

    def __init__(self, doc: Path | str) -> None:
        super().__init__(doc)
        self._word_index: WordIndex | None = None

    @property
    def word_index(self) -> WordIndex:
        if self._word_index is None:
            self._word_index = self._generate_word_index()
        return self._word_index

    def _generate_word_index(self) -> WordIndex:
        entries: dict[str, set[WordOccurrence]] = {}
        for elem in self.root.iter():
            elem_excluded = any(anc.tag in self.exclusions
                                for anc in elem.xpath('ancestor-or-self::*'))
            if not elem_excluded and elem.text and elem.text.strip():
                xpath_context = self.xpath_for(elem)
                for match in re.finditer(r"[\w'']+", elem.text, re.UNICODE):
                    word = match.group().lower()
                    start, end = match.span()
                    entries.setdefault(word, set()).add(
                        WordOccurrence(xpath_context, start, end)
                    )

            # tail text is logically part of the parent element, not this one
            if elem.tail and elem.tail.strip():
                parent = elem.getparent()
                if parent is not None:
                    parent_excluded = any(anc.tag in self.exclusions
                                          for anc in parent.xpath('ancestor-or-self::*'))
                    if not parent_excluded:
                        xpath_context = self.xpath_for(parent)
                        for match in re.finditer(r"[\w'']+", elem.tail, re.UNICODE):
                            word = match.group().lower()
                            start, end = match.span()
                            entries.setdefault(word, set()).add(
                                WordOccurrence(xpath_context, start, end)
                            )

        return WordIndex(entries=entries)


class ChunkIndexer(TEIIndexer):
    excluded_tags = ["teiHeader", "del", "note", "cit", "bibl", "rdg", "head"]
    chunk_tags = ["p", "l", "lg", "ab"]

    def __init__(self, doc: Path | str) -> None:
        super().__init__(doc)
        self.chunk_qnames = {f"{{http://www.tei-c.org/ns/1.0}}{tag}" for tag in self.chunk_tags}
        self._chunk_index: ChunkIndex | None = None

    @property
    def chunk_index(self) -> ChunkIndex:
        if self._chunk_index is None:
            self._chunk_index = self._generate_chunk_index()
        return self._chunk_index

    def _generate_chunk_index(self) -> ChunkIndex:
        """Map XPaths of chunk elements to their full, filtered text content."""
        index = ChunkIndex()
        for elem in self.root.iter():
            if elem.tag in self.chunk_qnames:
                xpath = self.xpath_for(elem)
                element_name = etree.QName(elem).localname
                text_bits: list[str] = []
                self._collect_text(elem, text_bits)
                full_text = "".join(text_bits).strip()
                if full_text:
                    index.entries.append(
                        ChunkOccurrence(xpath=xpath, element=element_name, chunk=full_text)
                    )
        return index

    def _collect_text(self, node, text_bits: list[str]) -> None:
        """Recursively collect text while respecting the exclusion list."""
        if node.tag in self.exclusions:
            # tail belongs to the parent, not this excluded node
            if node.tail:
                text_bits.append(node.tail)
            return
        if node.text:
            text_bits.append(node.text)
        for child in node:
            self._collect_text(child, text_bits)
        if node.tail:
            text_bits.append(node.tail)

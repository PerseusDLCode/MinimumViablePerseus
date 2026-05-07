from pathlib import Path
import re
from lxml import etree

from mvp.models import ChunkIndex, ChunkOccurrence, WordIndex, WordOccurrence

class TEIIndexer:
    ns = {'tei': 'http://www.tei-c.org/ns/1.0'}
    excluded_tags = ["teiHeader", "del", "note", "cit", "bibl", "rdg", "head"]

    def __init__(self, doc:Path | str) -> None:
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

    def xpath_for(self, elem):
        """Returns a readable XPath string using 'tei' prefixes."""
        path_parts = []
        for node in elem.xpath('ancestor-or-self::*'):
            name = etree.QName(node).localname
            siblings = node.xpath(f'preceding-sibling::tei:{name}', namespaces=self.ns)
            index = len(siblings) + 1
            path_parts.append(f"tei:{name}[{index}]")
        return "/" + "/".join(path_parts)




class WordIndexer(TEIIndexer):
    def __init__(self, doc:Path | str) -> None:
        super().__init__(doc)
        self._word_index = None

    @property
    def word_index(self) -> WordIndex:
        if self._word_index is None:
            self._word_index = self._generate_word_index()
        return self._word_index


    def _generate_word_index(self) -> WordIndex:
        entries: dict = {}
        for elem in self.root.iter():
            elem_excluded = any(anc.tag in self.exclusions
                                for anc in elem.xpath('ancestor-or-self::*'))

            if not elem_excluded and elem.text and elem.text.strip():
                xpath_context = self.xpath_for(elem)
                for match in re.finditer(r"[\w'']+", elem.text, re.UNICODE):
                    word = match.group().lower()
                    start, end = match.span()
                    occurrence: WordOccurrence = WordOccurrence(xpath_context, start, end)
                    entries.setdefault(word, set()).add(occurrence)


            # tail text is logically part of the parent element, not this one
            if elem.tail and elem.tail.strip():
                parent = elem.getparent()
                if parent is not None:
                    parent_excluded = any(anc.tag in self.exclusions for anc in parent.xpath('ancestor-or-self::*'))
                    if not parent_excluded:
                        xpath_context = self.xpath_for(parent)
                        for match in re.finditer(r"[\w'']+", elem.tail, re.UNICODE):
                            word = match.group().lower()
                            start, end = match.span()
                            occurrence: WordOccurrence = WordOccurrence(xpath_context, start, end)
                            entries.setdefault(word, set()).add(occurrence)


        return WordIndex(entries=entries)


class ChunkIndexer(TEIIndexer):
    # Tags that define a "chunk" for NLP
    chunk_tags = ["p", "l", "lg", "ab"]

    def __init__(self, doc: Path | str) -> None:
        super().__init__(doc)
        self.chunk_qnames = {f"{{http://www.tei-c.org/ns/1.0}}{tag}" for tag in self.chunk_tags}

    def generate_chunks(self) -> ChunkIndex:
        """Maps XPaths of chunk elements to their full, filtered text content."""
        index: ChunkIndex = ChunkIndex()


        # Iterate only over tags we consider "chunks"
        for elem in self.root.iter():
            if elem.tag in self.chunk_qnames:
                xpath = self.xpath_for(elem)
                # Collect text only from non-excluded descendants
                text_bits = []
                self._collect_text(elem, text_bits)
                full_text = "".join(text_bits).strip()

                if full_text:
                    index.entries.append(ChunkOccurrence(xpath, full_text))

        return index


    def _collect_text(self, node, text_bits):
        """Recursively collects text while respecting the exclusion list."""
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

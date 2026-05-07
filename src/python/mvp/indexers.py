from pathlib import Path
import re
from lxml import etree

class WordIndexer:
    ns = {'tei': 'http://www.tei-c.org/ns/1.0'}
    excluded_tags = ["teiHeader", "del", "note", "cit", "bibl", "rdg", "head"]

    def __init__(self, doc:Path | str) -> None:
        self.doc = doc
        self.exclusions = {f"{{http://www.tei-c.org/ns/1.0}}{tag}" for tag in self.excluded_tags}
        self._tree = None
        self._word_index = None

    @property
    def tree(self):
        if self._tree is None:
            parser = etree.XMLParser(remove_blank_text=True)
            self._tree = etree.parse(self.doc, parser)
        return self._tree

    @property
    def word_index(self) -> dict(str,str):
        if self._word_index is None:
            self._word_index = self._generate_word_index()
        return self._word_index



    @property
    def root(self):
        return self.tree.getroot()


    def get_tei_path(self, elem):
        """Returns a readable XPath string using 'tei' prefixes."""
        path_parts = []
        for node in elem.xpath('ancestor-or-self::*'):
            # Strip the {url} from the tag to get just the local name
            name = etree.QName(node).localname

            # Find the position among siblings of the same name
            siblings = node.xpath(f'preceding-sibling::tei:{name}', namespaces=self.ns)
            index = len(siblings) + 1
            path_parts.append(f"tei:{name}[{index}]")

        return "/" + "/".join(path_parts)


    def _generate_word_index(self) -> dict:
        index: dict = {}
        for elem in self.root.iter():
            elem_excluded = any(anc.tag in self.exclusions for anc in elem.xpath('ancestor-or-self::*'))

            if not elem_excluded and elem.text and elem.text.strip():
                xpath_context = self.get_tei_path(elem)
                for word in re.findall(r"[\w'’]+",elem.text, re.UNICODE):
                    index.setdefault(word.lower(), set()).add(xpath_context)

            # tail text is logically part of the parent element, not this one
            if elem.tail and elem.tail.strip():
                parent = elem.getparent()
                if parent is not None:
                    parent_excluded = any(anc.tag in self.exclusions for anc in parent.xpath('ancestor-or-self::*'))
                    if not parent_excluded:
                        xpath_context = self.get_tei_path(parent)
                        for word in re.findall(r"[\w'’]+",elem.tail, re.UNICODE):
                            index.setdefault(word.lower(), set()).add(xpath_context)
        return index

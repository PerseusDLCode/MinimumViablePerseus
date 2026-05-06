from pathlib import Path
import re
from lxml import etree

test_doc = Path("/Users/wulfmanc/repos/gh/PerseusDLCode/MinimumViablePerseus/tests/data/tlg0001.tlg001.perseus-grc2.xml")


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


    def generate_word_index(self) -> None:
        index = {}
        for elem in self.root.iter():
            if any(anc.tag in self.exclusions for anc in elem.xpath('ancestor-or-self::*')):
                continue

            text_content = elem.text
            if text_content and text_content.strip():
                xpath_context = self.get_tei_path(elem)
                words = re.findall(r"[\w']+", text_content, re.UNICODE)

                for word in words:
                    word_key = word.lower()
                    if word_key not in index:
                        index[word_key] = set()
                    index[word_key].add(xpath_context)
        return index

"""Family1ProseTransformer — TEI → Protopage rules for hierarchical-div prose."""
from __future__ import annotations

from lxml import etree

from mvp.corpus.tei_document import LenientTEIDocument
from mvp.compilers.transformers.base import Transformer


def _make_gap() -> etree._Element:
    el = etree.Element("gap")
    el.text = "…"
    return el


class Family1ProseTransformer(Transformer):
    """Transformer for Family-1 hierarchical-div prose TEI texts.

    Implements the generate_protopages.xsl content-mode rule set:
      placeName → <place>, persName → <person>, q/quote → <q>,
      del/add preserved, gap → <gap>…</gap>, milestone/pb/note/head suppressed,
      everything else descends without wrapping.
    """

    def __init__(self, tei_doc: LenientTEIDocument) -> None:
        super().__init__(tei_doc)
        self._register_prose_rules()

    def _register_prose_rules(self) -> None:
        suppress = Transformer._suppress

        # Suppressed elements
        for tag in ("milestone", "pb", "note", "head"):
            self.register(tag, suppress)

        # Pass-through with element rename
        self.register("p",     lambda t, el: Transformer._copy_inline(t, el, "p"))
        self.register("q",     lambda t, el: Transformer._copy_inline(t, el, "q"))
        self.register("quote", lambda t, el: Transformer._copy_inline(t, el, "q"))
        self.register("del",   lambda t, el: Transformer._copy_inline(t, el, "del"))
        self.register("add",   lambda t, el: Transformer._copy_inline(t, el, "add"))

        # Gap marker — Unicode horizontal ellipsis per Charles's review
        self.register("gap", lambda _t, _el: [_make_gap()])

        # Named entities — copy optional @key attribute
        self.register(
            "placeName",
            lambda t, el: Transformer._copy_inline(t, el, "place", ["key"]),
        )
        self.register(
            "persName",
            lambda t, el: Transformer._copy_inline(t, el, "person", ["key"]),
        )

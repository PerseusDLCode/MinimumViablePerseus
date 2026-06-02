"""SchemaRegistry and TransformerFactory — select a Transformer by TEI schema."""
from __future__ import annotations

from mvp.corpus.tei_document import LenientTEIDocument
from mvp.compilers.transformers.base import Transformer
from mvp.compilers.transformers.prose_transformer import Family1ProseTransformer


class SchemaRegistry:
    """Maps TEI schema keys to Transformer subclasses."""

    def __init__(self) -> None:
        self._registry: dict[str, type[Transformer]] = {}

    def register(self, key: str, transformer_class: type[Transformer]) -> None:
        self._registry[key] = transformer_class

    def look_up(self, key: str) -> type[Transformer] | None:
        return self._registry.get(key)


_default_registry = SchemaRegistry()
_default_registry.register("perseus_prose", Family1ProseTransformer)
_default_registry.register("perseus_base",  Family1ProseTransformer)


class TransformerFactory:
    def __init__(self, registry: SchemaRegistry = _default_registry) -> None:
        self._registry = registry

    def transformer_for(self, doc: LenientTEIDocument) -> Transformer:
        # TEIDocument has .schema; LenientTEIDocument does not — default gracefully.
        key = getattr(doc, "schema", None) or "perseus_prose"
        cls = self._registry.look_up(key) or Family1ProseTransformer
        return cls(doc)

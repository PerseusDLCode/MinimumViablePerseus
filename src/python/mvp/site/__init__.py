# mvp/site — static site compilation.
#
# Downstream layer: consumes Corpus and Annotations to produce HTML.

from mvp.site.compilers import Compiler, CompilationError, PageCompiler, CatalogCompiler, XSLTCompiler, copy_static_assets
from mvp.site.pipeline import BuildPipeline
from mvp.site.site_map import SiteMap
from mvp.site.strategy import ChunkingStrategy, DivisionStrategy, MilestoneStrategy, StrategySelector
from mvp.site.citation_index import CitationIndexGenerator
from mvp.site.models import ChunkManifestEntry, ChunkManifest

__all__ = [
    "Compiler", "CompilationError", "PageCompiler", "CatalogCompiler",
    "XSLTCompiler", "copy_static_assets",
    "BuildPipeline",
    "SiteMap",
    "ChunkingStrategy", "DivisionStrategy", "MilestoneStrategy", "StrategySelector",
    "CitationIndexGenerator",
    "ChunkManifestEntry", "ChunkManifest",
]

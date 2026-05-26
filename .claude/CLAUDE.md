# Perseus 6 and Minimum Viable Perseus — Claude Code context



## Project Scope

### What Perseus 6 and Minimum Viable Perseus Are

Perseus 6 will be the successor to [Perseus 4, currently in
production](https://www.perseus.tufts.edu/hopper/). It will
incorporate functionality developed for the [Scaife
Viewer](https://scaife.perseus.org/) and [Beyond
Translation](https://beyond-translation.perseus.org/reader/urn:cts:engLit:mds822-32.tpsthl-1599.pdl-eng:1-6)
prototypes.

Minimum Viable Perseus (MVP) is the core of the new Perseus 6
architecture.  It is a collection of modules that compile Perseus's
TEI-encoded XML texts into a static website of interlinked HTML pages
navigable without JavaScript or a backend database.

### What MVP Produces

- **Static HTML pages** — TEI texts rendered as a three-column reader
  (table of contents, text, annotations), chunked by
  structural division or milestone

- **Basic Catalog pages** - Simple browsable lists of available texts

These are meant to be served on the web via a simple HTTP server.

### How MVP Works
MVP components are meant to be used in a compilation pipeline.

**TEI --> word indexes** - Indexers generate word indexes and chunk
  indexes linking word tokens and chunk elements to XPaths. These
  indexes are used by NLP modules to create morphological analyses,
  which may be compiled into the web pages.

**TEI --> citation indexes** - a ReferenceParser is used to generate
  an index of elements and CTS urns.  This index is used to implement
  hypertextual linking and passage alignments.

**TEI --> HTML** - XSLT stylesheets are used to generate HTML pages
  from TEI documents that are "chunked" according to the TEI structure
  and the document's refsDecls. XSL stylesheets also convert TEI
  elements into HTML elements, according to the customized TEI schema
  for the document.


### External Services
Because MVP is a static site, it has no built-in back-end server or
database. Some services, however, like full-text searching and word
study, are best implemented with the aid of databases. MVP is
designed, therefore, to be compiled (optionally) with links to
independent servers that can provide these functions.

The first of these is a morph-server, which implements an API that
returns morphological analyses.


### Tools and Utilities
Perseus's TEI text base has been developed over many years and needs
to be cleaned up before it can be used properly by Perseus 6. Several
auditors and linters are being developed to assist in that effort.

There are also several scripts that may be run to generate output:

| Script | Role |
|------------|------|
| `src/tools/run_audit.py` | Corpus runner for `StructureAuditor` and `ReferenceAuditor`; writes JSON reports |
| `src/tools/run_build.py` | Builds the site |
| `src/tools/generate_html_from_tei.py` | Transforms a single TEI document to HTML via an XSLT driver |


### Major Modules and Their Roles

#### XSLT

XSLT stylesheets live under `src/xslt/`, organized into two subdirectories.

**`src/xslt/corpus-prep/` — TEI corpus preparation and migration**

| Stylesheet | Role |
|------------|------|
| `corpus-prep/transform1.xsl` | Primary migration pass: replaces `<cRefPattern>` refsDecl with `<citeStructure>`, sets `@xml:base` on `<body>`, hoists div subtypes to types, strips legacy EpiDoc attributes |
| `corpus-prep/fix_milestones_and_subchapters.xsl` | Aristotle/Bekker-specific preparation: normalizes Bekker page+column milestones, flattens subchapter divs |

These stylesheets are run offline against the raw corpus before the build pipeline; they are not invoked by the build pipeline itself.

**`src/xslt/html/` — HTML generation pipeline**

| Stylesheet | Role |
|------------|------|
| `html/driver.xsl`              | Entry point: dispatches to the appropriate chunker via `$chunk-strategy`; defines the page shell and all enrichment parameters |
| `html/generate_div_chunks.xsl` | Chunk TEI by `<div>` structure into HTML pages |
| `html/generate_chunks.xsl`     | Chunk TEI by `<milestone>` elements into HTML pages |
| `html/chunker_core.xsl`        | Chunking infrastructure (boundary logic) imported by both chunkers |
| `html/variables.xsl`           | Shared variables (currently kept for future use; `$page-css` removed when CSS was externalized) |
| `html/tei/*.xsl`               | Rendering library: templates for TEI elements in `mode="tei-to-html"`, organized by Perseus schema level |

#### Python
Almost all source code lives under `src/python/`.  The primary package is
`mvp/`, organized into three architectural layers:

**`mvp/corpus/` — TEI document model (foundational; no dependency on site or annotations)**

| Module | Role |
|--------|------|
| `mvp/corpus/tei_constants.py` | Shared XML namespace constants and TEI tag definitions |
| `mvp/corpus/tei_document.py` | Thin TEI wrapper with recover-mode parser |
| `mvp/corpus/models.py` | Core corpus data objects: `TEIMetadata`, `CitationRecord`, `Word*`/`Chunk*` index types |
| `mvp/corpus/document.py` | `TEIDocument` — parses a TEI file and extracts metadata |
| `mvp/corpus/corpus.py` | `Corpus` — discovers and enumerates `TEIDocument`s under a root directory |
| `mvp/corpus/auditors.py` | `StructureAuditor`, `ReferenceAuditor` — analyze TEI structure and `refsDecl` declarations |
| `mvp/corpus/indexers.py` | `TEIIndexer`, `WordIndexer`, `ChunkIndexer` — extract word tokens and chunk elements with XPath provenance for NLP pipelines |
| `mvp/corpus/reference_parser.py` | `ReferenceParser` — resolves CTS URNs to TEI elements and generates CTS URNs from elements via `<citeStructure>`; raises `ConfigurationError` / `CitationError` |

**`mvp/annotations/` — enrichments derived from the corpus**

| Module | Role |
|--------|------|
| `mvp/annotations/citation_resolver.py` | `CitationResolver` — resolves scholarly abbreviation strings (e.g. "Hom. Od. 1.1") to CTS URNs via OCD abbreviation data |

**`mvp/site/` — static site compilation (downstream consumer of corpus and annotations)**

| Module | Role |
|--------|------|
| `mvp/site/models.py` | Site data objects: `ChunkManifestEntry`, `ChunkManifest` |
| `mvp/site/site_map.py` | `SiteMap` — owns the output path and URL scheme for all compiled artifacts |
| `mvp/site/strategy.py` | `ChunkingStrategy` and `StrategySelector` |
| `mvp/site/citation_index.py` | `CitationIndexGenerator` — generates a per-document citation index (citations.json) mapping CTS URNs to XML IDs and depths |
| `mvp/site/compilers/` | Compilation package: `Compiler` ABC (`base.py`), `PageCompiler`/`XSLTCompiler` (`page_compiler.py`), `CatalogCompiler` and `copy_static_assets` (`catalog_compiler.py`) |
| `mvp/site/pipeline.py` | `BuildPipeline` — orchestrates the site build |

Each layer's public API is re-exported from its `__init__.py`.  The NLP
team's integration point is the `annotations/` layer (not `site/`).

There is also code outside the `mvp` package, under `src/tools/`.

| Script | Role |
|--------|------|
| `src/tools/run_audit.py` | Commandline script to run audits on a Perseus corpus |
| `src/tools/run_build.py` | Builds the site |
| `src/tools/generate_html_from_tei.py` | Transforms a single TEI document to HTML via an XSLT driver |
| `src/tools/classify_corpus.py` | Classifies corpus documents by structure type |
| `src/tools/analyze_audit.py` | Analyzes audit output reports |


There is also an implementation of a simple morphological server at
`src/morph-server`. It was developed independently by a different
developer (Peter Nadel), and should probably be incorporated into the
rest of the MVP code base; however, a case could be made for keeping
it separate, as an "external service". We do not need to decide this now, however.


### Active Development

The following areas are currently under active development (see
`forum.org` for the full deliberative record and current TODO items):

- **Citation infrastructure**: `ReferenceParser` is complete (merged to
  `dev`, PRs #49 and #53).  Next steps: (1) connect
  `ReferenceParser.citations()` to the XSLT chunkers for navigation-link
  generation (undesigned — see open question in `#implement-reference-parser`);
  (2) migrate corpus from `<cRefPattern>` to `<citeStructure>` (design phase).
- **XSLT modularization**: refactoring chunker stylesheets into a
  proper stylesheet family (see `#reimplement-xslt-to-be-modular`)


### Deferred / Out of Scope for MVP

- Full-text search (delegated to external systems)
- Dynamic morphological analysis at request time (delegated; MVP
  provides the data, not the service)
- SpaCy integration at corpus scale (experimental branch exists;
  not yet merged or designed for production)
- Bekker citation support (design agreed; implementation deferred)


## Corpora

The primary corpora are kept in GitHub repositories:

- [canonical-greekLit](https://github.com/PerseusDL/canonical-greekLit)
- [canonical-latinLit](https://github.com/PerseusDL/canonical-latinLit)
- [csel-dev](https://github.com/OpenGreekAndLatin/csel-dev)
- [First1KGreek](https://github.com/OpenGreekAndLatin/First1KGreek)
- [canonical-pdlrefwk](https://github.com/PerseusDL/canonical-pdlrefwk) - reference works (public)
- [canonical_pdlrefwk](https://github.com/PerseusDL/canonical_pdlrefwk) - reference works (private)
- [lexica](https://github.com/PerseusDL/lexica) - Greek and Latin lexica

Note that the layout of these data repositories varies. Corpus-traversal code needs to be customized for each.

`canonical_greekLit` and `canonical-latinLit` do share the same
structure: they contain a `data/` subdirectory that contains
hierarchical subdirectories organized in the pattern of cts urns.
When traversing these directories for processing, beware of
__cts__.xml metadata files.


## Further Reading

- `wiki/` — project wiki: standards, workflows, CTS
  URN architecture, chunking design
- `forum.org` — deliberative record: research, decisions,
  implementation notes for all significant work items
- `.claude/guidelines/` — coding conventions; read before any coding
  task
- `docs/Cayless_et_al_-_Introducing_Citation_Structures.pdf` —
  background reading for citation infrastructure work


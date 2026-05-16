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
| `run_audit.py` | Corpus runner for `StructureAuditor` and `ReferenceAuditor`; writes JSON reports |
| `run_build.py` | Builds the site |


### Major Modules and Their Roles

#### XSLT

XSLT stylesheets live under `src/xslt/`.

| Stylesheet | Role |
|------------|------|
| `xslt/add_xml_ids.xsl`         | Preparation pass: add stable `xml:id` to citable elements (obsolete) |
| `xslt/tokenize.xsl`            | Extract word tokens as `<tokens>/<token>` document (obsolete) |
| `html/generate_div_chunks.xsl` | Chunk TEI by `<div>` structure into HTML pages |
| `html/generate_chunks.xsl`     | Chunk TEI by `<milestone>` elements into HTML pages |
| `html/chunker_core.xsl`        | Shared CSS design system and templates imported by both chunkers |
| `html/driver.xsl`              | A stub driver file for combining  TEI->HTML XSL stylesheets     |
| `html/variables.xsl`           | The start of a file to hold variables common to all stylesheets     |
| `html/tei/*.xsl`               | Stylesheets tailored to cover elements and attributes defined in Perseus TEI custom schemas     |


`xslt/add_xml_ids.xsl` and `xslt/tokenize.xsl` are obsolete, because we are shifting to a new workflow that uses indexers.

#### Python
Almost all source code lives under `src/python/`.  The primary package is
`mvp/`.

| Module | Role |
|--------|------|
| `mvp/auditors.py` | `StructureAuditor`, `ReferenceAuditor` — analyze TEI document structure and `refsDecl` declarations |
| `mvp/compilers.py` | PageCompiler and CatalogCompiler. Other compilation activities should get their own classes here. |
| `mvp/corpus.py` | the Corpus object discovers and enumerates TEI source documents (TEIDocuments) under a root directory |
| `mvp/document.py` | One version of the TEIDocument class, with extracted metadata |
| `mvp/indexers.py` | `TEIIndexer`, `WordIndexer`, `ChunkIndexer` — extract word tokens and chunk elements with XPath provenance for NLP pipelines |
| `mvp/linters.py` | Probably obsolete |
| `mvp/tei_document.py` | Thin TEI wrapper with recover-mode parser; shared by auditors and normalizers |
| `mvp/models.py`| Core data objects for the build pipeline |
| `mvp/normalizers.py` | Phases 2 and 3 of the citation pipeline: repair `xml:base`, add `xml:id` (status: possibly superseded by `citeStructure` approach; retained pending decision) |
| `mvp/pipeline.py` | BuildPipeline : orchestrates the site build |
| `mvp/site_map.py` | owns the output path and URL scheme for all compiled artifacts |
| `mvp/strategy.py` | ChunkingStrategy and StrategySelector  |
| `run_build.py` | Builds the site |
| `run_audit.py` | Corpus runner for `StructureAuditor` and `ReferenceAuditor`; writes JSON reports |
| `tei_citation_pipeline.py` | CLI wrapper (legacy entry point; logic now in `auditors.py` and `normalizers.py`) |


There is also code outside the `mvp` package.

| Module | Role |
|--------|------|
|`src/python/run_audit.py` | commandline script to run audits on a Perseus corpus |
|`src/python/tei_citation_pipeline.py`       | an older script that combined auditing, normalizing, and adding xml ids. `run_audit.py` has been refactored out of it; the other tasks have been moved to `mvp/normalizers.py`.  This is ripe for cleanup.     |
|`/src/python/utils/*.py`       | Developed before the auditor tools; these scripts should be looked at to see if they are still needed.     |


There is also an implementation of a simple morphological server at
`src/morph-server`. It was developed independently by a different
developer (Peter Nadel), and should probably be incorporated into the
rest of the MVP code base; however, a case could be made for keeping
it separate, as an "external service". We do not need to decide this now, however.


### Active Development

The following areas are currently under active development (see
`forum.org` for the full deliberative record and current TODO items):

- **Citation infrastructure**: `ReferenceParser` implementation
  (resolves/generates CTS URNs via `<citeStructure>`); migration of
  corpus from `<cRefPattern>` to `<citeStructure>` (design phase)
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


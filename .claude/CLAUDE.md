# Minimum Viable Perseus — Claude Code context

## Context

`CLAUDE.md` is the primary context document for Claude Code and Claude Chat
sessions. The "Major Modules and Their Roles" section (line 186 onward) was
written to reflect a planned package reorganization and may not accurately
reflect the current state of the repository. Your task is to verify and update
it so that it is accurate.

## Instructions

1. **Survey the actual repo layout.** Walk `src/xslt/`, `src/python/mvp/`, and
   `src/tools/` and produce an accurate picture of what exists on disk. Do not
   rely on the existing tables in `CLAUDE.md`; verify against the filesystem.

2. **Update the XSLT tables.** For `src/xslt/`:
   - Confirm which subdirectories exist (`corpus-prep/`, `html/`, others).
   - List every stylesheet with an accurate one-line description of its role.
   - Note any stylesheets that are obsolete or superseded (e.g., if
     `generate_html_from_tei.py` / `driver.xsl` are being replaced by the
     proto-page pipeline, say so explicitly).

3. **Update the Python tables.** For `src/python/mvp/`:
   - Confirm the three-layer package structure (`corpus/`, `annotations/`,
     `site/`) exists as described, or note what the actual structure is.
   - List every module in each package with an accurate one-line description.
   - For `mvp/site/compilers/`, list every compiler module individually.
   - Note any modules listed in the current `CLAUDE.md` that do not exist, and
     any modules that exist but are not listed.

4. **Update the `src/tools/` table.** List every script under `src/tools/`
   with an accurate description. Note which tools belong to which pipeline
   (proto-page pipeline vs. legacy XSLT pipeline vs. corpus audit tools).

5. **Flag the proto-page pipeline status.** The "Active Development" section
   references branch `76-write-proto-page-compiler` as "awaiting PR/merge."
   Check whether this branch has been merged to `dev`. Update the status
   accordingly.

6. **Fix the garbled sentence.** Line 113 reads: "and t resolution of
   traditional citations to CTS URNs". Repair this to read: "and the
   resolution of traditional citations to CTS URNs".

## Constraints

- Do not change the architecture description prose (the Corpus / Annotations /
  Views layer descriptions). That content has been reviewed and approved.
- Do not change the Corpora section or the Further Reading section.
- Edit `CLAUDE.md` in place. Make a backup first (`CLAUDE.md.bak`).
- If you are uncertain whether a module is obsolete or just unused, note it
  with a `<!-- TODO: verify -->` comment rather than deleting it silently.

## Introduction
Minimum Viable Perseus (MVP) is a stepping-stone to the development
of Perseus 6, the successor to [Perseus 4, currently in
production](https://www.perseus.tufts.edu/hopper/). Perseus 6 will
incorporate functionality developed for the [Scaife
Viewer](https://scaife.perseus.org/) and [Beyond
Translation](https://beyond-translation.perseus.org/reader/urn:cts:engLit:mds822-32.tpsthl-1599.pdl-eng:1-6)
prototypes.

MVP is intended to replace Perseus 4 (P4, or "the Hopper"), which is
implemented in out-dated Java code running on unsupportable Tufts
infrastructure.  Its scope is deliberately narrow. MVP is not a
next-generation research platform.  It is a system that is
maintainable and deployable — one that preserves access to Perseus's
digital library of classical texts while the longer-term development
of Perseus 6 proceeds.



### Architecture
MVP is organized around three layers: **Corpus**, **Annotations**, and
**Views**. Each layer has a clearly bounded responsibility; each depends
on the layer below it but not on the layer above.

#### Corpus

The Corpus layer models the Perseus textual holdings and provides the
code infrastructure for working with them programmatically.

Perseus's texts are organized as a hierarchy of collections, following
the Canonical Text Services (CTS) URN architecture
(collection-\>textgroup-\>work-\>edition) , and the Corpus layer is
responsible for modeling it faithfully: traversing the file system,
parsing metadata, resolving identifiers.

The Corpus layer also models the internal structure of individual
encoded documents --- the `<div>` hierarchies and `<milestone>`
elements that represent intellectual divisions; the `<refsDecl>` and
`<citeStructure>` declarations that describe how those divisions
correspond to traditional citation schemes. This model is what makes
it possible to reason about documents, to chunk them, and to generate
navigation from them.

Besides these models, the corpus layer includes several modules that
may be used to work directly with the TEI documents.  They are
implemented in both Python and in XSLT.

##### Python modules

- **indexers.py** :
  - A **WordIndexer** that generates indexes of word occurrences in
    selected TEI elements (it excludes notes, cits, bibls, heads, and
    other text-bearing elements not germane to NLP processing;

  - A **ChunkIndexer** that generates indexes of chunks defined by the
    CTS citation scheme defined in the `<citeStructure>`; the indexes
    include the plain text of the chunk, the CTS URN, and the XPath to
    the chunk in the TEI document.

  - A **ReferenceParser** that implements a CTS interface to a TEI
    document. The reference parser can resolve a CTS URN into a chunk;
    generate a CTS URN for an element in the document; and it can
    generate an exhaustive list of all the CTS citations supported by
    the document. The ReferenceParser establishes a *consistent
    citation surface* for the document.
    

  These modules can be used to generate intermediate files that may be
  used by programs in the Annotation and View layers.

  The Corpus layer also contains  **Auditors** that can be used to
  inspect the milestone  and div structure and the reference structure
  and generate reports that human editors can use to discover problems
  with the encoding.

##### XSLT Modules

  - A growing collection of stylesheets that supplement the Auditors
    and can be used when cleaning up the Perseus text base
    (transitioning from EpiDoc back to Perseus schemas; generating
    `<citeStructure>` elements from existing RefsDecls and actual text
    structure; etc.

#### Annotations

The Annotations layer models the scholarly apparatus that accumulates
around encoded texts: morphological and syntactic analyses; lexical
glosses; citations linking passages in one text to passages in another;
and other forms of structured commentary.

Annotations are **stand-alone data** --- they are not embedded in the
source TEI documents. An annotation identifies the text passage it
describes (via CTS URN), specifies its type, and carries its content.
This design keeps the source texts clean and allows annotations from
different producers --- NLP pipelines, manual scholarly editing,
third-party lexica --- to coexist and be updated independently.

The Annotations layer defines:

- The data formats in which annotations are represented (JSON index
  files at present; a more principled schema is a near-term goal).
- The interfaces by which annotation producers write annotations and
  annotation consumers read them.
- The code for reading and writing annotation stores.


The annotation layer includes NLP processes and artifacts. Crucially,
the current implementation of MVP does not yet specify those
artifacts, nor how they are produced: MVP is being developed following
Agile principles, by a very small team of developers, under great time
constraints. A vital part of the next iteration of MVP development
will be defining that integration and the resolution of traditional
citations to CTS URNs, in order to implement the hypertextual linking
between texts and commentaries that is a crucial part of P4.

The codebase contains only one module in the Annotation layer so far:
a **CitationResolver** that resolves classical citation strings to CTS
URNs. (This was ported from Charles Pletcher's citation-resolution module.)

#### Site (Views)

The Site layer is responsible for generating the website. It includes
a **ProtopageCompiler** that partitions TEI texts into simplified,
intermediate XML (proto-pages) corresponding with the citation
structure described in the TEI RefsDecl element; and a
**ProtopageRenderer**, which uses Jinja templates (separately defined)
to generate HTML pages.

There is also an XSLT-based **PageCompiler**, intended to be used to
generate HTML pages from TEI documents. It is part of an earlier
processing strategy, but it is being retained for the time being.


The primary output of Minimum Viable Perseus is a **static website**: a
collection of interlinked HTML pages that can be served by a simple HTTP
server with no backend application or database. The static site
comprises:

- **Reader pages** --- individual text passages rendered as a
  three-column layout (navigation, text, annotations), chunked according
  to the document\'s structural declarations.
- **Catalog pages** --- browsable lists of available texts.


#### The Interface Between Layers

The boundary between Annotations and Views is the most important
interface in the system. At present, the Corpus layer produces **word
indexes** and **chunk indexes** --- JSON documents that give NLP tools
what they need: surface forms, positions, and anchors into the source
XML. The NLP pipeline consumes those indexes and writes annotation files
back to the annotation store. The Views compiler reads from the
annotation store when generating pages.


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
| `src/tools/run_corpus_prep.py` | Applies a corpus-prep XSLT to an entire canonicalLit corpus tree |
| `src/tools/run_index.py` | Builds `chunks.json` and `words.jsonl` index files from TEI documents |
| `src/tools/generate_html_from_tei.py` | Transforms a single TEI document to HTML via an XSLT driver |
| `src/tools/generate_protopages.py` | Step 1 of proto-page pipeline: TEI → proto-page XML (via Saxon) |
| `src/tools/render_protopages.py` | Step 2 of proto-page pipeline: proto-page XML → HTML (via Jinja2) |


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
| `html/generate_protopages.xsl` | Proto-page pipeline step 1: iterates Family-1 chapters, writes one `chunk_{book}.{chapter}.xml` + `index.json` per chapter |

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
| `mvp/site/compilers/` | Compilation package: `Compiler` ABC (`base.py`), `PageCompiler`/`XSLTCompiler` (`page_compiler.py`), `CatalogCompiler` and `copy_static_assets` (`catalog_compiler.py`), `ProtopageCompiler`/`ProtopageRenderer` (`protopage_compiler.py`) |
| `mvp/site/pipeline.py` | `BuildPipeline` — orchestrates the site build |

Each layer's public API is re-exported from its `__init__.py`.  The NLP
team's integration point is the `annotations/` layer (not `site/`).

There is also code outside the `mvp` package, under `src/tools/`.

| Script | Role |
|--------|------|
| `src/tools/run_audit.py` | Commandline script to run audits on a Perseus corpus |
| `src/tools/run_build.py` | Builds the site |
| `src/tools/run_corpus_prep.py` | Applies a corpus-prep XSLT to an entire canonicalLit corpus tree |
| `src/tools/generate_html_from_tei.py` | Transforms a single TEI document to HTML via an XSLT driver |
| `src/tools/classify_corpus.py` | Classifies corpus documents by structure type |
| `src/tools/analyze_audit.py` | Analyzes audit output reports |


There is also an implementation of a simple morphological server at
`src/morph-server`. It was developed independently by a different
developer (Peter Nadel), and should probably be incorporated into the
rest of the MVP code base; however, a case could be made for keeping
it separate, as an "external service". We do not need to decide this now, however.


### Tracking Development

Development is tracked in three places:

 - **forum.org** a local, deliberative record of research, decisions,
 and implementation notes. It is a shared space for AIs (Claude Chat,
   Claude Code) and human developers.

 - **wiki/** — Project wiki on GitHub (and in cloned local repo). Not
   always up-to-date.

- **GitHub Projects and Issues** The principal activity tracker,
shared among human developers.




The following areas are currently under active development (see
`forum.org` for the full deliberative record and current TODO items):

- **Proto-page pipeline** (branch `76-write-proto-page-compiler`, pushed, awaiting PR/merge):
  A two-step replacement for the one-step `PageCompiler`+`driver.xsl` pipeline.
  Step 1 (`ProtopageCompiler` + `generate_protopages.xsl`) transforms a Family-1 TEI
  file into per-chapter proto-page XML files plus `index.json`.  Step 2
  (`ProtopageRenderer`) renders those XML files to HTML via Jinja2.  Thucydides is
  the reference corpus (917 chapters).  See `wiki/Proto-Page-Pipeline.org` for design
  notes.  The scratchpad work in `PerseusDLCode/tei-tagger` is now mothballed; all
  further development happens here.
- **Citation infrastructure**: `ReferenceParser` is complete (merged to
  `dev`, PRs #49 and #53).  Next steps: (1) connect
  `ReferenceParser.citations()` to the XSLT chunkers for navigation-link
  generation (undesigned — see open question in `#implement-reference-parser`);
  (2) migrate corpus from `<cRefPattern>` to `<citeStructure>` (design phase).
- **XSLT modularization**: refactoring chunker stylesheets into a
  proper stylesheet family (see `#reimplement-xslt-to-be-modular`)




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

- `wiki/` — project wiki: standards, workflows, CTS URN architecture,
  chunking design. The `mvp_architecture` wiki page is required
  reading.

- `forum.org` — deliberative record: research, decisions,
  implementation notes for all significant work items
- `.claude/guidelines/` — coding conventions; read before any coding
  task
- `docs/Cayless_et_al_-_Introducing_Citation_Structures.pdf` —
  background reading for citation infrastructure work


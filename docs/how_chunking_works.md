# How chunking works

## The two-layer split

`src/mvp/site/app.py` itself does **no chunking**. It's a read-only rendering
layer over pre-computed "proto-pages" — chunking is a build-time step that
happens in `mvp.site.proto_pages.generate_proto_pages`, called once at app
startup (`app.py:66`). By the time a request hits `reading_view`, `app.py` is
just looking up an already-chunked `index.json`/`metadata.json`/chunk XML
from `PROTO_DIR` (`app.py:241-260`). So "how does the chunker decide what's
linkable" is really a question about `perseus_cts.chunker.Chunker` and
`perseus_cts.cts_resolver.CTSResolver`.

## Build-time: `proto_pages.py` → `Chunker` → `CTSResolver`

For each TEI document, `_compile_proto_page` (`proto_pages.py:26`) builds a
*list* of `(scheme_slug, Chunker)` pairs, not just one:

1. **One `Chunker` per declared `refsDecl`** — `available_refsDecl_ids(doc)`
   returns the `xml:id` of every `<refsDecl>` in the TEI header that has a
   `<citeStructure>`. A document can hand-declare more than one citation
   scheme this way (e.g. tragedy's scene-based vs. card-based `refsDecl`s —
   genuinely different match expressions, not just different depths).
2. **Plus auto-derived shallower schemes** — `auto_chunk_units(doc)` inspects
   the *default* scheme's citeStructure hierarchy and, if it's 3+ levels
   deep, adds one more scheme for free at the second-deepest level.

Each `Chunker` wraps a `CTSResolver` and calls `.chunks()`, which decides
where the citation hierarchy gets "cut" into pages.

## How `CTSResolver` picks the chunk level

The citeStructure tree in the TEI `refsDecl` is a nested hierarchy (e.g. book
→ chapter → section). `_find_chunk_cs()` (`cts_resolver.py:565`) decides
which level in that tree becomes one URL/page:

1. If a `chunk_unit` override was passed (used for the auto-derived scheme),
   find the citeStructure with that `unit`.
2. Else, look for a citeStructure explicitly marked `n="chunk"` in the TEI.
3. Else, fall back to the **penultimate** level of the deepest chain
   (`_penultimate_cs`) — one level up from the very bottom, since the bottom
   is usually individual lines/words, too fine-grained to be a page.
4. Guard: if that penultimate level resolves to `unit="line"`, raise
   `ConfigurationError` rather than silently building line-level pages.

Once the chunk-level citeStructure is found, `.chunks()` walks the tree and
yields one `CitationChunk` per matching element at that level
(`_div_chunks`) — or, for milestone-style citation (`match` containing
`"milestone"`), slices the document between consecutive milestones
(`_milestone_chunks`), which is how tragedy's card scheme works despite
having no nested `<div>`s to walk.

## Concretely: Thucydides

Thucydides' `refsDecl` (from `tests/data/tlg0003.tlg001.perseus-grc2.xml`):

```xml
<citeStructure match=".../tei:body" use="@n">
  <citeStructure unit="book" delim=":" match="tei:div[@subtype='book']" use="@n">
    <citeStructure unit="chapter" delim="." match="tei:div[@subtype='chapter']" use="@n">
      <citeStructure unit="section" delim="." match="tei:div[@subtype='section']" use="@n"/>
    </citeStructure>
  </citeStructure>
</citeStructure>
```

No `n="chunk"` anywhere, so `_find_chunk_cs` falls through to the
penultimate-of-deepest-chain rule. The deepest chain is
`[book, chapter, section]`, so the penultimate is **chapter** — that's the
default reading unit (one page per chapter, URL like `1.1`).

Then `auto_chunk_units` kicks in because the chain is 3 levels deep: since
the default chunk level (`chapter`) is `chain[-2]`, the "other" level is
`chain[-1]` = **section**. So a second `Chunker` gets built with
`chunk_unit="section"`, producing a parallel tree of section-level pages. In
`proto_pages.py`, that scheme's slug is just `"section"` (no `_scheme_slug`
mapping needed since it's not from a named `refsDecl_id`), so it compiles to
`<version>/section/index.json` and section pages live at URLs like
`/urn:cts:...:1.1.1/section/`.

That's the mechanism behind "Thucydides links both chapters and sections" —
it's not something hand-configured per-work, it's the generic
3-level-hierarchy rule (`auto_chunk_units`'s docstring explicitly calls out
Thucydides-vs-Herodotus as the motivating contrast: Herodotus' default chunk
level is the *shallower* `chapter`, so its auto scheme goes the other
direction).

There's also `section_scheme_unit`, a related but separate rule: even a
**2-level** hierarchy (e.g. tragedy's chapter/section) still gets
`"section"` exposed as its own scheme if it's not already the default —
because individual sections are always meant to be independently readable
regardless of hierarchy depth.

## Tying schemes back together for navigation

`Chunker.compile()` writes each scheme's `metadata.json` with a `toc` built
by `CTSResolver.toc(unit_scheme_map)`. `proto_pages.py:72-76` builds
`unit_scheme_map` as `{"chapter": "", "section": "section"}` (unit name →
URL slug) across *all* compiled schemes for that document, then passes it
into every scheme's own `.toc()` call. With a map present, `_toc_level` stops
truncating at the chunk level and recurses to the true leaf, stamping every
entry with its `scheme`. That's what lets the left-nav TOC on a chapter page
show clickable section links (and vice versa) — both granularities are baked
into one combined tree, and `app.py`'s `_render_nav_fragment`/
`get_nav_fragment_scheme` routes just render whichever `metadata.json` the
current URL's scheme points to.

The `/<scheme>/` URL segment in `app.py`'s routes (`reading_view_scheme`,
`get_nav_fragment_scheme`, etc.) is literally that scheme slug — `""` for
the default chunk level, `"section"` for the auto-derived one,
`"card"`/`"scene"` for tragedy's hand-declared alternates.

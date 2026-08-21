# What a TEI document needs to be included

This describes the minimum structure a TEI XML source file must have for
`Corpus.documents()`, `Chunker`, and `CTSResolver` (all in the `perseus_cts`
package) to pick it up and generate proto-pages for it. Requirements below
are grounded in `perseus_cts.models.document.TEIDocument` and
`perseus_cts.cts_resolver.CTSResolver`.

## 1. A CTS URN on `text/body/@xml:base`

```xml
<text xml:lang="grc">
  <body xml:base="urn:cts:greekLit:tlg0003.tlg001.perseus-grc2">
    ...
  </body>
</text>
```

- `body` must be the immediate child of `text`.
- `@xml:base` on `body` is the CTS URN for the *whole document* (no passage
  component). It's read via a direct XPath,
  `/tei:TEI/tei:text/tei:body/@xml:base`.
- If it's missing, `CTSResolver.__init__` raises
  `ConfigurationError("Base CTS URN not declared on tei:body/@xml:base")`,
  and the document is skipped rather than paginated
  (`proto_pages.py`'s `_compile_proto_page` catches this and reports
  `"no-schema"`).
- `TEIDocument._extract_urn` also reads this same attribute first (falling
  back to the first `div/@n` starting with `urn:cts:` if it's absent). A
  document with **no URN at all** is skipped before chunking is even
  attempted — see [[proto-dir-slash-separated-urns]] for how this URN maps
  to the on-disk proto-page path.

## 2. `text/@xml:lang`

```xml
<text xml:lang="grc">
```

- Read directly off `text` (a direct child of the TEI root, not searched
  recursively) to determine the document's main language, normalized to
  ISO 639-3 (e.g. `grc`, `lat`, `eng`) via `normalize_lang`.
- If absent, both `TEIDocument._extract_language` and
  `Chunker._build_document_metadata` fall back to
  `teiHeader//langUsage/language/@ident`. If that's also absent, language
  is recorded as `""` — not a hard failure, but it silently degrades
  catalog-title lookup (`_catalog_title` matches by language) and any
  language-dependent rendering.
- Practical rule: always set `xml:lang` on `text`, not just deeper inside
  the document (e.g. only on `titleStmt/title`).

## 3. `refsDecl[@xml:id="CTS"]` with a nested `citeStructure`

```xml
<encodingDesc>
  <refsDecl xml:id="CTS">
    <citeStructure match="/TEI/text/body" use="@n">
      <citeStructure unit="book" delim=":" match="div[@subtype='book']" use="@n">
        <citeStructure unit="chapter" delim="." match="div[@subtype='chapter']" use="@n">
          <citeStructure unit="section" delim="." match="div[@subtype='section']" use="@n"/>
        </citeStructure>
      </citeStructure>
    </citeStructure>
  </refsDecl>
</encodingDesc>
```

- `CTS` is the default `refsDecl_id` `CTSResolver` and `Chunker` look for
  (`CTSResolver(tei_doc, refsDecl_id="CTS")` by default). This is the
  **modern TEI `citeStructure` form**, not the older CapiTainS-style
  `<refsDecl n="CTS"><cRefPattern .../></refsDecl>`, which this codebase
  does not parse for chunking.
- Write bare, unprefixed element names in `@match` (`div`, not `tei:div`).
  `CTSResolver` prefixes every bare element name in a `@match` expression
  to the document's own namespace automatically
  (`_prefix_match_expr`/`_BARE_ELEMENT`); writing `tei:div` yourself would
  get double-prefixed and fail to match.
- `available_refsDecl_ids(doc)` finds every `refsDecl` that has both
  `@xml:id` and a nested `citeStructure`; a document with **none** produces
  an empty `compilers` list and is reported as `"no-schema"` — it parses
  fine and shows up in the corpus listing, but no reading pages are
  generated for it.
- A document may declare **more than one** `refsDecl`/`citeStructure`
  scheme this way (e.g. tragedy's `CTS-scene` vs. `CTS-card`) to expose
  alternate citation/chunking granularities — see
  `docs/how_chunking_works.md` for how these compile into
  `<scheme-slug>/` subdirectories.

### citeStructure rules enforced by `CTSResolver`

- The outermost `citeStructure` (matching the body) is a pure wrapper —
  its own `@delim`, if given at all, must be `":"` (the CTS passage
  separator), enforced at `CTSResolver.__init__`. Its **children** are the
  actual hierarchy levels (book, chapter, section, ...).
- Every citeStructure level actually used to build a URN must declare
  `@delim` (e.g. `delim=":"` for the first level under the body,
  `delim="."` for each level below that). A level missing `@delim` raises
  `ConfigurationError` the first time a URN is generated for an element
  under it.
- `@unit` names the citation level (`book`, `chapter`, `section`, ...) and
  is what `chunk_unit` overrides and TOC/scheme-slug logic key off of.
- `@match` is an XPath (bare element names, auto-prefixed to the
  document's own namespace) selecting the elements at that level; `@use`
  (default `"@n"`) extracts each element's citation value — either an
  `@attr` shorthand or an arbitrary XPath.
- Citation can also be **milestone-based** (`@match` containing
  `"milestone"`) instead of `<div>`-nested, for documents that mark
  boundaries with empty milestone elements rather than wrapping divs.

### Picking the chunk (page) level

`CTSResolver` decides which citeStructure level becomes one page/URL,
in this order:

1. An explicit `chunk_unit` override (used internally for auto-derived
   schemes).
2. A citeStructure marked `n="chunk"` in the TEI.
3. Otherwise, the **penultimate** level of the deepest citeStructure chain
   (one level up from the bottom, since the bottom is usually
   individual lines — too fine-grained for a page).
4. If that penultimate level resolves to `unit="line"`, `ConfigurationError`
   is raised rather than silently building line-level pages.

If your hierarchy is 3+ levels deep, an additional scheme is generated for
free at the next level down (`auto_chunk_units`) — you don't need to
hand-declare a second `refsDecl` just to expose that.

## Summary checklist

- [ ] `<text xml:lang="XXX">` — main language of the document, ISO 639-1
      or 639-3.
- [ ] `<body xml:base="urn:cts:...">` as the immediate child of `text` —
      the document's own CTS URN, no passage component.
- [ ] `<refsDecl xml:id="CTS">` in `teiHeader/encodingDesc` containing a
      nested `<citeStructure>` tree, with unprefixed element names in
      `@match`.
- [ ] Every non-wrapper `citeStructure` level has `@delim` and `@unit`.
- [ ] The outermost (wrapper) `citeStructure`'s `@delim`, if present, is
      `":"`.
- [ ] The citation hierarchy is deep enough that the penultimate level
      isn't `unit="line"` (or mark the intended page level explicitly with
      `n="chunk"`).

A document missing the URN or the `citeStructure` entirely doesn't crash
the build — it's just skipped (`"no-schema"`/no manifest written), so it's
safe to add partially-encoded texts to a corpus; they simply won't produce
reading pages until the citation scheme is filled in.

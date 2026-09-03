---
title: Variable-depth leaf nodes in citation chunking
date: 2026-09-03
status: implemented
updated: 2026-09-03
---

# Variable-depth leaf nodes in citation chunking

## Problem

`perseus-cts`'s `CTSResolver` assumes a work's citeStructure hierarchy is
uniformly deep everywhere it's declared: pick one target level (e.g.
"chapter" for Livy's book/chapter/section scheme) and walk the whole tree to
that level, recursing into any node whose citeStructure schema declares
children.

Some works don't nest uniformly. Livy's
`corpora/canonical-latinLit/data/phi0914/phi001/phi0914.phi001.perseus-lat2.xml`
declares book → chapter → section throughout, and most books (`n="1"`...`"45"`)
do have `chapter`/`section` descendants — but the periochae (summary
"books", `n="1s"`...`"45s"`, `n="46"`...`"142"`, 132 of 177 book-level divs
in this file) sit at the same tree depth with only a `<head>`/`<p>` directly
inside them, no `chapter`/`section` subdivisions at all.

The current traversal (`_collect_cs_elements` in
`perseus_cts/cts_resolver.py`) recurses into a node's *declared* child
citeStructure unconditionally whenever `node.children` is non-empty,
regardless of whether that specific element actually has any matching
descendants. For a periocha book, the recursion finds zero `chapter`
candidates and contributes nothing — the book vanishes from `chunks()`
entirely. Confirmed empirically: `CTSResolver(doc).chunks()` on this file
yields 1765 chunks, none of them for any periocha.

This isn't Livy-specific. A grep across `canonical-latinLit` (908 files) and
`canonical-greekLit` (2538 files) for book-level divs with no nested chapter
div found 66 and 69 files respectively with the same shape — e.g. Ovid's
*Ars Amatoria* (`phi0959/phi001` etc.), Galen's *On the Natural Faculties*
(`tlg0057/tlg010`), Plato's *Republic* (`tlg0059/tlg030`), Quintus
Smyrnaeus (`tlg2046/tlg001`), the *Greek Anthology* (`tlg7000/tlg001`).
`First1KGreek`, `canonical-engLit`, and the other corpora under
`corpora/` weren't scanned but are plausible candidates for the same
pattern.

## Where this lives (not in MVP)

The fix belongs entirely in `perseus-cts`
(`/Users/pletcher/code/PerseusCode/perseus-cts/src/perseus_cts/`), not in
MinimumViablePerseus's `src/mvp/site/`. MVP's own citation-handling code
(`mvp/site/chunks.py`'s `_chunk_start_line`/`_chunk_distance`, `mvp/site/toc.py`'s
recursive TOC walk) is already depth-agnostic — dotted citation components
become variable-length tuples, zero-padded for comparison, specifically to
tolerate "citation keys of differing depth ... between sibling versions"
(`chunks.py:376-379`). MVP shouldn't need functional changes beyond one
`unit_scheme_map` construction fix in `proto_pages.py` (see Step 3).

## Plan

### Step 1 — leaf-fallback in the traversal (`cts_resolver.py`)

`_walk_cs`'s shared traversal primitive (used by `_collect_cs_elements`,
`_records_recursive`, `_toc_level`, `_find_milestone_parents`) yields one
`_CSNode` per matched element at a level, carrying that level's declared
`children` citeStructure list. The fix is the same shape everywhere it's
needed: when recursing into a node's declared children produces nothing,
treat the node itself as a leaf chunk at its own (shallower) unit instead
of silently dropping it.

Concretely, in `_collect_cs_elements` (`cts_resolver.py:1110-1124`):
compare `len(result)` before and after the recursive call; if unchanged,
append `(node.element, self._base_urn + node.suffix, node.unit)` as a
fallback. This requires widening `_candidates_at_level`/
`_collect_cs_elements`'s result shape from `(element, urn)` to
`(element, urn, unit)` pairs, since a fallback leaf's real unit (e.g.
"book") differs from the target citeStructure's unit (e.g. "chapter").
`_div_chunks` then yields each `CitationChunk` with its own per-pair unit
rather than one `unit = target_cs.get("unit", "")` for every chunk.
`CitationChunk.unit` is already a per-instance field
(`models/core.py:69`), so no schema change is needed there.

The same fallback is added to `_toc_level` (`cts_resolver.py:661-747`) so
a leaf book gets a real TOC entry instead of either vanishing or (in the
`unit_scheme_map`-present case already used by every real build) appearing
as an unclickable orphan whose URN has no backing chunk file.

### Step 2 — a `target_unit` property, used to fix the `chunk_unit` metadata assumption

`Chunker.compile` writes `metadata.json["chunk_unit"]` as
`self.citation_chunks[0].unit` (`chunker.py:86`) — the *first* chunk's
unit, standing in for "the granularity this scheme reads at". Once
individual chunks can carry different units (Step 1), that's fragile: if
a periocha happens to be document-order-first, the whole scheme's
metadata would misreport "book" instead of "chapter". `mvp/site/proto_pages.py`
builds an analogous `unit_scheme_map` (`proto_pages.py:112-116`) the same
fragile way, keyed off `compiler.citation_chunks[0].unit`.

Fix: add a `target_unit` property to `CTSResolver` —
`self._find_chunk_cs().get("unit", "")` — which reports the citeStructure
level this resolver was actually configured to chunk at (explicit
`n="chunk"`, override, or the penultimate-level default), independent of
any individual chunk's leaf-fallback unit. Use it in both places instead
of `citation_chunks[0].unit`. This also cleanly resolves TOC labeling
(`mvp/site/toc.py:124`'s `"By {chunk_unit.capitalize()}"`) for free — "By
Chapter" remains an accurate description of the scheme as a whole even
though a handful of its entries are book-level leaves; those leaves are
already visually distinguished in the TOC tree by their own
`subtype="book"`. No separate "mixed units" label handling is needed.

### Step 3 — MVP-side: one line in `proto_pages.py`

Replace `proto_pages.py:112-116`'s
`compiler.citation_chunks[0].unit: scheme` dict-comprehension key with
`compiler.cts_resolver.target_unit: scheme`. No other MVP change is
required: `mvp/site/toc.py::_annotate_toc` already links any TOC entry
carrying a non-`None` `"scheme"` key (`toc.py:42-50`), and once
`_toc_level`'s fallback (Step 1) stamps a leaf entry with
`unit_scheme_map.get(self.target_unit)` — the *resolver's own* scheme,
not the leaf's own "book" unit — that resolves to a real, valid scheme
slug (`""` for the default reading view, `"section"` for the auto-derived
section scheme, etc.), so the periocha book becomes clickable under every
scheme that would otherwise have silently dropped it.

## Cross-edition alignment (sibling passages)

Handled gracefully even without changes — degradation, not breakage —
and now improved. `mvp/site/siblings.py`'s `_build_sibling_data` never
crashes when one edition has a leaf book and a sibling edition
(translation, different print edition) is chaptered normally: Strategy 1
("in-range") couldn't originally match a leaf book's single-component
citation tuple against a chaptered sibling's deeper tuples (`(5,) <=
(5,1)` is true but never the reverse, so no chaptered start ever fell "in
range" of a leaf end), so it always fell through to Strategy 2,
`_find_nearest_chunk` (`chunks.py:390-408`), whose `_chunk_distance`
(`chunks.py:374-387`) explicitly zero-pads shorter tuples before
comparing. The practical effect was a UX degradation: a reader on a
leaf-level periocha saw only the chaptered sibling's *first chapter* of
the corresponding book, not the sibling's whole book.

**Update (2026-09-03, same day):** fixed. `_starts_within_range`
(`siblings.py`, new) extends Strategy 1's in-range test: when the base
chunk's own citation is a single point (`current_line == current_end` —
true both for a leaf-fallback chunk and, incidentally, for any ordinary
non-milestone chunk, since those already cite a single div rather than a
line range) and a sibling start shares that citation as a leading prefix,
it now counts as "in range" too. Every such sibling chunk is collected
and merged via the existing `_merge_sibling_chunks`, so a reader on
Livy's periocha for book 5 now sees the chaptered sibling's *entire* book
5, not just chapter 5.1. Ordinary same-depth siblings are unaffected —
the new branch only fires when the plain tuple comparison already failed
and depths genuinely differ. Covered by
`tests/test_sibling_focus_url.py::TestBuildSiblingDataLeafBaseAlignment`.

## Verification

Given the ~135-file blast radius, test against at least three
structurally distinct cases before considering this done:

- Livy (`phi0914.phi001.perseus-lat2.xml`) — periochae summary books.
- Ovid's *Ars Amatoria* (`phi0959/phi001`) — different author/genre, same
  missing-chapter-division shape.
- Plato's *Republic* (`tlg0059/tlg030`) — Greek, dialogue structure.

"""Abbreviation lookup: the human-browsable help page and the JSON index
that powers the "jump to a citation" search box (Perseus/MVP#169).

Both are built from the same filtered view of the citation_resolution
gazetteer: only textgroups/works this build actually has an edition for
(per urn-index.json) are included, so neither surface ever links to or
offers to resolve a passage the site can't render.
"""

from __future__ import annotations

import json

from mvp.site import config
from mvp.site.catalog_tree import _group_name, _work_title

# Prefer a source-language edition over a translation when jumping to a
# work, per issue #169: "look for a perseus-grc/lat edition ... provide a
# source text as focus". Falls through to whatever's available.
_LANGUAGE_PREFERENCE = ("grc", "lat")


def _version_sort_key(version: dict) -> tuple:
    """Order a work's versions source-language-first (see
    _LANGUAGE_PREFERENCE), then other non-English languages, then English
    last -- the order a popover of editions should list them in.
    """
    lang = version["language"]
    if lang in _LANGUAGE_PREFERENCE:
        return (0, _LANGUAGE_PREFERENCE.index(lang), version["label"])
    if lang == "eng":
        return (2, lang, version["label"])
    return (1, lang, version["label"])


def _load_gazetteer() -> dict:
    with open(config.GAZETTEER_PATH, encoding="utf-8") as f:
        return json.load(f)


def _build_citation_index(
    gazetteer: dict, urn_index: dict[str, list[dict]], catalog
) -> dict:
    """Filter the gazetteer to textgroups/works with an available edition.

    Shape (per textgroup URN):
        {
          "name": "Sophocles",
          "name_abbrevs": ["Soph.", "S."],
          "default_work_urn": "urn:cts:greekLit:tlg0011.tlg003" | null,
          "works": {
            "urn:cts:greekLit:tlg0011.tlg003": {
              "title": "Ajax", "title_abbrevs": ["Aj."], "scheme": "line"
            }
          }
        }

    `default_work` in the source gazetteer is a title_abbrev string (the
    key a bare author-only citation should resolve to); it's resolved here
    to a work URN so the client doesn't need to redo that lookup.
    """
    index: dict = {}

    for tg_urn, rec in gazetteer.items():
        if tg_urn.startswith("urn:cts:cwkb:"):
            # HuCit assigns some authors a second, cwkb-namespaced identity
            # alongside their real textgroup URN, sometimes pointing at the
            # *same* (real, routable) work URNs as the proper entry -- e.g.
            # Caesar exists as both urn:cts:cwkb:408 and
            # urn:cts:latinLit:phi0448. cwkb is never itself a corpus this
            # site serves, so it can only ever duplicate a proper entry
            # here, not add a reachable one; skip it to avoid a bare "Caes."
            # spuriously resolving as ambiguous between "Caesar" and itself.
            continue
        name_abbrevs = rec.get("name_abbrevs") or []
        if not name_abbrevs:
            continue

        works: dict = {}
        for work_urn, w in rec.get("works", {}).items():
            if work_urn not in urn_index:
                continue
            works[work_urn] = {
                "title": _work_title(catalog, work_urn, work_urn.rsplit(".", 1)[-1]),
                "title_abbrevs": w.get("title_abbrevs") or [],
                "scheme": w.get("scheme", "flat"),
            }
        if not works:
            continue

        default_work_abbrev = rec.get("default_work")
        default_work_urn = None
        if default_work_abbrev:
            for work_urn, w in works.items():
                if default_work_abbrev in w["title_abbrevs"]:
                    default_work_urn = work_urn
                    break

        index[tg_urn] = {
            "name": _group_name(catalog, tg_urn, tg_urn.rsplit(":", 1)[-1]),
            "name_abbrevs": name_abbrevs,
            "default_work_urn": default_work_urn,
            "works": works,
        }

    return index


def _build_abbreviation_page_entries(
    citation_index: dict, urn_index: dict[str, list[dict]]
) -> list[dict]:
    """Flatten the citation index into rows for the /abbreviations/ page,
    sorted by author display name. Each work carries every available
    version (source-language-first, see _version_sort_key), each with
    route_kwargs for url_for("get_first_chunk", **route_kwargs), so the
    template can offer a reader every edition that resolves rather than
    silently picking one.
    """
    entries = []
    for rec in citation_index.values():
        works = []
        for work_urn, w in rec["works"].items():
            versions = sorted(urn_index.get(work_urn, []), key=_version_sort_key)
            works.append(
                {
                    "title": w["title"],
                    "title_abbrevs": w["title_abbrevs"],
                    "scheme": w["scheme"],
                    "work_urn": work_urn,
                    "is_default": work_urn == rec["default_work_urn"],
                    "versions": versions,
                }
            )
        works.sort(key=lambda w: w["title"])
        entries.append(
            {
                "name": rec["name"],
                "name_abbrevs": rec["name_abbrevs"],
                "works": works,
            }
        )
    entries.sort(key=lambda e: e["name"])
    return entries

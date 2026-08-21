"""Abbreviation lookup: the human-browsable help page and the JSON index
that powers the "jump to a citation" search box (Perseus/MVP#169).

Both are built from the same filtered view of the citation_resolution
gazetteer: only textgroups/works this build actually has an edition for
(per urn-index.json) are included, so neither surface ever links to or
offers to resolve a passage the site can't render.
"""

from __future__ import annotations

import json
import re

from mvp.site import config
from mvp.site.catalog_tree import _group_name, _work_title

# Prefer a source-language edition over a translation when jumping to a
# work, per issue #169: "look for a perseus-grc/lat edition ... provide a
# source text as focus". Falls through to whatever's available.
_LANGUAGE_PREFERENCE = ("grc", "lat")

_URL_PREFIX_RE = re.compile(r"^/([^:]+):([^.]+)\.([^.]+)\.(.+)$")


def _pick_language(versions: dict[str, str]) -> str | None:
    """Pick which language's edition to link to for a work, given
    urn-index.json's {language: url_prefix} map for that work.
    """
    for lang in _LANGUAGE_PREFERENCE:
        if lang in versions:
            return lang
    if not versions:
        return None
    non_eng = [lang_ for lang_ in versions if lang_ != "eng"]
    if non_eng:
        return min(non_eng)
    return min(versions)


def _parse_url_prefix(prefix: str) -> dict[str, str] | None:
    """Split a urn-index.json url_prefix ("/greekLit:tlg0011.tlg003.perseus-grc2")
    into get_first_chunk's route kwargs."""
    m = _URL_PREFIX_RE.match(prefix)
    if not m:
        return None
    corpus, textgroup, work, version = m.groups()
    return {"corpus": corpus, "textgroup": textgroup, "work": work, "version": version}


def _load_gazetteer() -> dict:
    with open(config.GAZETTEER_PATH, encoding="utf-8") as f:
        return json.load(f)


def _build_citation_index(
    gazetteer: dict, urn_index: dict[str, dict[str, str]], catalog
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
    citation_index: dict, urn_index: dict[str, dict[str, str]]
) -> list[dict]:
    """Flatten the citation index into rows for the /abbreviations/ page,
    sorted by author display name. Each work carries route_kwargs for
    url_for("get_first_chunk", **route_kwargs), pointing at the preferred
    (source-language-first) edition, or None if the work's editions aren't
    parseable route prefixes.
    """
    entries = []
    for rec in citation_index.values():
        works = []
        for work_urn, w in rec["works"].items():
            versions = urn_index.get(work_urn, {})
            lang = _pick_language(versions)
            route_kwargs = _parse_url_prefix(versions[lang]) if lang else None
            works.append(
                {
                    "title": w["title"],
                    "title_abbrevs": w["title_abbrevs"],
                    "scheme": w["scheme"],
                    "work_urn": work_urn,
                    "is_default": work_urn == rec["default_work_urn"],
                    "route_kwargs": route_kwargs,
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

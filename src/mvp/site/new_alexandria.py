"""Read and match "New Alexandria Commentaries" against a displayed passage.

New Alexandria Commentaries are curated, attributed Markdown commentaries
pulled from opencommentaries.org (see src/tools/fetch_new_alexandria.py),
kept in their native Markdown rather than converted to TEI/CTS XML. This
module reads the already-fetched local directory tree (built by that
script), parses each file, and answers "what entries overlap this
passage" — a Markdown-native counterpart to
perseus_cts.commentary.links_for_passage, which does the same job for the
site's TEI-based commentary apparatus.

Despite differing frontmatter across the three sources, every entry in all
of them opens with a standalone `@urn:cts:<workurn>:<citation>` line
carrying the full work URN + citation, which is all this module needs for
alignment.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import markdown
import yaml
from perseus_cts.commentary import ranges_overlap

_FRONTMATTER_RE = re.compile(r"\A---\n(.*?)\n---\n?", re.DOTALL)
_ENTRY_SPLIT_RE = re.compile(r"\n-{3,}\n")
_HEADING_RE = re.compile(r"^#+\s+(.*)$")
_ANCHOR_RE = re.compile(r"^@(urn:cts:\S+)$")
_METADATA_RE = re.compile(r"^:(\w+):\s*(.*)$")

# Root-relative asset paths (e.g. Pausanias's <img src="/commentaries/...">)
# resolve against opencommentaries.org, not this site, so they need
# rewriting to an absolute URL before rendering.
_ROOT_RELATIVE_SRC_RE = re.compile(r'(src=")(/[^"]*)(")')


@dataclass(frozen=True)
class _Source:
    """One hard-coded, curated New Alexandria Commentaries source.

    `dir_path` is a flat GitHub directory of `.md` files (no recursive
    walk needed for any of the three sources today).
    """

    repo: str
    dir_path: str
    site_base_url: str


SOURCES: tuple[_Source, ...] = (
    _Source(
        repo="Open-Commentaries/pausanias.opencommentaries.org",
        dir_path="static/commentaries",
        site_base_url="https://pausanias.opencommentaries.org",
    ),
    _Source(
        repo="Open-Commentaries/homer.opencommentaries.org",
        dir_path="commentary",
        site_base_url="https://homer.opencommentaries.org",
    ),
    _Source(
        repo="Open-Commentaries/pindar.opencommentaries.org",
        dir_path="priv/static/commentary",
        site_base_url="https://pindar.opencommentaries.org",
    ),
)


@dataclass
class NewAlexandriaEntry:
    """One commentary entry, anchored to a CTS work URN + citation range."""

    work_urn: str
    citation: str
    authors: list[str]
    body_html: str
    section: str | None = None
    metadata: dict[str, str] = field(default_factory=dict)
    source_label: str = ""
    source_url: str | None = None


@dataclass
class NewAlexandriaGroup:
    """Entries for one passage, grouped by author byline for rendering."""

    label: str
    entries: list[NewAlexandriaEntry]


def _split_frontmatter(text: str) -> tuple[dict, str]:
    """Split a New Alexandria Markdown file into (frontmatter, body).

    Only the file's very first `---`...`---` block is treated as
    frontmatter (the regex is anchored to the start of the string) — later
    standalone `---` lines are entry separators, not a second frontmatter
    block. The Pausanias source in particular has a `---` immediately
    after its first `## Scroll` heading, right before its first entry.
    """
    match = _FRONTMATTER_RE.match(text)
    if not match:
        return {}, text
    frontmatter = yaml.safe_load(match.group(1)) or {}
    return frontmatter, text[match.end() :]


def _authors_from_frontmatter(frontmatter: dict) -> list[str]:
    authors = frontmatter.get("authors")
    if isinstance(authors, list):
        return [str(author) for author in authors]
    author = frontmatter.get("author")
    return [str(author)] if author else []


def _rewrite_image_urls(markdown_text: str, site_base_url: str) -> str:
    return _ROOT_RELATIVE_SRC_RE.sub(rf"\1{site_base_url}\2\3", markdown_text)


def _render_body(comment_text: str, source: _Source) -> str:
    return markdown.markdown(_rewrite_image_urls(comment_text, source.site_base_url))


def _parse_entries(
    body: str, authors: list[str], source: _Source, source_label: str
) -> list[NewAlexandriaEntry]:
    """Split a file's body into commentary entries.

    Every source separates entries with a standalone `---` line, including
    Pausanias's leading `## Scroll ...` chunk (heading-only, no anchor —
    tracked as `section` context for the entries that follow, not emitted
    as an entry itself).
    """
    entries: list[NewAlexandriaEntry] = []
    section: str | None = None

    for raw_chunk in _ENTRY_SPLIT_RE.split(f"\n{body}\n"):
        chunk = raw_chunk.strip("\n")
        if not chunk.strip():
            continue

        first_line, _, rest = chunk.partition("\n")
        first_line = first_line.strip()

        heading_match = _HEADING_RE.match(first_line)
        if heading_match:
            section = heading_match.group(1).strip()
            continue

        anchor_match = _ANCHOR_RE.match(first_line)
        if not anchor_match:
            continue

        work_urn, _, citation = anchor_match.group(1).rpartition(":")
        if not work_urn:
            continue

        metadata: dict[str, str] = {}
        body_lines = rest.splitlines()
        idx = 0
        while idx < len(body_lines):
            line = body_lines[idx].strip()
            if not line:
                idx += 1
                continue
            meta_match = _METADATA_RE.match(line)
            if not meta_match:
                break
            metadata[meta_match.group(1)] = meta_match.group(2).strip()
            idx += 1

        comment_text = "\n".join(body_lines[idx:]).strip()

        entries.append(
            NewAlexandriaEntry(
                work_urn=work_urn,
                citation=citation,
                authors=authors,
                body_html=_render_body(comment_text, source),
                section=section,
                metadata=metadata,
                source_label=source_label,
                source_url=source.site_base_url,
            )
        )

    return entries


def _urns_overlap(a: str, b: str) -> bool:
    return a.startswith(b) or b.startswith(a)


def _build_new_alexandria_groups(
    entries: list[NewAlexandriaEntry],
) -> list[NewAlexandriaGroup]:
    groups: dict[str, NewAlexandriaGroup] = {}
    for entry in entries:
        label = ", ".join(entry.authors) or entry.source_label
        group = groups.setdefault(label, NewAlexandriaGroup(label=label, entries=[]))
        group.entries.append(entry)
    return list(groups.values())


@dataclass
class NewAlexandriaIndex:
    """All parsed New Alexandria entries, queryable by passage."""

    entries: list[NewAlexandriaEntry] = field(default_factory=list)

    def entries_for_passage(
        self, work_urn: str, citation: str
    ) -> list[NewAlexandriaGroup]:
        matches = [
            entry
            for entry in self.entries
            if _urns_overlap(entry.work_urn, work_urn)
            and ranges_overlap(entry.citation, citation)
        ]
        return _build_new_alexandria_groups(matches)


def _parse_file(path: Path, source: _Source) -> list[NewAlexandriaEntry]:
    text = path.read_text(encoding="utf-8")
    frontmatter, body = _split_frontmatter(text)
    authors = _authors_from_frontmatter(frontmatter)
    source_label = str(frontmatter.get("shortname") or path.stem)
    return _parse_entries(body, authors, source, source_label)


def build_new_alexandria_index(new_alexandria_dir: Path | None) -> NewAlexandriaIndex:
    """Load and parse all fetched New Alexandria Markdown files.

    Returns an empty index if `new_alexandria_dir` is unset or missing —
    reading views render fine without New Alexandria data, same as
    mvp.site.config.TOKENS_DIR.
    """
    if new_alexandria_dir is None or not new_alexandria_dir.is_dir():
        return NewAlexandriaIndex()

    entries: list[NewAlexandriaEntry] = []
    for source in SOURCES:
        repo_dir = new_alexandria_dir / source.repo.rsplit("/", 1)[-1]
        if not repo_dir.is_dir():
            continue
        for md_path in sorted(repo_dir.glob("*.md")):
            entries.extend(_parse_file(md_path, source))

    return NewAlexandriaIndex(entries=entries)

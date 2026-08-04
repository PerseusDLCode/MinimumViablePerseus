"""Building and reassembling manifest.json for split (per-corpus) builds."""

import json
from datetime import UTC, datetime
from pathlib import Path

from flask import Flask, url_for
from perseus_cts.models import CTSCatalog

from mvp.site.catalog_tree import (
    _build_collections,
    _build_urn_index,
    _merge_collections,
)

# Bump when the manifest.json shape below changes incompatibly, so a global
# build can refuse to merge manifests it doesn't know how to read instead of
# silently mis-rendering.
_MANIFEST_SCHEMA_VERSION = 2


def _build_corpus_manifest(
    app: Flask, proto_dir: Path, catalog: CTSCatalog, source_digest: str
) -> dict:
    """Build one build's manifest.json payload for a `--mode corpus-only` build.

    Deliberately not "one corpus's manifest": a single corpus-only build's
    proto-page tree can itself span more than one CTS namespace (see
    _merge_collections), so this carries the *full* _build_collections()
    result — however many namespaces it contains — rather than assuming
    exactly one. A --mode global-only build reassembles these via
    _merge_manifests. Each version's first_chunk_kwargs is resolved to a
    concrete href via url_for here — the global build has no Flask app of
    its own and can't resolve them. url_for needs a request context, which
    a build process never otherwise has, hence test_request_context().
    """
    collections = _build_collections(proto_dir, catalog)

    with app.test_request_context():
        for corpus in collections:
            for textgroup in corpus["textgroups"]:
                for work in textgroup["works"]:
                    for version in work["versions"]:
                        kwargs = version.pop("first_chunk_kwargs")
                        version["href"] = url_for("reading_view", **kwargs)

    return {
        "schema_version": _MANIFEST_SCHEMA_VERSION,
        "built_at": datetime.now(UTC).isoformat(),
        "source_digest": source_digest,
        "collections": collections,
        "urn_index": _build_urn_index(proto_dir),
    }


def _merge_manifests(
    manifest_paths: list[Path],
) -> tuple[list[dict], dict[str, dict[str, str]]]:
    """Reassemble the global collections tree and URN index for a `--mode global-only` build.

    urn_index keys embed their corpus namespace (see _build_urn_index), so a
    plain dict union across manifests can't collide the way collections can
    (see _merge_collections) — but a work_urn's language->prefix mapping
    could theoretically be contributed by more than one manifest, so this
    still merges per-key rather than blindly overwriting.
    """
    all_collections: list[list[dict]] = []
    urn_index: dict[str, dict[str, str]] = {}

    for path in manifest_paths:
        with open(path, encoding="utf-8") as f:
            manifest = json.load(f)

        if manifest.get("schema_version") != _MANIFEST_SCHEMA_VERSION:
            raise ValueError(
                f"{path}: manifest schema_version {manifest.get('schema_version')!r} "
                f"!= expected {_MANIFEST_SCHEMA_VERSION!r}"
            )

        all_collections.append(manifest["collections"])
        for work_urn, versions in manifest["urn_index"].items():
            urn_index.setdefault(work_urn, {}).update(versions)

    collections = _merge_collections(all_collections)

    return collections, urn_index

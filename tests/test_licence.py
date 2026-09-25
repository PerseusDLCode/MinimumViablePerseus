# tests/test_licence.py
#
# Tests for how the reading page decides which licence a text is under: the
# TEI header's own <licence> first, else its source repo's declared licence
# (config._SOURCE_LICENCES), else none at all -- never a hardcoded default.

from __future__ import annotations

import json
from pathlib import Path

from perseus_cts.models import Corpus

from mvp.site import config
from mvp.site.chunks import _resolve_licence
from mvp.site.proto_pages import _record_source_repo, _source_repo

TEI_LICENCE = {
    "text": "Public domain (U.S.)",
    "target": "https://www.hathitrust.org/rights/public-domain",
}


class TestResolveLicence:
    def test_tei_licence_wins_over_source_repo(self):
        document = {
            "publication": {"licence": TEI_LICENCE},
            "source_repo": "canonical-greekLit",
        }
        assert _resolve_licence(document) == TEI_LICENCE

    def test_falls_back_to_source_repo(self):
        document = {
            "publication": {"licence": None},
            "source_repo": "Notre-Dame-Digitized-Latin-Collection",
        }
        assert _resolve_licence(document)["target"] == (
            "https://creativecommons.org/licenses/by-nc-sa/4.0/"
        )

    def test_availability_text_wins_over_source_repo(self):
        document = {
            "publication": {"licence": None, "availability": "Public Domain"},
            "source_repo": "canonical-greekLit",
        }
        assert _resolve_licence(document) == {"text": "Public Domain", "target": ""}

    def test_unlicensed_repo_makes_no_claim(self):
        document = {"publication": {"licence": None}, "source_repo": "canonical-engLit"}
        assert _resolve_licence(document) is None

    def test_legacy_metadata_makes_no_claim(self):
        # metadata.json compiled before publication/source_repo were recorded.
        assert _resolve_licence({}) is None

    def test_every_licensed_repo_has_text_and_target(self):
        for licence in config._SOURCE_LICENCES.values():
            assert licence["text"] and licence["target"]


class TestSourceRepo:
    def test_repo_with_data_dir(self, tmp_path: Path):
        root = tmp_path / "canonical-greekLit" / "data"
        root.mkdir(parents=True)
        assert _source_repo(Corpus(root)) == "canonical-greekLit"

    def test_repo_without_data_dir(self, tmp_path: Path):
        root = tmp_path / "ajmc-tei"
        root.mkdir()
        assert _source_repo(Corpus(root)) == "ajmc-tei"

    def test_record_source_repo_preserves_metadata(self, tmp_path: Path):
        path = tmp_path / "metadata.json"
        path.write_text(json.dumps({"version": "1", "document": {"title": "Ἰλιάς"}}))
        _record_source_repo(path, "canonical-greekLit")
        metadata = json.loads(path.read_text(encoding="utf-8"))
        assert metadata["version"] == "1"
        assert metadata["document"] == {
            "title": "Ἰλιάς",
            "source_repo": "canonical-greekLit",
        }

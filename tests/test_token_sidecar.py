# tests/test_token_sidecar.py
#
# _load_token_sidecar resolves a chunk's token data from one of three
# places, in priority order: the external TOKENS_DIR tree (compressed,
# mirroring PROTO_DIR's layout), a co-located compressed sidecar (local
# `run_tokenizer.py` runs against proto-pages directly), or a legacy
# co-located uncompressed .tokens.json (pre-compression checkouts). Each
# candidate is decompressed independently and on demand -- never as part
# of a bulk archive -- so a build never has to materialize the full token
# tree on disk to render one chunk.

from __future__ import annotations

import json

import pytest
import zstandard

from mvp.site import chunks as chunksmod
from mvp.site import config

TOKENS_PAYLOAD = {
    "urn": "urn:cts:latinLit:phi1017.phi007.perseus-lat2:57",
    "tokens": [{"text": "foo"}],
}


def _zst(payload: dict) -> bytes:
    return zstandard.ZstdCompressor(level=3).compress(
        json.dumps(payload).encode("utf-8")
    )


@pytest.fixture
def proto_dir(tmp_path, monkeypatch):
    d = tmp_path / "proto-pages" / "latinLit" / "phi1017" / "phi007" / "perseus-lat2"
    d.mkdir(parents=True)
    monkeypatch.setattr(config, "PROTO_DIR", tmp_path / "proto-pages")
    return d


class TestNoSidecar:
    def test_returns_none_when_nothing_exists(self, proto_dir, monkeypatch):
        monkeypatch.setattr(config, "TOKENS_DIR", None)
        chunk = proto_dir / "57.xml"
        chunk.write_text("<x/>")
        assert chunksmod._load_token_sidecar(chunk) is None


class TestCoLocatedSidecar:
    def test_reads_compressed_co_located_sidecar(self, proto_dir, monkeypatch):
        monkeypatch.setattr(config, "TOKENS_DIR", None)
        chunk = proto_dir / "57.xml"
        chunk.write_text("<x/>")
        (proto_dir / "57.tokens.json.zst").write_bytes(_zst(TOKENS_PAYLOAD))

        result = chunksmod._load_token_sidecar(chunk)
        assert result == TOKENS_PAYLOAD

    def test_reads_legacy_uncompressed_sidecar(self, proto_dir, monkeypatch):
        monkeypatch.setattr(config, "TOKENS_DIR", None)
        chunk = proto_dir / "57.xml"
        chunk.write_text("<x/>")
        (proto_dir / "57.tokens.json").write_text(json.dumps(TOKENS_PAYLOAD))

        result = chunksmod._load_token_sidecar(chunk)
        assert result == TOKENS_PAYLOAD


class TestExternalTokensDir:
    def test_reads_from_tokens_dir_mirroring_proto_dir_layout(
        self, tmp_path, proto_dir, monkeypatch
    ):
        tokens_dir = tmp_path / "tokens"
        rel = tokens_dir / "latinLit" / "phi1017" / "phi007" / "perseus-lat2"
        rel.mkdir(parents=True)
        monkeypatch.setattr(config, "TOKENS_DIR", tokens_dir)

        chunk = proto_dir / "57.xml"
        chunk.write_text("<x/>")
        (rel / "57.tokens.json.zst").write_bytes(_zst(TOKENS_PAYLOAD))

        result = chunksmod._load_token_sidecar(chunk)
        assert result == TOKENS_PAYLOAD

    def test_tokens_dir_takes_priority_over_co_located(
        self, tmp_path, proto_dir, monkeypatch
    ):
        tokens_dir = tmp_path / "tokens"
        rel = tokens_dir / "latinLit" / "phi1017" / "phi007" / "perseus-lat2"
        rel.mkdir(parents=True)
        monkeypatch.setattr(config, "TOKENS_DIR", tokens_dir)

        chunk = proto_dir / "57.xml"
        chunk.write_text("<x/>")
        (rel / "57.tokens.json.zst").write_bytes(
            _zst({"urn": "from-tokens-dir", "tokens": []})
        )
        (proto_dir / "57.tokens.json.zst").write_bytes(
            _zst({"urn": "from-co-located", "tokens": []})
        )

        result = chunksmod._load_token_sidecar(chunk)
        assert result["urn"] == "from-tokens-dir"

    def test_falls_back_to_co_located_when_missing_from_tokens_dir(
        self, tmp_path, proto_dir, monkeypatch
    ):
        tokens_dir = tmp_path / "tokens"
        tokens_dir.mkdir()
        monkeypatch.setattr(config, "TOKENS_DIR", tokens_dir)

        chunk = proto_dir / "57.xml"
        chunk.write_text("<x/>")
        (proto_dir / "57.tokens.json.zst").write_bytes(_zst(TOKENS_PAYLOAD))

        result = chunksmod._load_token_sidecar(chunk)
        assert result == TOKENS_PAYLOAD

    def test_does_not_raise_when_chunk_outside_proto_dir(self, tmp_path, monkeypatch):
        """A chunk path unrelated to PROTO_DIR (e.g. in ad hoc test fixtures)
        must not blow up computing the TOKENS_DIR candidate."""
        tokens_dir = tmp_path / "tokens"
        tokens_dir.mkdir()
        monkeypatch.setattr(config, "TOKENS_DIR", tokens_dir)
        monkeypatch.setattr(config, "PROTO_DIR", tmp_path / "elsewhere")

        outside = tmp_path / "somewhere-else"
        outside.mkdir()
        chunk = outside / "57.xml"
        chunk.write_text("<x/>")

        assert chunksmod._load_token_sidecar(chunk) is None

# tests/test_search_normalize.py
#
# The /search page computes match keys in the browser
# (static/js/search/normalize.js) that must equal the keys mvp-tokenization
# stored in the search index. search_normalization.json is a copy of
# mvp-tokenization's tests/fixtures/normalization.json -- the shared
# contract both implementations are tested against. Needs node to run the
# JS; skipped without it.

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
FIXTURE = ROOT / "tests" / "data" / "search_normalization.json"
NORMALIZE_JS = ROOT / "src" / "mvp" / "site" / "static" / "js" / "search" / "normalize.js"

SCRIPT = """
const [modulePath, fixturePath] = process.argv.slice(1);
const { matchKey, looseKey } = await import(modulePath);
const { readFileSync } = await import('node:fs');
const { cases } = JSON.parse(readFileSync(fixturePath, 'utf8'));
console.log(JSON.stringify(cases.map((c) => ({
    text: c.text, lang: c.lang,
    match_key: matchKey(c.text, c.lang), loose_key: looseKey(c.text, c.lang),
}))));
"""


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_js_keys_match_shared_fixture():
    result = subprocess.run(
        ["node", "--input-type=module", "-e", SCRIPT, NORMALIZE_JS.as_uri(), str(FIXTURE)],
        capture_output=True,
        text=True,
        check=True,
    )
    expected = json.loads(FIXTURE.read_text(encoding="utf-8"))["cases"]
    assert json.loads(result.stdout) == expected

import json
import os

from pathlib import Path

import requests

from mvp.models import ChunkIndex, ChunkOccurrence

NLP_SERVER_URL = os.getenv("NLP_SERVER_URL", "http://127.0.0.1:8000")


def analyze_chunk_index(index: ChunkIndex):
    return [do_analyze(entry) for entry in index.entries]


def do_analyze(entry: ChunkOccurrence):
    s = entry.chunk

    body = {"content": s}

    resp = requests.post(f"{NLP_SERVER_URL}/analyze", json=body)

    return resp.json()


def write_annotations(index: ChunkIndex, path: Path):
    results = {entry.xpath: do_analyze(entry) for entry in index.entries}
    path.write_text(json.dumps(results, ensure_ascii=False), encoding="utf-8")

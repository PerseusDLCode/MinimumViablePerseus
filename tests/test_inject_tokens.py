# tests/test_inject_tokens.py
#
# chunks._inject_tokens replaces kodon_py's inject_tokens, which scanned
# every token for every text run (minutes on a book-length chunk). It must
# select exactly the same tokens per run, and keep only the fields the
# templates read.

from __future__ import annotations

import copy

from kodon_py.tei_parser import inject_tokens as kodon_inject_tokens

from mvp.site import chunks


def _elements():
    return [
        {
            "tagname": "div",
            "children": [
                {"tagname": "text_run", "start": 0, "end": 11, "text": "μῆνιν ἄειδε"},
                {"tagname": "lb", "children": []},
                {
                    "tagname": "l",
                    "children": [
                        {"tagname": "text_run", "start": 11, "end": 20, "text": " θεὰ, ὦ "},
                        {"tagname": "text_run", "start": 20, "end": 25, "text": "     "},
                    ],
                },
                {"tagname": "note", "children": [{"tagname": "text_run", "text": "paratext"}]},
            ],
        }
    ]


def _token(text, start, n, urn=True):
    return {
        "text": text,
        "start_char": start,
        "end_char": start + len(text),
        "whitespace": True,
        "identifier": f"{text}[{n}]",
        "urn": f"urn:cts:greekLit:tlg0012.tlg001.perseus-grc2:1.1@{text}[{n}]" if urn else None,
        "words": [{"lemma": "x", "upos": "NOUN", "feats": "Case=Acc"}],
    }


TOKENS = [
    _token("μῆνιν", 0, 1),
    _token("ἄειδε", 6, 1),
    _token("θεὰ", 12, 1),
    _token(",", 15, 1, urn=False),
    _token("ὦ", 17, 1),
]


def _shape(elements):
    """Each node's tag and text, with tokens reduced to the fields kept."""
    out = []
    for el in elements:
        node = {"tagname": el.get("tagname"), "text": el.get("text"), "urn": el.get("urn")}
        if "children" in el:
            node["children"] = _shape(el["children"])
        out.append(node)
    return out


def test_matches_kodon_inject_tokens():
    ours, theirs = _elements(), _elements()
    chunks._inject_tokens(ours, copy.deepcopy(TOKENS))
    kodon_inject_tokens(theirs, copy.deepcopy(TOKENS))
    assert _shape(ours) == _shape(theirs)


def test_unsorted_tokens_are_placed_in_order():
    ours, theirs = _elements(), _elements()
    chunks._inject_tokens(ours, list(reversed(copy.deepcopy(TOKENS))))
    kodon_inject_tokens(theirs, copy.deepcopy(TOKENS))
    assert _shape(ours) == _shape(theirs)


def test_keeps_only_rendered_fields():
    elements = _elements()
    chunks._inject_tokens(elements, copy.deepcopy(TOKENS))
    token = elements[0]["children"][0]
    assert token["tagname"] == "token"
    assert set(token) == {"tagname", *chunks._TOKEN_FIELDS}


def test_parse_chunk_cache_is_bounded():
    assert chunks._parse_chunk.cache_info().maxsize == chunks._PARSED_CHUNK_CACHE_SIZE

# Notes for Charles — `site/` code and the document class consolidation

## Nothing breaks immediately

The `LenientTEIDocument` name is kept as a backward-compatible alias for the
merged `TEIDocument` class, so all existing imports in `app.py` continue to
work without any changes.

## What changed under the hood

`TEIDocument` and `LenientTEIDocument` were two separate classes wrapping the
same file with different parsers.

- `TEIDocument` (strict parser: `load_dtd=False`, `resolve_entities=False`) was
  used by `Corpus.documents()` to enumerate files and extract URNs.
- `LenientTEIDocument` (`recover=True`) was used by `Chunker` and `CTSResolver`.

They are now a single class — `TEIDocument` — using a lenient parser
(`recover=True`, `load_dtd=False`, `resolve_entities=False`, `no_network=True`).

One visible behavior change: the corpus no longer silently skips files that the
old strict parser rejected as malformed. Those files now parse with whatever
partial tree `recover=True` can build. If the resulting structure is unusable
(no `<body @xml:base>`, no `<citeStructure>`), `CTSResolver` raises a
`ConfigurationError` with a clear message. That is more informative than a
silent skip.

## One thing you should fix: eliminating a double parse

In `generate_proto_pages` (`app.py`, lines 285–299), every document is
currently parsed **twice**: once by `Corpus.documents()` to get the URN, and
again on line 293 when `LenientTEIDocument(doc.path)` is constructed and passed
to `Chunker`.

The `doc` object that `Corpus.documents()` yields is now the same class as
`LenientTEIDocument`. It already has a parsed tree and exposes `.root`. You can
pass it directly to `Chunker` and eliminate the second parse entirely:

```python
# Current — two parses of the same file:
tei_doc = LenientTEIDocument(doc.path)
compiler = Chunker(tei_doc)

# Simplified — one parse:
compiler = Chunker(doc)
```

For a large corpus this halves the I/O and XML parse work in the generation
loop.

When you make this change you can also drop the `LenientTEIDocument` import
from `app.py`:

```python
# Before
from mvp.models import Corpus, LenientTEIDocument

# After
from mvp.models import Corpus
```

## Two smaller issues worth cleaning up

### 1. Redundant exception clause (`app.py`, line 297)

```python
except (ConfigurationError, Exception) as exc:
```

`Exception` is the superclass of `ConfigurationError`, so naming both is
redundant. Simplify to:

```python
except Exception as exc:
```

### 2. `tei_parser.py` creates a `tmp/` directory at import time (lines 23–30)

```python
tmp_dir = Path("tmp")
if not tmp_dir.exists():
    tmp_dir.mkdir()
log_filepath = tmp_dir / Path(f"{__name__}.log")
file_handler = logging.FileHandler(log_filepath, mode="w")
```

These lines execute the moment any code does
`from mvp.site.tei_parser import TEIParser`. The directory is created relative
to wherever the process happens to run, and the log file is truncated
(`mode="w"`) every time the module is imported in a new process.

Moving this setup into a helper function or into `TEIParser.__init__` would
make the module safe to import without side effects.

# Perseus6

Perseus 6 will be a reading environment that replaces Perseus 4 (the
Hopper). Our first project is implementing Minimum Viable Perseus (MVP),
a website that reproduces the Hopper's critical functionality.

## Background

The Perseus Digital Library is a large collection of texts encoded in
TEI XML. These encoded texts are Open Source and available on
[GitHub](https://github.com/PerseusDL). Perseus has always provided
tools for discovering resources and reading them in a richly
hypertextual environment. Perseus6 is an implementation of those tools.

## Installation

### Prerequisites

- **Python 3.12+**
- **Java 11+** (required by Saxon for XSLT 3.0 transformations)
- **[PDM](https://pdm-project.org/)** — Python dependency manager

### Steps

1. Clone the repository:

   ```bash
   git clone https://github.com/PerseusDLCode/mvp.git
   cd mvp
   ```

2. Install Python dependencies (including Saxon):

   ```bash
   pdm install
   ```

3. Clone the corpus data (optional — required for building the site):

   ```bash
   git clone https://github.com/PerseusDL/canonical-latinLit.git data/canonical-latinLit
   git clone https://github.com/PerseusDL/canonical-greekLit.git  data/canonical-greekLit
   ```

4. Download the morphology data files (optional — required for the morphological server):

   ```bash
   python src/tools/setup_morph_data.py
   ```

   This fetches `greek.morph.xml` (~270 MB) and `latin.morph.xml` (~111 MB) from Tufts Box
   into `src/morph-server/`. The files are derived from the
   [Perseus Morpheus project](https://github.com/PerseusDL/morpheus) and are not stored
   in this repository due to their size.

   Install the morph server dependencies as well:

   ```bash
   pdm install -G morph
   ```

### Running the test suite

```bash
pdm run test
```

Slow integration tests (require Saxon) are excluded by default. To run them:

```bash
pdm run test -m slow
```

## Building the site

Compile one or more corpora into a static site:

```bash
# Single corpus
pdm run python src/tools/run_build.py data/canonical-latinLit/data /tmp/out

# Both corpora in one pass → unified catalog
pdm run python src/tools/run_build.py \
    data/canonical-latinLit/data \
    data/canonical-greekLit/data \
    /tmp/out
```

Rebuild the catalog from existing compiled output (no recompilation):

```bash
pdm run python src/tools/run_build.py --catalog-only /tmp/out
```

### Building with morphological links

Pass `--morph-url` to embed a link to the morphological server on every word.
Use the same port you intend to run the morph server on (default: 5000):

```bash
pdm run python src/tools/run_build.py \
    --morph-url http://localhost:5000 \
    data/canonical-latinLit/data \
    /tmp/out
```

## Running locally

To serve the compiled site and start the morphological server together:

```bash
python src/tools/run_local.py /tmp/out
```

This starts:
- A static HTTP server at `http://localhost:8000/`
- The morphological analysis server at `http://localhost:5000/`

Use `--site-port` and `--morph-port` to change the defaults. Press Ctrl+C to stop both servers.

Note: the morph server indexes ~380 MB of XML on startup; expect a 30–60 second delay before it is ready.

The morphological server also exposes a JSON API directly:

```
GET http://localhost:5000/analyze?form=arma&lang=la
```

## Documentation

See the wiki associated with this repository for standards, workflows,
and best practices used in this project. Also see documentation in the
docs/ directory of this repository.

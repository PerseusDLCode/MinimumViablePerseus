# ================================================================
# MinimumViablePerseus — Build + Serve Image
#
# At build time, this image clones the TEI corpus repositories,
# generates proto-pages, and compiles the frozen static site.
# At run time, it serves the static site via Python's built-in
# HTTP server.
#
# The GitHub Actions workflow can still extract /app/build/ from
# a created container for release packaging.
# ================================================================

FROM python:3.12-slim

# ----------------------------------------------------------------
# System dependencies
# ----------------------------------------------------------------
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# ----------------------------------------------------------------
# uv
# ----------------------------------------------------------------
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:${PATH}"

# ----------------------------------------------------------------
# TEI Corpus data
#
# GREEK_CORPUS_SHA and LATIN_CORPUS_SHA are set by the CI workflow
# to the current HEAD commit of each corpus's `editing` branch.
# When those SHAs change, Docker invalidates this layer and
# re-clones. When they haven't changed, the cached layer is reused,
# so a code-only push to `dev` never triggers a full re-clone.
#
# The `echo` on each line is intentional: it forces Docker to see
# the ARG value as part of the RUN command, which is what triggers
# cache invalidation when the SHA changes.
# ----------------------------------------------------------------
ARG GREEK_CORPUS_SHA=latest
ARG LATIN_CORPUS_SHA=latest

ARG CORPORA_DIR=/corpora
RUN echo "greekLit @ ${GREEK_CORPUS_SHA}" && \
    git clone --depth 1 --branch editing \
    https://github.com/PerseusDLCode/canonical-greekLit \
    ${CORPORA_DIR}/greekLit

RUN echo "latinLit @ ${LATIN_CORPUS_SHA}" && \
    git clone --depth 1 --branch editing \
    https://github.com/PerseusDLCode/canonical-latinLit \
    ${CORPORA_DIR}/latinLit

# ----------------------------------------------------------------
# Python dependencies
#
# We copy pyproject.toml first and run `uv sync --no-install-project`
# so that the heavy dependency-install layer is cached independently
# of source code changes. A code-only push hits the cache here and
# only re-runs the build layer below.
#
# --no-dev excludes pytest, ruff, mypy — not needed at build time.
# --no-install-project installs deps only; the project itself is
# installed in the next step once source is present.
# ----------------------------------------------------------------
WORKDIR /app

COPY pyproject.toml .
COPY README.md .  
COPY uv.lock .

ENV UV_PYTHON=3.12
RUN uv sync --no-dev --no-install-project

# ----------------------------------------------------------------
# Source code
# ----------------------------------------------------------------
COPY src/ src/

# Install the project itself (registers the mvp-* entry points).
RUN uv sync --no-dev

# ----------------------------------------------------------------
# Proto-pages
#
# Generate proto-page XML from the cloned TEI corpora.
# ----------------------------------------------------------------
ENV CORPORA_DIR=${CORPORA_DIR}
ENV PROTOPAGE_OUTPUT_DIR=/app/proto-pages
RUN uv run mvp-proto

# ----------------------------------------------------------------
# Build
#
# MORPH_URL is passed in at build time so the generated HTML links
# to the correct Morpheus endpoint for the target environment
# (dev vs prod). It comes from a GitHub Actions secret and is
# passed as a --build-arg by the CI workflow.
# ----------------------------------------------------------------
ARG MORPH_URL=http://localhost:5000
ENV MORPH_URL=${MORPH_URL}

ARG BUILD_DATE

RUN uv run mvp-build; \
    PAGE_COUNT=$(find /app/build -name "*.html" 2>/dev/null | wc -l); \
    echo "Build finished. ${PAGE_COUNT} HTML pages generated."; \
    if [ "${PAGE_COUNT}" -eq 0 ]; then \
    echo "ERROR: Build produced no HTML output."; exit 1; \
    fi

# ----------------------------------------------------------------
# Runtime — serve the frozen static site
# ----------------------------------------------------------------
EXPOSE 8080
CMD ["python", "-m", "http.server", "8080", "--directory", "/app/build"]

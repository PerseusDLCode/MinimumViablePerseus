# ================================================================
# MinimumViablePerseus — Builder Image
#
# At build time, this image clones the TEI corpus repositories
# and installs Python dependencies. At run time, it generates
# proto-pages and runs the static site build into a mounted
# /app/build volume.
#
# This image is ~2 GB (well under GHCR's 10 GB-per-layer cap) and
# is intended to be run on the VM, not serve directly.
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
ARG FIRST_1K_GREEK_SHA=latest
ARG PDLREFWK_SHA=latest

ARG CORPORA_DIR=/corpora
RUN echo "greekLit @ ${GREEK_CORPUS_SHA}" && \
    git clone --depth 1 --branch editing \
    https://github.com/PerseusDLCode/canonical-greekLit \
    ${CORPORA_DIR}/greekLit

RUN echo "latinLit @ ${LATIN_CORPUS_SHA}" && \
    git clone --depth 1 --branch editing \
    https://github.com/PerseusDLCode/canonical-latinLit \
    ${CORPORA_DIR}/latinLit

RUN echo "First1KGreek @ ${FIRST_1K_GREEK_SHA}" && \
    git clone --depth 1 --branch editing \
    https://github.com/PerseusDLCode/First1KGreek \
    ${CORPORA_DIR}/First1KGreek

RUN echo "canonical-pdlrefwk @ ${PDLREFWK_SHA}" && \
    git clone --depth 1 --branch dev \
    https://github.com/PerseusDLCode/canonical-pdlrefwk \
    ${CORPORA_DIR}/canonical-pdlrefwk

# pdl_refwk 
COPY canonical_pdlrefwk/ /app/data/  

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
RUN uv sync --no-dev --no-install-project --no-cache

# ----------------------------------------------------------------
# Source code
# ----------------------------------------------------------------
COPY src/ src/

# Install the project itself (registers the mvp-* entry points).
RUN uv sync --no-dev --no-cache

ENV CORPORA_DIR=${CORPORA_DIR}
ENV PROTOPAGE_OUTPUT_DIR=/app/proto-pages

# ----------------------------------------------------------------
# Runtime — build the static site
#
# MORPH_URL must be passed via `-e` at runtime.
# The build output is written to /app/build (mount a volume there).
# ----------------------------------------------------------------
CMD ["uv", "run", "mvp-build"]

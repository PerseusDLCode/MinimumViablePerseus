# ================================================================
# MinimumViablePerseus — Build Image
#
# This is a BUILD image, not a serve image. It produces a static
# site at /app/build/ which the GitHub Actions workflow extracts,
# packages, and publishes as a GitHub Release artifact.
#
# The running web server on the VM is untouched by this process;
# the deploy script on the VM simply downloads the release tarball
# and swaps the symlink.
# ================================================================

FROM eclipse-temurin:21-jdk-jammy

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
#
# If you add a uv.lock to the repo (recommended for reproducibility),
# uncomment the COPY uv.lock line and add --frozen to both uv sync
# calls below.
# ----------------------------------------------------------------
WORKDIR /app

COPY pyproject.toml .
COPY README.md .  
# COPY uv.lock .                  ← uncomment once uv.lock exists

ENV UV_PYTHON=3.12
RUN uv sync --no-dev --no-install-project

# ----------------------------------------------------------------
# Source code
# ----------------------------------------------------------------
COPY src/ src/

# Install the project itself (registers the mvp-build entry point).
RUN uv sync --no-dev

# ----------------------------------------------------------------
# Build
#
# MORPH_URL is passed in at build time so the generated HTML links
# to the correct Morpheus endpoint for the target environment
# (dev vs prod). It comes from a GitHub Actions secret and is
# passed as a --build-arg by the CI workflow.
#
# TEI_DATA_ROOT points to the corpora directory cloned above.
# ----------------------------------------------------------------
ARG MORPH_URL=http://localhost:5000
ENV MORPH_URL=${MORPH_URL}
ENV TEI_DATA_ROOT=${CORPORA_DIR}

# This argument invalidates caching to allow for the runner to update this everytime
ARG BUILD_DATE 

# This is hacky but I am getting ValueError: Unexpected status '500 INTERNAL SERVER ERROR' on URL /greekLit/tlg0016/tlg001/perseus-eng2/1.1/, will need to talk to Charles about this
RUN uv run mvp-build; \
    PAGE_COUNT=$(find /app/build -name "*.html" 2>/dev/null | wc -l); \
    echo "Build finished. ${PAGE_COUNT} HTML pages generated."; \
    if [ "${PAGE_COUNT}" -eq 0 ]; then \
        echo "ERROR: Build produced no HTML output."; exit 1; \
    fi

# The static site is now at /app/build/.
# The CI workflow extracts it with:
#   docker create mvp-build:latest  →  docker cp <id>:/app/build/ ./build/
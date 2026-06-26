import os
from pathlib import Path

from mvp.site.app import _discover_corpora, generate_proto_pages


def main() -> None:
    corpora_dir = Path(os.environ.get("CORPORA_DIR", "/corpora"))
    proto_dir = Path(os.environ.get("PROTOPAGE_OUTPUT_DIR", "proto-pages"))
    corpora = _discover_corpora(corpora_dir)
    generate_proto_pages(proto_dir, corpora)


if __name__ == "__main__":
    main()

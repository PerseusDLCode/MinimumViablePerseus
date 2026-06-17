from pathlib import Path
import json
import os


# TODO: Move to cts utilities module
def split_cts_urn(urn):
    last_part = urn.split(":")[-1]
    parts = last_part.split(".")

    group = parts[0]
    work = parts[1]
    version = parts[2]

    return group, work, version


def classify_document(document):
    language = document.get("language", "")
    base_urn = document.get("base_urn", "")

    if "commentary" in document.get("title", "").lower():
        return "commentaries"

    if language == "grc" or language == "lat":
        return "editions"

    # Non-Greek = translation
    return "translations"


def generate_mapping(proto_root, output_file):
    PROTO_ROOT = Path(
    os.getenv("PROTOPAGE_OUTPUT_DIR", "./proto-pages")
)
    mapping = {}

    for metadata_file in proto_root.rglob("metadata.json"):
        with open(metadata_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        document = data.get("document", {})

        base_urn = document.get("base_urn")
        author = document.get("author")
        title = document.get("title")
        language = document.get("language")

        if not base_urn:
            continue

        group, work, version = split_cts_urn(base_urn)

        if not group or not work:
            continue

        if group not in mapping:
            mapping[group] = {
                "author": author,
                "works": {}
            }

        if work not in mapping[group]["works"]:
            mapping[group]["works"][work] = {
                "title": title,
                "editions": [],
                "translations": [],
                "commentaries": []
            }

        category = classify_document(document)

        mapping[group]["works"][work][category].append({
            "urn": base_urn,
            "language": language,
            "title": title,
            "metadata_file": str(metadata_file)
        })

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(mapping, f, indent=4, ensure_ascii=False)

    return mapping
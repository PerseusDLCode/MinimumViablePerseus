# Templating (The Site/Views Layer)

This README documents the data required for the view layer (Jinja templates)
of MVP.

## Required for the reading view

- [ ] CTS URN
- [ ] XML source URL

### Header

- [ ] Textgroup (author)
- [ ] Title
- [ ] Creator(s) (editors, translators, commentary authors)

### Left column

- [ ] Corpus information (e.g., _Argonautica_ belongs to "Greek and Roman Materials", "Greek Texts", "Greek Poetry", and "Apollonius Rhodius" (from least to most specific))
    - [ ] `url` attribute
    - [ ] `name` attribute
- [ ] Table of contents

If the table of contents can look something like this:

```json
{
  "depth": 0,
  "index": 0,
  "label": "Book 1",
  "subtype": "book",
  "urn": "urn:cts:greekLit:tlg0057.tlg009.1st1K-grc1:1",
  "subpassages": [
    {
      "depth": 1,
      "index": 1,
      "label": "Chapter 1",
      "subtype": "chapter",
      "urn": "urn:cts:greekLit:tlg0057.tlg009.1st1K-grc1:1.1"
    },
    {
      "depth": 1,
      "index": 2,
      "label": "Chapter 2",
      "subtype": "chapter",
      "urn": "urn:cts:greekLit:tlg0057.tlg009.1st1K-grc1:1.2"
    }]
}
```

where `subpassages` (vel sim.) indicates more chunks of greater specificity,
I have templates ready to go that can handle the nesting.

### Center column (main text)

- [ ] Text chunk(s)
- [ ] Text chunk identifiers (e.g., line numbers or other canonical references)
- [ ] Words/tokens within each text chunk
- [ ] Base URL for Morpheus server (so that we can assemble the links on each word)
- [ ] Full publication information: `${TEXTGROUP}. ${TITLE}. ${EDITOR}. ${LOCATION}. ${PUBLISHER}. ${YEAR}.`


### Right column

- [ ] Notes with editor information, if available
- [ ] Cross-references, if available
- [ ] Stable identifiers: Citation URI, Text URI, Work URI, Catalog Record URI


## Required for the dictionary view

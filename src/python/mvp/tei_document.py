# mvp/tei_document.py — shim; to be removed in cleanup commit
from mvp.corpus.tei_document import *  # noqa: F401,F403
from mvp.corpus.tei_document import (  # noqa: F401
    TEI_NS, XML_NS, NS, XML_BASE, XML_ID, XML_LANG,
    LenientTEIDocument, expected_div_base, expected_leaf_base,
)

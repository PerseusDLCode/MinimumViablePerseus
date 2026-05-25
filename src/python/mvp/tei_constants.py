"""Shared TEI and XML namespace constants for the mvp package."""

TEI_NS = "http://www.tei-c.org/ns/1.0"
XML_NS = "http://www.w3.org/XML/1998/namespace"

NS = {"tei": TEI_NS, "xml": XML_NS}

XML_BASE = f"{{{XML_NS}}}base"
XML_ID   = f"{{{XML_NS}}}id"
XML_LANG = f"{{{XML_NS}}}lang"

<?xml version="1.0" encoding="UTF-8"?>
<xsl:stylesheet xmlns:xsl="http://www.w3.org/1999/XSL/Transform"
    xmlns:xs="http://www.w3.org/2001/XMLSchema"
    xmlns:tei="http://www.tei-c.org/ns/1.0"
    xpath-default-namespace="http://www.tei-c.org/ns/1.0"
    exclude-result-prefixes="xs tei"
    version="4.0">
    <xsl:output method="xml" indent="yes" />

    <!-- Replace cRefPattern-based CTS refsDecl with one using citeStructure-->
    <xsl:template match="tei:refsDecl[@n='CTS']">
        <xsl:copy>
            <xsl:attribute name="xml:id">cite_by_cts_urn</xsl:attribute>
            <xsl:attribute name="default">true</xsl:attribute>
            <tei:citeStructure match="/tei:TEI/tei:text/tei:body" use="@xml:base">
                <tei:citeStructure unit="book" delim=":" match="tei:div[@type='book']" use="@n">
                    <tei:citeStructure unit="chapter" delim="." match="tei:div[@type='chapter']"
                        use="@n">
                        <tei:citeStructure unit="section" delim="." match="tei:div[@type='section']"
                            use="@n" />
                    </tei:citeStructure>
                </tei:citeStructure>
            </tei:citeStructure>
        </xsl:copy>
    </xsl:template>

    <!-- Suppress the refState RefsDecl; no longer used -->
    <xsl:template match="tei:refsDecl" />


    <xsl:template match="@*|node()">
        <xsl:copy>
            <xsl:apply-templates select="@*|node()" />
        </xsl:copy>
    </xsl:template>

    <!-- remove unneeded attributes -->
    <xsl:template
        match="@part[. = 'N'] | @org[. = 'uniform'] | @sample[. = 'complete'] | @instant | @status | @full" />

</xsl:stylesheet>

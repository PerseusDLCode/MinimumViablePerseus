<?xml version="1.0" encoding="UTF-8"?>
<xsl:stylesheet xmlns:xsl="http://www.w3.org/1999/XSL/Transform"
    xmlns:xs="http://www.w3.org/2001/XMLSchema"
    xmlns:tei="http://www.tei-c.org/ns/1.0"
    xpath-default-namespace="http://www.tei-c.org/ns/1.0"
    exclude-result-prefixes="xs tei"

    version="4.0">
    <xsl:output method="xml" indent="yes" />
    
    <!-- remove spurious extent -->
    <xsl:template match="tei:teiHeader/tei:extent" />
    
    <!-- Add a CTS identifier; it is the same as the filename 
        identifer minus the .xml suffix. -->
    <xsl:template match="tei:idno[@type='filename']">
        <xsl:variable name="stem" select="substring-before(., '.xml')"/>
        <xsl:copy-of select="."></xsl:copy-of>
        <xsl:copy>
            <xsl:attribute name="type">cts_urn</xsl:attribute>
            <xsl:value-of select="concat('urn:cts:greekLit:', $stem)"/>
        </xsl:copy>
    </xsl:template>
    
    <!-- Replace cRefPattern-based CTS refsDecl with one using citeStructure-->
    <xsl:template match="tei:refsDecl[@n='CTS']">
        <xsl:copy>
            <xsl:attribute name="xml:id">cite_by_cts_urn</xsl:attribute>
            <xsl:attribute name="default">true</xsl:attribute>
            <tei:citeStructure match="/tei:TEI/tei:text/tei:body" use="@xml:base">
                <tei:citeStructure unit="book" delim=":" match="tei:div[@type='book']" use="@n">
                    <tei:citeStructure unit="chapter" delim="." match="tei:div[@type='chapter']" use="@n">
                        <tei:citeStructure unit="section" delim="." match="tei:div[@type='section']" use="@n"/>
                    </tei:citeStructure>
                </tei:citeStructure>
            </tei:citeStructure>
        </xsl:copy>
    </xsl:template>
    
    <!-- Suppress the refState RefsDecl; no longer used -->
    <xsl:template match="tei:refsDecl" />

    <!-- Put the cts urn base on the body element. -->
    <xsl:template match="tei:body">
        <xsl:variable name="stem" select="substring-before(ancestor::TEI/teiHeader//idno[@type='filename'], '.xml')"/>
        <xsl:copy>
        
            <xsl:attribute name="xml:base">
                <xsl:value-of select="concat('urn:cts:greekLit:', $stem)" />
            </xsl:attribute>
            <xsl:apply-templates />
        </xsl:copy>
    </xsl:template>
    
    <!-- remove EpiDoc-inspired top-level attributes -->
    <xsl:template match="tei:div[@type='edition'] | tei:div[@type='translation']">
        <xsl:apply-templates />
    </xsl:template>
    
    <!-- hoist div subtypes to types -->
    <xsl:template match="tei:div[@type='textpart' and not(empty(@subtype))]">
        <xsl:copy>
            <xsl:attribute name="type" select="@subtype" />
            <xsl:attribute name="n"><xsl:value-of select="@n"/></xsl:attribute>
            <xsl:apply-templates />
        </xsl:copy>
    </xsl:template>
    
    <!-- properly encode dactylic meter -->
    <xsl:template match="tei:l[@ana='#met-dact']">
        <xsl:copy>
            <xsl:attribute name="met">dact</xsl:attribute>
            <xsl:apply-templates />
        </xsl:copy>
    </xsl:template>
    
    <!-- properly encode hexameter -->
    <xsl:template match="tei:l[@ana='#met-hexameter']">
        <xsl:copy>
            <xsl:attribute name="met">hexameter</xsl:attribute>
            <xsl:apply-templates />
        </xsl:copy>
    </xsl:template>

    <!-- remove @xml:base attributes;
    CTS URNs are calculated from <citeStructure>-->
    <xsl:template match="@xml:base" />

    
    <xsl:template match="@*|node()">
        <xsl:copy>
            <xsl:apply-templates select="@*|node()"/>
        </xsl:copy>
    </xsl:template>
    
    <!-- remove unneeded attributes -->
    <xsl:template match="@part[. = 'N'] | @org[. = 'uniform'] | @sample[. = 'complete'] | @instant | @status | @full"/>
    
    
</xsl:stylesheet>
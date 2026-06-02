<?xml version="1.0" encoding="UTF-8"?>
<xsl:stylesheet xmlns:xsl="http://www.w3.org/1999/XSL/Transform"
    xmlns:xs="http://www.w3.org/2001/XMLSchema"
    xmlns:tei="http://www.tei-c.org/ns/1.0"
    xpath-default-namespace="http://www.tei-c.org/ns/1.0"
    exclude-result-prefixes="xs tei"

    version="4.0">
    <xsl:output method="xml" indent="yes" />

    <!-- CTS namespace component (greekLit, latinLit, …).
         Pass as a stylesheet parameter; defaults to greekLit. -->
    <xsl:param name="cts-namespace" as="xs:string" select="'greekLit'"/>

    <!-- Derive the work stem from the source document's filename
         (e.g. tlg0003.tlg001.perseus-grc2 from tlg0003.tlg001.perseus-grc2.xml).
         This is reliable for every file in the corpus regardless of whether
         idno[@type='filename'] is present. -->
    <xsl:variable name="doc-stem" as="xs:string"
        select="substring-before(tokenize(document-uri(/), '/')[last()], '.xml')"/>

    <!-- Match the xml-model PI and replace the href -->
    <xsl:template match="processing-instruction('xml-model')">
        <xsl:processing-instruction name="xml-model">
      <xsl:text>href="https://raw.githubusercontent.com/PerseusDLCode/perseus-schemas/main/perseus_base.rnc" type="application/xml" schematypens="http://relaxng.org"</xsl:text>
    </xsl:processing-instruction>
    </xsl:template>

    <!-- remove spurious extent -->
    <xsl:template match="tei:teiHeader/tei:extent" />

    <!-- Add a cts_urn idno alongside any existing filename idno. -->
    <xsl:template match="tei:idno[@type='filename']">
        <xsl:copy-of select="."/>
        <xsl:copy>
            <xsl:attribute name="type">cts_urn</xsl:attribute>
            <xsl:value-of select="concat('urn:cts:', $cts-namespace, ':', $doc-stem)"/>
        </xsl:copy>
    </xsl:template>

    <!-- Put the CTS URN base on the body element.
         refsDecl is left intact here; refsDeclTransform.xsl handles
         the cRefPattern → citeStructure migration in a separate pass. -->
    <xsl:template match="tei:body">
        <xsl:copy>
            <xsl:attribute name="xml:base"
                select="concat('urn:cts:', $cts-namespace, ':', $doc-stem)"/>
            <xsl:apply-templates/>
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

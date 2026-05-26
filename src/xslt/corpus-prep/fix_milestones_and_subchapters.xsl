<?xml version="1.0" encoding="UTF-8"?>
<xsl:stylesheet xmlns:xsl="http://www.w3.org/1999/XSL/Transform"
    xmlns:xs="http://www.w3.org/2001/XMLSchema"
    xmlns:tei="http://www.tei-c.org/ns/1.0"
    xpath-default-namespace="http://www.tei-c.org/ns/1.0"
    exclude-result-prefixes="xs tei"
    version="4.0">
    
    <xsl:template match="tei:div[@type='edition'] | tei:div[@type='translation']">
        <xsl:apply-templates />
    </xsl:template>
    
    <xsl:template match="tei:div[@type='textpart' and @subtype='chapter']">
        <xsl:copy>
            <xsl:attribute name="type" select="@subtype"/>
            <xsl:attribute name="n" select="@n"/>
            <xsl:apply-templates />
        </xsl:copy>
    </xsl:template>

    <xsl:template match="tei:div[@type='textpart' and @subtype='subchapter']">
        <xsl:apply-templates>
            <xsl:with-param name="subchapter-n" select="@n" tunnel="yes"/>
        </xsl:apply-templates>
    </xsl:template>
    
    <xsl:template match="tei:body//tei:p">
        <xsl:param name="subchapter-n" tunnel="yes"/>
        <xsl:copy>
            <xsl:attribute name="n" select="$subchapter-n"/>
            <xsl:apply-templates select="@*|node()"/>
        </xsl:copy>
    </xsl:template> 
    
    <xsl:template match="tei:milestone[@unit='page' and @resp='Bekker']">
        <xsl:variable name="val" select="@n"/>
        <xsl:variable name="num" select="substring($val, 1, string-length($val) - 1)"/>
        <xsl:variable name="col" select="substring($val, string-length($val))"/>
        
        <xsl:choose>
            <xsl:when test="$col = 'a'">
                <xsl:copy>
                    <xsl:attribute name="ed">Bekker</xsl:attribute>
                    <xsl:attribute name="unit" select="@unit" />
                    <xsl:attribute name="n" select="$num" />
                </xsl:copy>
                <xsl:copy>
                    <xsl:attribute name="ed">Bekker</xsl:attribute>
                    <xsl:attribute name="unit">column</xsl:attribute>
                    <xsl:attribute name="n">a</xsl:attribute>
                </xsl:copy>
            </xsl:when>
            <xsl:when test="$col = 'b'">
                <xsl:copy>
                    <xsl:attribute name="unit">column</xsl:attribute>
                    <xsl:attribute name="ed">Bekker</xsl:attribute>
                    <xsl:attribute name="n">b</xsl:attribute>
                </xsl:copy>
            </xsl:when>
            <xsl:otherwise>
                <xsl:copy>
                    <xsl:attribute name="ed" select="@resp"/>
                    <xsl:apply-templates select="@* except (@n, @resp) | node()"/>
                    <xsl:attribute name="n" select="$val"/>
                </xsl:copy>
            </xsl:otherwise>
        </xsl:choose>
    </xsl:template>
    
    <xsl:template match="@xml:base" />
    
    <xsl:template match="@*|node()">
        <xsl:copy>
            <xsl:apply-templates select="@*|node()"/>
        </xsl:copy>
    </xsl:template>
    
    <xsl:template match="@part[. = 'N'] | @org[. = 'uniform'] | @sample[. = 'complete'] | @instant | @status "/>
    
</xsl:stylesheet>
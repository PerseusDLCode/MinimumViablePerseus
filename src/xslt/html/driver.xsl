<?xml version="1.0" encoding="UTF-8"?>

<!-- 
    SAMPLE DRIVER FILE
-->

<xsl:stylesheet xmlns:xsl="http://www.w3.org/1999/XSL/Transform"
    xmlns:xs="http://www.w3.org/2001/XMLSchema"
    xmlns:tei="http://www.tei-c.org/ns/1.0"
    exclude-result-prefixes="xs tei"
    version="4.0">
    <xsl:import href="core.xsl"/>
    <xsl:import href="textstructure.xsl"/>
    
    <xsl:output method="html" doctype-system="about:legacy-compat" />
    
    <xsl:template match="/">
        <xsl:apply-templates />
    </xsl:template>
    
</xsl:stylesheet>
<?xml version="1.0" encoding="UTF-8"?>

<!-- 
                4. DEFAULT TEXT STRUCTURE
-->
<xsl:stylesheet xmlns:xsl="http://www.w3.org/1999/XSL/Transform"
    xmlns:xs="http://www.w3.org/2001/XMLSchema"
    xmlns:tei="http://www.tei-c.org/ns/1.0"
    exclude-result-prefixes="xs tei"
    version="4.0">
    
    
    <xsl:template match="tei:TEI">
        <html>
            <head>
                
                <title>
                    <xsl:apply-templates select="tei:teiHeader/tei:fileDesc/tei:titleStmt/tei:title"></xsl:apply-templates>
                </title>
                
            </head>
            <body>
                <xsl:apply-templates select="tei:text" />
            </body>
        </html>
    </xsl:template>
    
    
</xsl:stylesheet>
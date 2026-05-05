<?xml version="1.0" encoding="UTF-8"?>
<xsl:stylesheet xmlns:xsl="http://www.w3.org/1999/XSL/Transform"
    xmlns:xs="http://www.w3.org/2001/XMLSchema"
    xmlns:tei="http://www.tei-c.org/ns/1.0"
    xmlns:xhtml="http://www.w3.org/1999/xhtml"
    exclude-result-prefixes="xs tei xhtml"
    version="4.0">
    
    <xsl:output method="xhtml" encoding="UTF-8" indent="yes" media-type="text/html" />
    <xsl:variable name="page-css" as="xs:string">
        :root {
        --color-bg-primary:     #ffffff;
        --color-bg-secondary:   #f7f7f5;
        --color-text-primary:   #1a1a1a;
        --color-text-secondary: #555555;
        --color-text-tertiary:  #999999;
        --color-border-primary:   #cccccc;
        --color-border-secondary: #dddddd;
        --color-border-tertiary:  #e8e8e6;
        --font-sans:  system-ui, -apple-system, sans-serif;
        --font-serif: Georgia, 'Times New Roman', serif;
        --font-mono:  'Courier New', Courier, monospace;
        --radius-sm: 3px;
        --radius-md: 4px;
        }
        p { line-height: 1.7; margin-bottom: .75em; font-family: var(--font-serif); font-size: 14px; color: var(--color-text-primary); position: relative; }
        
        .tei-del {
        text-decoration: line-through;
        color: red;
        }
        
        .tei-add {
        text-decoration: none;
        color: blue;
        }
        
    </xsl:variable>
    
    <xsl:template match="tei:TEI">
        <html>
            <head>
                
                <title>
                    <xsl:apply-templates select="tei:teiHeader/tei:fileDesc/tei:titleStmt/tei:title"></xsl:apply-templates>
                </title>
                <style><xsl:value-of select="$page-css"/></style>
            </head>
            <body>
                <xsl:apply-templates select="tei:text" />
            </body>
        </html>
    </xsl:template>
    
    <xsl:template match="tei:body">
        <main>
            <xsl:apply-templates />
        </main>
    </xsl:template>

    <xsl:template match="tei:div[@type='textpart' and @subtype='chapter']">
        <xsl:variable name="number" select="@n"/>
        <section class="chapter" aria-label="">
            <xsl:attribute name="aria-label">
                <xsl:value-of select="'Chapter ' || $number"/>
            </xsl:attribute>
            <xsl:apply-templates />
        </section>
    </xsl:template>
    
    <xsl:template match="tei:div[@type='textpart' and @subtype='subchapter']">
        <xsl:variable name="number" select="@n"/>
        <section class="subchapter">
            <xsl:attribute name="aria-label">
                <xsl:value-of select="'Sub Chapter ' || $number"/>
            </xsl:attribute>           
            <xsl:apply-templates />
        </section>
    </xsl:template>
    
    <xsl:template match="tei:p[@rend='align(indent)']">
        <p style="text-indent: 1.5em"><xsl:apply-templates></xsl:apply-templates></p>
    </xsl:template>
    
    <xsl:template match="tei:p">
        <p><xsl:apply-templates></xsl:apply-templates></p>
    </xsl:template>
    
    <xsl:template match="tei:milestone">
        <br/>
        <span><xsl:value-of select="@n"/></span>
    </xsl:template>
    
    <xsl:template match="tei:add">
        <ins class="tei-add"><xsl:apply-templates /></ins>
    </xsl:template>
    
    <xsl:template match="tei:del">
        <del class="tei-del"><xsl:apply-templates /></del>
    </xsl:template>
</xsl:stylesheet>
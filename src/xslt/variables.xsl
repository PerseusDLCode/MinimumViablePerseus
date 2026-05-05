<?xml version="1.0" encoding="UTF-8"?>
<xsl:stylesheet xmlns:xsl="http://www.w3.org/1999/XSL/Transform"
    xmlns:xs="http://www.w3.org/2001/XMLSchema"
    xmlns:tei="http://www.tei-c.org/ns/1.0"
    exclude-result-prefixes="xs tei"
    version="4.0">
    
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
    
</xsl:stylesheet>
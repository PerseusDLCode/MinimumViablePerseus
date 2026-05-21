<?xml version="1.0" encoding="UTF-8"?>
<!--
  tei/perseus_base.xsl
  Rendering library for Perseus base TEI elements.

  All templates operate in mode="tei-to-html". This stylesheet has no root
  template, no page shell, and no knowledge of chunk boundaries.

  Mode contract
  ─────────────
  • mode="tei-to-html" : owned here. Transforms a TEI element into its HTML
    equivalent. Never references $start, $stop, local:before-stop, or
    local:after-start.

  • mode="chunk" : owned by chunker_core.xsl. Container templates in this
    library recurse into children via <xsl:apply-templates mode="chunk"/>
    rather than mode="tei-to-html". This keeps chunk-boundary filtering active
    for every child node, which is required to handle the straddling case: a
    container element that spans a chunk boundary must still suppress content
    on the far side. Tunnel params ($start, $stop, $morph-url) flow through
    implicitly and are never declared by mode="tei-to-html" templates.

  Leaf templates (tei:gap, tei:lb, tei:pb|tei:milestone, text()) produce
  their output directly and do not recurse.

  Import this stylesheet into a driver or chunker. Override individual
  templates for TEI-customization-specific rendering.
-->
<xsl:stylesheet
  xmlns:xsl  ="http://www.w3.org/1999/XSL/Transform"
  xmlns:tei  ="http://www.tei-c.org/ns/1.0"
  xmlns:xs   ="http://www.w3.org/2001/XMLSchema"
  xmlns:local="http://local.functions"
  version="3.0"
  exclude-result-prefixes="tei xs local">

  <xsl:import href="../variables.xsl"/>

  <!-- ============================================================
       Helper functions
       ============================================================ -->

  <!--
    local:strip-punct($s) → xs:string
    Remove leading and trailing punctuation from a token so the bare
    surface form can be submitted to the morphological server.
    Mirrors the same function in tokenize.xsl.
  -->
  <xsl:function name="local:strip-punct" as="xs:string">
    <xsl:param name="s" as="xs:string"/>
    <xsl:variable name="s1"
      select="replace($s,
                '^[.,;:!?·—–(){}\[\]&lt;&gt;⟨⟩&quot;]+', '')"/>
    <xsl:variable name="s2"
      select="replace($s1,
                '[.,;:!?·—–(){}\[\]&lt;&gt;⟨⟩&quot;]+$', '')"/>
    <xsl:variable name="s3" select="replace($s2, &quot;^'+&quot;, '')"/>
    <xsl:variable name="s4" select="replace($s3, &quot;'+$&quot;,  '')"/>
    <xsl:sequence select="$s4"/>
  </xsl:function>

  <!-- ============================================================
       Structural elements
       ============================================================ -->

  <!-- Document body: recurse in tei-to-html (no chunking context at body level) -->
  <xsl:template match="tei:body" mode="tei-to-html">
    <xsl:apply-templates mode="tei-to-html"/>
  </xsl:template>

  <!-- Generic division -->
  <xsl:template match="tei:div" mode="tei-to-html">
    <div><xsl:apply-templates mode="chunk"/></div>
  </xsl:template>

  <!-- Verse group -->
  <xsl:template match="tei:lg" mode="tei-to-html">
    <div class="lg"><xsl:apply-templates mode="chunk"/></div>
  </xsl:template>

  <!-- Section heading -->
  <xsl:template match="tei:head" mode="tei-to-html">
    <h2><xsl:apply-templates mode="chunk"/></h2>
  </xsl:template>

  <!-- Generic paragraph -->
  <xsl:template match="tei:p" mode="tei-to-html">
    <p><xsl:apply-templates mode="chunk"/></p>
  </xsl:template>

  <!--
    Verse line (tei:l → p.line).
    Reads the base CTS URN from ancestor::tei:body/@xml:base.
    Terminates if that attribute is absent — the document must carry
    xml:base on the body element before this stylesheet runs.
    Adds id="l{@n}" on first occurrence to avoid duplicate ids for split lines.
  -->
  <xsl:template match="tei:l" mode="tei-to-html">
    <xsl:variable name="base-urn" select="ancestor::tei:body/@xml:base/string()"/>
    <xsl:if test="$base-urn = ''">
      <xsl:message terminate="yes">
        tei:l encountered but ancestor tei:body has no @xml:base.
        Ensure the document carries xml:base on the body element
        (e.g. &lt;body xml:base="urn:cts:..."&gt;) before running this stylesheet.
      </xsl:message>
    </xsl:if>
    <p class="line" data-n="{@n}"
       data-cts-urn="{concat($base-urn, ':', @n)}">
      <xsl:if test="not(preceding::tei:l[@n = current()/@n])">
        <xsl:attribute name="id" select="concat('l', @n)"/>
      </xsl:if>
      <span class="line-n">
        <xsl:if test="@n castable as xs:integer and xs:integer(@n) mod 5 = 0">
          <xsl:value-of select="@n"/>
        </xsl:if>
      </span>
      <span class="line-text">
        <xsl:apply-templates mode="chunk"/>
      </span>
    </p>
  </xsl:template>

  <!-- Dramatic speech -->
  <xsl:template match="tei:sp" mode="tei-to-html">
    <div class="speech">
      <xsl:if test="@who">
        <xsl:attribute name="data-who" select="@who"/>
      </xsl:if>
      <xsl:apply-templates mode="chunk"/>
    </div>
  </xsl:template>

  <!-- Speaker label -->
  <xsl:template match="tei:speaker" mode="tei-to-html">
    <b class="speaker"><xsl:apply-templates mode="chunk"/></b>
  </xsl:template>

  <!-- Stage direction -->
  <xsl:template match="tei:stage" mode="tei-to-html">
    <div class="stage"><xsl:apply-templates mode="chunk"/></div>
  </xsl:template>

  <!-- ============================================================
       Inline and phrase-level elements
       ============================================================ -->

  <!-- Emphasis -->
  <xsl:template match="tei:emph" mode="tei-to-html">
    <em><xsl:apply-templates mode="chunk"/></em>
  </xsl:template>

  <!-- Inline note; suppress empty notes (footnote anchors with no content) -->
  <xsl:template match="tei:note" mode="tei-to-html">
    <xsl:if test="normalize-space(.) != ''">
      <span class="note"><xsl:apply-templates mode="chunk"/></span>
    </xsl:if>
  </xsl:template>

  <!-- Editorial gap (leaf) -->
  <xsl:template match="tei:gap" mode="tei-to-html">
    <span class="gap">&#x2020;</span>
  </xsl:template>

  <!-- Page breaks and milestones: suppress entirely (leaf) -->
  <xsl:template match="tei:pb | tei:milestone" mode="tei-to-html"/>

  <!-- Block quotation -->
  <xsl:template match="tei:quote" mode="tei-to-html">
    <blockquote><xsl:apply-templates mode="chunk"/></blockquote>
  </xsl:template>

  <!-- Citation with quotation -->
  <xsl:template match="tei:cit" mode="tei-to-html">
    <blockquote class="cit"><xsl:apply-templates mode="chunk"/></blockquote>
  </xsl:template>

  <!-- Foreign-language span -->
  <xsl:template match="tei:foreign" mode="tei-to-html">
    <span>
      <xsl:if test="@xml:lang">
        <xsl:attribute name="lang" select="@xml:lang"/>
      </xsl:if>
      <xsl:apply-templates mode="chunk"/>
    </span>
  </xsl:template>

  <!-- Highlighted text -->
  <xsl:template match="tei:hi" mode="tei-to-html">
    <xsl:choose>
      <xsl:when test="@rend = 'ital' or @rend = 'italic'">
        <em><xsl:apply-templates mode="chunk"/></em>
      </xsl:when>
      <xsl:when test="@rend = 'bold'">
        <strong><xsl:apply-templates mode="chunk"/></strong>
      </xsl:when>
      <xsl:otherwise>
        <span class="hi"><xsl:apply-templates mode="chunk"/></span>
      </xsl:otherwise>
    </xsl:choose>
  </xsl:template>

  <!-- Editorial supplement -->
  <xsl:template match="tei:supplied" mode="tei-to-html">
    <span class="supplied"><xsl:apply-templates mode="chunk"/></span>
  </xsl:template>

  <!-- Editorial deletion -->
  <xsl:template match="tei:del" mode="tei-to-html">
    <del><xsl:apply-templates mode="chunk"/></del>
  </xsl:template>

  <!-- Editorial addition -->
  <xsl:template match="tei:add" mode="tei-to-html">
    <span class="add"><xsl:apply-templates mode="chunk"/></span>
  </xsl:template>

  <!-- Line break within prose (leaf) -->
  <xsl:template match="tei:lb" mode="tei-to-html">
    <br/>
  </xsl:template>

  <!-- Unclear reading -->
  <xsl:template match="tei:unclear" mode="tei-to-html">
    <span class="unclear"><xsl:apply-templates mode="chunk"/></span>
  </xsl:template>

  <!-- ============================================================
       Catch-all and text nodes
       ============================================================ -->

  <!-- Unrecognized elements: fall through to children -->
  <xsl:template match="tei:*" mode="tei-to-html">
    <xsl:apply-templates mode="chunk"/>
  </xsl:template>

  <!--
    Text nodes (leaf).
    When $morph-url is set, each whitespace-delimited token is wrapped in
    an <a class="word"> linking to the morphological server.  The bare
    surface form (punctuation stripped) is used as the lookup key; the
    original raw token (with punctuation) is the visible link text.
    Whitespace-only nodes pass through unchanged in both modes.
  -->
  <xsl:template match="text()" mode="tei-to-html">
    <xsl:param name="morph-url" tunnel="yes" as="xs:string" select="''"/>
    <xsl:choose>
      <xsl:when test="$morph-url != ''">
        <xsl:variable name="tei-lang"
          select="(ancestor::*[@xml:lang])[1]/@xml:lang"/>
        <xsl:variable name="morph-lang" select="
          if      ($tei-lang = 'lat') then 'la'
          else if ($tei-lang = 'grc') then 'grc'
          else ''
        "/>
        <xsl:variable name="normalized" select="normalize-space(.)"/>
        <xsl:if test="$normalized != ''">
          <xsl:if test="matches(., '^\s')">
            <xsl:text> </xsl:text>
          </xsl:if>
          <xsl:for-each select="tokenize($normalized, '\s+')">
            <xsl:variable name="raw"     select="."/>
            <xsl:variable name="surface" select="local:strip-punct($raw)"/>
            <xsl:choose>
              <xsl:when test="$morph-lang != '' and $surface != ''">
                <a href="{$morph-url}/morph?form={encode-for-uri($surface)}&amp;lang={$morph-lang}"
                   class="word"><xsl:value-of select="$raw"/></a>
              </xsl:when>
              <xsl:otherwise>
                <xsl:value-of select="$raw"/>
              </xsl:otherwise>
            </xsl:choose>
            <xsl:if test="position() != last()">
              <xsl:text> </xsl:text>
            </xsl:if>
          </xsl:for-each>
          <xsl:if test="matches(., '\s$')">
            <xsl:text> </xsl:text>
          </xsl:if>
        </xsl:if>
      </xsl:when>
      <xsl:otherwise>
        <xsl:copy/>
      </xsl:otherwise>
    </xsl:choose>
  </xsl:template>

</xsl:stylesheet>

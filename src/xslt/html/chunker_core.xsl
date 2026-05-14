<?xml version="1.0" encoding="UTF-8"?>
<!--
  chunker_core.xsl
  Base stylesheet for converting TEI content to HTML, chunk by chunk.

  All element templates operate in "chunk" mode and receive two tunnel
  parameters:

    $stop     (node()?)   — the milestone that ends this chunk, or the empty
                            sequence for the final chunk (no stop).

    $base-urn (xs:string?) — the CTS base URN for the work, or empty sequence
                             if the document has none.

  Import this stylesheet and add or override templates to handle TEI
  customizations not covered here.
-->
<xsl:stylesheet
  xmlns:xsl  ="http://www.w3.org/1999/XSL/Transform"
  xmlns:tei  ="http://www.tei-c.org/ns/1.0"
  xmlns:xs   ="http://www.w3.org/2001/XMLSchema"
  xmlns:local="http://local.functions"
  version="3.0"
  exclude-result-prefixes="tei xs local">

  <!-- ============================================================
       Shared page CSS (used by generate_chunks.xsl and generate_div_chunks.xsl)
       ============================================================ -->

  <xsl:variable name="page-css" as="xs:string">body         { font-family: serif; max-width: 48em; margin: 0 auto; padding: 1em 2em }
.site-header { border-bottom: 1px solid #ccc; margin-bottom: 1.5em;
               padding-bottom: .5em; font-size: .9em; color: #555 }
.site-header a { text-decoration: none; font-weight: bold; color: inherit }
.chunk-nav   { display: flex; justify-content: space-between; font-size: .9em;
               margin-bottom: 1.5em }
.chunk-nav a { margin-right: 1em }
h1           { font-size: 1em; color: #555; margin-bottom: .25em }
.speech      { margin: 1em 0 }
.speaker     { font-weight: bold; display: block; margin-bottom: .25em }
.line        { margin: .1em 0; padding-left: 2em }
.gap         { color: #888; font-style: italic }
.note        { border-bottom: 1px dotted #888 }
.toc         { padding-left: 1.5em; line-height: 1.8 }
.site-footer { border-top: 1px solid #eee; margin-top: 2em; padding-top: .5em;
               font-size: .8em; color: #888; text-align: center }
a.word       { color: inherit; text-decoration: none; border-bottom: 1px dotted #aaa }
a.word:hover { border-bottom-style: solid }</xsl:variable>

  <!-- ============================================================
       Helper functions
       ============================================================ -->

  <!--
    local:before-stop($node, $stop) → xs:boolean
    True when $node should be included in the current chunk.

    • If $stop is empty (last chunk), always true.
    • If $node IS the stop milestone, false.
    • If $node starts after the stop in document order, false.
    • If $node CONTAINS the stop as a descendant (straddles the boundary),
      true — the template renders the element's open/close tags and
      lets children suppress themselves individually.
  -->
  <xsl:function name="local:before-stop" as="xs:boolean">
    <xsl:param name="node" as="node()"/>
    <xsl:param name="stop" as="node()?"/>
    <xsl:sequence select="
      empty($stop)
      or (not($node is $stop) and not($node &gt;&gt; $stop))
    "/>
  </xsl:function>

  <!--
    local:after-start($node, $start) → xs:boolean
    True when $node should be included as the start of the current chunk.

    • If $start is empty (no start filtering), always true.
    • If $node comes after $start in document order, true.
    • If $node IS an element that contains $start as a descendant (straddles
      the start boundary), true — the template renders the element's open/close
      tags and lets children suppress themselves individually via their own
      local:after-start check.
    • Otherwise (node precedes start and does not contain it), false.
  -->
  <xsl:function name="local:after-start" as="xs:boolean">
    <xsl:param name="node"  as="node()"/>
    <xsl:param name="start" as="node()?"/>
    <xsl:sequence select="
      empty($start)
      or ($node >> $start)
      or ($node instance of element()
          and exists($start/ancestor::* intersect $node))
    "/>
  </xsl:function>

  <!--
    local:extract-base-urn($root) → xs:string?
    Returns the CTS base URN from div[@type='edition']/@n, or empty sequence.
  -->
  <xsl:function name="local:extract-base-urn" as="xs:string?">
    <xsl:param name="root" as="node()"/>
    <xsl:sequence select="($root//tei:div[@type='edition']/@n/string())[1]"/>
  </xsl:function>

  <!--
    local:chunk-cts-range($top, $stop, $base-urn) → xs:string?
    Returns the CTS range URN for all tei:l elements in the chunk,
    e.g. "urn:cts:latinLit:phi1017.phi007.perseus-lat2:57-107".
    Returns empty sequence when there are no lines or no base URN.
  -->
  <xsl:function name="local:chunk-cts-range" as="xs:string?">
    <xsl:param name="top"      as="element()*"/>
    <xsl:param name="stop"     as="node()?"/>
    <xsl:param name="base-urn" as="xs:string?"/>
    <xsl:if test="exists($base-urn)">
      <xsl:variable name="ns" as="xs:string*"
        select="$top//tei:l[local:before-stop(., $stop)]/@n/string()"/>
      <xsl:if test="exists($ns)">
        <xsl:sequence select="
          if (head($ns) eq $ns[last()])
          then concat($base-urn, ':', head($ns))
          else concat($base-urn, ':', head($ns), '-', $ns[last()])
        "/>
      </xsl:if>
    </xsl:if>
  </xsl:function>


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
       Element templates — chunk mode
       ============================================================ -->

  <!-- Dramatic speech (tei:sp → div.speech) -->
  <xsl:template match="tei:sp" mode="chunk">
    <xsl:param name="start" tunnel="yes" as="node()?"/>
    <xsl:param name="stop"  tunnel="yes" as="node()?"/>
    <xsl:if test="local:after-start(., $start) and local:before-stop(., $stop)">
      <div class="speech">
        <xsl:if test="@who">
          <xsl:attribute name="data-who" select="@who"/>
        </xsl:if>
        <xsl:apply-templates mode="chunk"/>
      </div>
    </xsl:if>
  </xsl:template>

  <!-- Speaker label (tei:speaker → b.speaker) -->
  <xsl:template match="tei:speaker" mode="chunk">
    <xsl:param name="start" tunnel="yes" as="node()?"/>
    <xsl:param name="stop"  tunnel="yes" as="node()?"/>
    <xsl:if test="local:after-start(., $start) and local:before-stop(., $stop)">
      <b class="speaker"><xsl:apply-templates mode="chunk"/></b>
    </xsl:if>
  </xsl:template>

  <!--
    Verse line (tei:l → p.line).
    Adds id="l{@n}" and data-cts-urn when a base URN is present.
    The id is omitted on any line whose @n already appeared earlier in
    the document, avoiding duplicate ids for split lines.
  -->
  <xsl:template match="tei:l" mode="chunk">
    <xsl:param name="start"    tunnel="yes" as="node()?"/>
    <xsl:param name="stop"     tunnel="yes" as="node()?"/>
    <xsl:param name="base-urn" tunnel="yes" as="xs:string?"/>
    <xsl:if test="local:after-start(., $start) and local:before-stop(., $stop)">
      <p class="line" data-n="{@n}">
        <xsl:if test="exists($base-urn)">
          <xsl:attribute name="data-cts-urn" select="concat($base-urn, ':', @n)"/>
          <xsl:if test="not(preceding::tei:l[@n = current()/@n])">
            <xsl:attribute name="id" select="concat('l', @n)"/>
          </xsl:if>
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
    </xsl:if>
  </xsl:template>

  <!-- Generic paragraph (tei:p → p) -->
  <xsl:template match="tei:p" mode="chunk">
    <xsl:param name="start" tunnel="yes" as="node()?"/>
    <xsl:param name="stop"  tunnel="yes" as="node()?"/>
    <xsl:if test="local:after-start(., $start) and local:before-stop(., $stop)">
      <p><xsl:apply-templates mode="chunk"/></p>
    </xsl:if>
  </xsl:template>

  <!-- Generic division (tei:div → div) -->
  <xsl:template match="tei:div" mode="chunk">
    <xsl:param name="start" tunnel="yes" as="node()?"/>
    <xsl:param name="stop"  tunnel="yes" as="node()?"/>
    <xsl:if test="local:after-start(., $start) and local:before-stop(., $stop)">
      <div><xsl:apply-templates mode="chunk"/></div>
    </xsl:if>
  </xsl:template>

  <!-- Emphasis (tei:emph → em) -->
  <xsl:template match="tei:emph" mode="chunk">
    <xsl:param name="start" tunnel="yes" as="node()?"/>
    <xsl:param name="stop"  tunnel="yes" as="node()?"/>
    <xsl:if test="local:after-start(., $start) and local:before-stop(., $stop)">
      <em><xsl:apply-templates mode="chunk"/></em>
    </xsl:if>
  </xsl:template>

  <!-- Inline note (tei:note → span.note).
       Empty notes (<note target="..."/>) are footnote anchors with no content;
       the note text lives in a separate <note n="..."> elsewhere in the document.
       Suppress them to avoid empty spans in the output. -->
  <xsl:template match="tei:note" mode="chunk">
    <xsl:param name="start" tunnel="yes" as="node()?"/>
    <xsl:param name="stop"  tunnel="yes" as="node()?"/>
    <xsl:if test="local:after-start(., $start) and local:before-stop(., $stop)
                  and normalize-space(.) != ''">
      <span class="note"><xsl:apply-templates mode="chunk"/></span>
    </xsl:if>
  </xsl:template>

  <!-- Editorial gap (tei:gap → span.gap with dagger marker) -->
  <xsl:template match="tei:gap" mode="chunk">
    <xsl:param name="start" tunnel="yes" as="node()?"/>
    <xsl:param name="stop"  tunnel="yes" as="node()?"/>
    <xsl:if test="local:after-start(., $start) and local:before-stop(., $stop)">
      <span class="gap">&#x2020;</span>
    </xsl:if>
  </xsl:template>

  <!-- Page breaks and milestones: suppress entirely.
       Because text nodes are separate nodes in XPath (unlike lxml tails),
       no explicit tail-rescue is needed — adjacent text nodes are handled
       by the text() template below. -->
  <xsl:template match="tei:pb | tei:milestone" mode="chunk"/>

  <!-- Section heading (tei:head → h2) -->
  <xsl:template match="tei:head" mode="chunk">
    <xsl:param name="start" tunnel="yes" as="node()?"/>
    <xsl:param name="stop"  tunnel="yes" as="node()?"/>
    <xsl:if test="local:after-start(., $start) and local:before-stop(., $stop)">
      <h2><xsl:apply-templates mode="chunk"/></h2>
    </xsl:if>
  </xsl:template>

  <!-- Block quotation (tei:quote → blockquote) -->
  <xsl:template match="tei:quote" mode="chunk">
    <xsl:param name="start" tunnel="yes" as="node()?"/>
    <xsl:param name="stop"  tunnel="yes" as="node()?"/>
    <xsl:if test="local:after-start(., $start) and local:before-stop(., $stop)">
      <blockquote><xsl:apply-templates mode="chunk"/></blockquote>
    </xsl:if>
  </xsl:template>

  <!-- Citation with quotation (tei:cit → blockquote.cit) -->
  <xsl:template match="tei:cit" mode="chunk">
    <xsl:param name="start" tunnel="yes" as="node()?"/>
    <xsl:param name="stop"  tunnel="yes" as="node()?"/>
    <xsl:if test="local:after-start(., $start) and local:before-stop(., $stop)">
      <blockquote class="cit"><xsl:apply-templates mode="chunk"/></blockquote>
    </xsl:if>
  </xsl:template>

  <!-- Foreign-language span (tei:foreign → span[lang]) -->
  <xsl:template match="tei:foreign" mode="chunk">
    <xsl:param name="start" tunnel="yes" as="node()?"/>
    <xsl:param name="stop"  tunnel="yes" as="node()?"/>
    <xsl:if test="local:after-start(., $start) and local:before-stop(., $stop)">
      <span>
        <xsl:if test="@xml:lang">
          <xsl:attribute name="lang" select="@xml:lang"/>
        </xsl:if>
        <xsl:apply-templates mode="chunk"/>
      </span>
    </xsl:if>
  </xsl:template>

  <!-- Highlighted text (tei:hi → em for italic, otherwise span.hi) -->
  <xsl:template match="tei:hi" mode="chunk">
    <xsl:param name="start" tunnel="yes" as="node()?"/>
    <xsl:param name="stop"  tunnel="yes" as="node()?"/>
    <xsl:if test="local:after-start(., $start) and local:before-stop(., $stop)">
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
    </xsl:if>
  </xsl:template>

  <!-- Editorial supplement (tei:supplied → span.supplied) -->
  <xsl:template match="tei:supplied" mode="chunk">
    <xsl:param name="start" tunnel="yes" as="node()?"/>
    <xsl:param name="stop"  tunnel="yes" as="node()?"/>
    <xsl:if test="local:after-start(., $start) and local:before-stop(., $stop)">
      <span class="supplied"><xsl:apply-templates mode="chunk"/></span>
    </xsl:if>
  </xsl:template>

  <!-- Editorial deletion (tei:del → del) -->
  <xsl:template match="tei:del" mode="chunk">
    <xsl:param name="start" tunnel="yes" as="node()?"/>
    <xsl:param name="stop"  tunnel="yes" as="node()?"/>
    <xsl:if test="local:after-start(., $start) and local:before-stop(., $stop)">
      <del><xsl:apply-templates mode="chunk"/></del>
    </xsl:if>
  </xsl:template>

  <!-- Editorial addition (tei:add → span.add) -->
  <xsl:template match="tei:add" mode="chunk">
    <xsl:param name="start" tunnel="yes" as="node()?"/>
    <xsl:param name="stop"  tunnel="yes" as="node()?"/>
    <xsl:if test="local:after-start(., $start) and local:before-stop(., $stop)">
      <span class="add"><xsl:apply-templates mode="chunk"/></span>
    </xsl:if>
  </xsl:template>

  <!-- Line break within prose (tei:lb → br) -->
  <xsl:template match="tei:lb" mode="chunk">
    <xsl:param name="start" tunnel="yes" as="node()?"/>
    <xsl:param name="stop"  tunnel="yes" as="node()?"/>
    <xsl:if test="local:after-start(., $start) and local:before-stop(., $stop)">
      <br/>
    </xsl:if>
  </xsl:template>

  <!-- Unclear reading (tei:unclear → span.unclear) -->
  <xsl:template match="tei:unclear" mode="chunk">
    <xsl:param name="start" tunnel="yes" as="node()?"/>
    <xsl:param name="stop"  tunnel="yes" as="node()?"/>
    <xsl:if test="local:after-start(., $start) and local:before-stop(., $stop)">
      <span class="unclear"><xsl:apply-templates mode="chunk"/></span>
    </xsl:if>
  </xsl:template>

  <!-- Catch-all: unrecognized elements fall through to their text content.
       This prevents silent content loss when encountering TEI elements not
       yet mapped to HTML equivalents.  Named templates above take
       precedence; this template fires only for everything else. -->
  <xsl:template match="*" mode="chunk">
    <xsl:param name="start" tunnel="yes" as="node()?"/>
    <xsl:param name="stop"  tunnel="yes" as="node()?"/>
    <xsl:if test="local:after-start(., $start) and local:before-stop(., $stop)">
      <xsl:apply-templates mode="chunk"/>
    </xsl:if>
  </xsl:template>

  <!--
    Text nodes: copy only when within the start/stop range.
    When $morph-url is set, each whitespace-delimited token is wrapped in
    an <a class="word"> linking to the morphological server.  The bare
    surface form (punctuation stripped) is used as the lookup key; the
    original raw token (with punctuation) is the visible link text.
    Whitespace-only text nodes pass through unchanged in both modes.
  -->
  <xsl:template match="text()" mode="chunk">
    <xsl:param name="start"     tunnel="yes" as="node()?"/>
    <xsl:param name="stop"      tunnel="yes" as="node()?"/>
    <xsl:param name="morph-url" tunnel="yes" as="xs:string" select="''"/>
    <xsl:if test="local:after-start(., $start) and local:before-stop(., $stop)">
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
    </xsl:if>
  </xsl:template>

</xsl:stylesheet>

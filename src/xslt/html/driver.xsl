<?xml version="1.0" encoding="UTF-8"?>
<!--
  driver.xsl
  Composition root and page assembler for the Perseus TEI-to-HTML pipeline.

  Architecture
  ────────────
  Chunkers (generate_chunks.xsl, generate_div_chunks.xsl) are pure iterators:
  they traverse the document, compute per-chunk metadata, and call the named
  template page:render defined here.  This driver owns the page shell and all
  enrichment parameters; the chunkers have no knowledge of $morph-url,
  $citation-table, or any other rendering enrichment.

  Enrichment parameters declared here:
    $morph-url       — when non-empty, word tokens are linked to a morphological
                       server.  Consumed by the text() template in perseus_base.xsl.
    $citation-table  — path/URL of a compiled citation link table.  Loaded via
                       document() and injected as $citation-map.  Not yet designed;
                       present to stabilise the driver interface.

  Dispatch parameters:
    $chunk-strategy  — 'milestone' | 'div' | 'auto' (default).
                       'auto' selects milestone chunking when the document has
                       milestones of $chunk-unit, otherwise div chunking.
    $chunk-unit      — passed through to the selected chunker.

  Usage:
    generate-html-from-tei source.xml src/xslt/html/driver.xsl
        -output-dir /tmp/out -param chunk-unit=card
    generate-html-from-tei source.xml src/xslt/html/driver.xsl
        -output-dir /tmp/out -param chunk-unit=chapter -param chunk-strategy=div
-->
<xsl:stylesheet
  xmlns:xsl     ="http://www.w3.org/1999/XSL/Transform"
  xmlns:tei     ="http://www.tei-c.org/ns/1.0"
  xmlns:xs      ="http://www.w3.org/2001/XMLSchema"
  xmlns:local   ="http://local.functions"
  xmlns:page    ="http://mvp.perseus.org/page"
  xmlns:chunker ="http://mvp.perseus.org/chunker"
  version="3.0"
  exclude-result-prefixes="tei xs local page chunker">

  <!-- Import both chunkers.  Both transitively import chunker_core.xsl and
       tei/perseus_base.xsl.  This driver's match="/" overrides both chunkers'
       match="/" templates (higher import precedence). -->
  <xsl:import href="generate_chunks.xsl"/>
  <xsl:import href="generate_div_chunks.xsl"/>

  <xsl:output method="html" html-version="5" indent="yes"/>

  <!-- ============================================================
       Parameters
       ============================================================ -->

  <!-- Enrichment parameters — owned exclusively by the driver -->
  <xsl:param name="morph-url"      as="xs:string" select="''"/>
  <xsl:param name="citation-table" as="xs:string" select="''"/>

  <!-- Structural parameters — redeclared here for documentation;
       the chunkers also declare these and will receive command-line values. -->
  <xsl:param name="output-dir"     as="xs:string" select="'.'"/>
  <xsl:param name="catalog-url"    as="xs:string" select="'/index.html'"/>
  <xsl:param name="chunk-unit"     as="xs:string" select="'card'"/>

  <!-- Dispatch -->
  <xsl:param name="chunk-strategy" as="xs:string" select="'auto'"/>


  <!-- ============================================================
       Root template — dispatch to appropriate chunker
       ============================================================ -->

  <xsl:template match="/">
    <xsl:choose>
      <xsl:when test="$chunk-strategy = 'div'">
        <xsl:call-template name="chunker:run-divs"/>
      </xsl:when>
      <xsl:when test="$chunk-strategy = 'milestone'">
        <xsl:call-template name="chunker:run-milestones"/>
      </xsl:when>
      <xsl:otherwise>
        <!-- auto: prefer milestone if the document has milestones of the given unit -->
        <xsl:choose>
          <xsl:when test="exists(//tei:milestone[@unit = $chunk-unit])">
            <xsl:call-template name="chunker:run-milestones"/>
          </xsl:when>
          <xsl:otherwise>
            <xsl:call-template name="chunker:run-divs"/>
          </xsl:otherwise>
        </xsl:choose>
      </xsl:otherwise>
    </xsl:choose>
  </xsl:template>


  <!-- ============================================================
       page:render
       Called once per chunk by the active chunker.  Constructs the
       full HTML page and injects enrichment tunnel parameters.

       $chunk     — node()* : content to render (inter-milestone elements
                    for milestone chunking; $div/node() for div chunking)
       $start     — node()? : start milestone, or empty (div chunking)
       $stop      — node()? : stop milestone, or empty (div chunking / last chunk)
       $work-title, $author, $doc-lang, $home-url — document metadata
       $chunk-label — human-readable label, e.g. "card 57"
       $chunk-n   — @n value of current chunk element
       $cts-range — xs:string? : CTS range URN, or empty
       $file-name, $prev-file, $next-file — navigation
       $all-chunks — sequence of maps {n, pos, file} for the sidebar TOC
       ============================================================ -->

  <xsl:template name="page:render">
    <xsl:param name="chunk"       as="node()*"/>
    <xsl:param name="start"       as="node()?"   select="()"/>
    <xsl:param name="stop"        as="node()?"   select="()"/>
    <xsl:param name="work-title"  as="xs:string"/>
    <xsl:param name="author"      as="xs:string"/>
    <xsl:param name="doc-lang"    as="xs:string"/>
    <xsl:param name="home-url"    as="xs:string"/>
    <xsl:param name="chunk-label" as="xs:string"/>
    <xsl:param name="chunk-n"     as="xs:string"/>
    <xsl:param name="cts-range"   as="xs:string?"/>
    <xsl:param name="file-name"   as="xs:string"/>
    <xsl:param name="prev-file"   as="xs:string?"/>
    <xsl:param name="next-file"   as="xs:string?"/>
    <xsl:param name="all-chunks"  as="map(*)*"/>

    <!-- Load citation map if a table path was provided -->
    <xsl:variable name="citation-map"
      select="if ($citation-table != '') then document($citation-table) else ()"/>

    <html>
      <xsl:if test="$doc-lang != ''">
        <xsl:attribute name="lang" select="$doc-lang"/>
      </xsl:if>
      <head>
        <meta charset="utf-8"/>
        <meta name="viewport" content="width=device-width, initial-scale=1"/>
        <title>
          <xsl:value-of select="$work-title"/>
          <xsl:text> &#x2014; </xsl:text>
          <xsl:value-of select="$chunk-label"/>
          <xsl:text> | Perseus</xsl:text>
        </title>
        <xsl:if test="exists($cts-range)">
          <meta name="dc.identifier" content="{$cts-range}"/>
        </xsl:if>
        <style><xsl:value-of select="$page-css"/></style>
      </head>
      <body>
        <div class="perseus-shell">
          <xsl:call-template name="page:header">
            <xsl:with-param name="catalog-url" select="$catalog-url"/>
            <xsl:with-param name="home-url"    select="$home-url"/>
          </xsl:call-template>
          <div class="main-area">
            <xsl:call-template name="page:sidebar-left">
              <xsl:with-param name="all-chunks"  select="$all-chunks"/>
              <xsl:with-param name="chunk-n"     select="$chunk-n"/>
              <xsl:with-param name="work-title"  select="$work-title"/>
              <xsl:with-param name="author"      select="$author"/>
              <xsl:with-param name="doc-lang"    select="$doc-lang"/>
            </xsl:call-template>
            <main class="center-col">
              <xsl:call-template name="page:passage-header">
                <xsl:with-param name="author"      select="$author"/>
                <xsl:with-param name="work-title"  select="$work-title"/>
                <xsl:with-param name="chunk-label" select="$chunk-label"/>
                <xsl:with-param name="prev-file"   select="$prev-file"/>
                <xsl:with-param name="next-file"   select="$next-file"/>
                <xsl:with-param name="cts-range"   select="$cts-range"/>
              </xsl:call-template>
              <!-- CSS-only line-number toggle; must precede .text-body -->
              <input type="checkbox" class="toggle-input" id="toggle-linenum" checked="checked"/>
              <div class="text-body">
                <xsl:apply-templates select="$chunk" mode="chunk">
                  <xsl:with-param name="start"        tunnel="yes" select="$start"/>
                  <xsl:with-param name="stop"         tunnel="yes" select="$stop"/>
                  <xsl:with-param name="morph-url"    tunnel="yes" select="$morph-url"/>
                  <xsl:with-param name="citation-map" tunnel="yes" select="$citation-map"/>
                </xsl:apply-templates>
              </div>
              <xsl:call-template name="page:passage-footer"/>
            </main>
            <xsl:call-template name="page:sidebar-right"/>
          </div>
          <xsl:call-template name="page:footer">
            <xsl:with-param name="catalog-url" select="$catalog-url"/>
          </xsl:call-template>
        </div>
      </body>
    </html>
  </xsl:template>


  <!-- ============================================================
       page:header
       ============================================================ -->

  <xsl:template name="page:header">
    <xsl:param name="catalog-url" as="xs:string"/>
    <xsl:param name="home-url"    as="xs:string"/>
    <header class="site-header">
      <div class="header-logo">Perseus <span>Digital Library</span></div>
      <nav class="header-nav">
        <a href="{$catalog-url}">&#x2190; Catalog</a>
        <a href="{$home-url}">Home</a>
      </nav>
    </header>
  </xsl:template>


  <!-- ============================================================
       page:footer
       ============================================================ -->

  <xsl:template name="page:footer">
    <xsl:param name="catalog-url" as="xs:string"/>
    <footer class="site-footer">
      <div class="footer-text">Perseus Digital Library &#xB7; Tufts University</div>
      <div class="footer-links">
        <a href="{$catalog-url}">&#x2190; Catalog</a>
        <a href="toc.html">Contents</a>
      </div>
    </footer>
  </xsl:template>


  <!-- ============================================================
       page:sidebar-left
       ============================================================ -->

  <xsl:template name="page:sidebar-left">
    <xsl:param name="all-chunks"  as="map(*)*"/>
    <xsl:param name="chunk-n"     as="xs:string"/>
    <xsl:param name="work-title"  as="xs:string"/>
    <xsl:param name="author"      as="xs:string"/>
    <xsl:param name="doc-lang"    as="xs:string"/>
    <xsl:variable name="base-urn" select="local:extract-base-urn(/)"/>
    <aside class="sidebar">
      <details open="open">
        <summary>Contents</summary>
        <div class="panel-body">
          <ol class="toc-list">
            <xsl:for-each select="$all-chunks">
              <li>
                <xsl:if test=".('n') = $chunk-n">
                  <xsl:attribute name="class">current</xsl:attribute>
                </xsl:if>
                <a href="{.('file')}">
                  <span class="toc-dot"/>
                  <xsl:value-of select="concat($chunk-unit, ' ', .('n'))"/>
                </a>
              </li>
            </xsl:for-each>
          </ol>
        </div>
      </details>
      <details>
        <summary>Work info</summary>
        <div class="panel-body">
          <div class="meta-row">
            <span class="meta-label">Work</span>
            <span class="meta-value"><xsl:value-of select="$work-title"/></span>
          </div>
          <xsl:if test="$author != ''">
            <div class="meta-row">
              <span class="meta-label">Author</span>
              <span class="meta-value"><xsl:value-of select="$author"/></span>
            </div>
          </xsl:if>
          <xsl:if test="$doc-lang != ''">
            <div class="meta-row">
              <span class="meta-label">Language</span>
              <span class="meta-value"><xsl:value-of select="$doc-lang"/></span>
            </div>
          </xsl:if>
          <xsl:if test="exists($base-urn)">
            <div class="meta-row">
              <span class="meta-label">URN</span>
              <span class="meta-value"><xsl:value-of select="$base-urn"/></span>
            </div>
          </xsl:if>
        </div>
      </details>
      <details>
        <summary>Other versions</summary>
        <div class="panel-body">
          <p class="placeholder-msg">Other editions available via the CTS resolver.</p>
        </div>
      </details>
    </aside>
  </xsl:template>


  <!-- ============================================================
       page:sidebar-right
       ============================================================ -->

  <xsl:template name="page:sidebar-right">
    <aside class="sidebar right">
      <details open="open">
        <summary>Vocabulary</summary>
        <div class="panel-body">
          <p class="placeholder-msg">Vocabulary lookup coming in a future release.</p>
        </div>
      </details>
      <details>
        <summary>Commentary</summary>
        <div class="panel-body">
          <p class="placeholder-msg">Commentary coming in a future release.</p>
        </div>
      </details>
      <details>
        <summary>Word study</summary>
        <div class="panel-body">
          <p class="placeholder-msg">Morphological analysis coming in a future release.</p>
        </div>
      </details>
    </aside>
  </xsl:template>


  <!-- ============================================================
       page:passage-header
       ============================================================ -->

  <xsl:template name="page:passage-header">
    <xsl:param name="author"      as="xs:string"/>
    <xsl:param name="work-title"  as="xs:string"/>
    <xsl:param name="chunk-label" as="xs:string"/>
    <xsl:param name="prev-file"   as="xs:string?"/>
    <xsl:param name="next-file"   as="xs:string?"/>
    <xsl:param name="cts-range"   as="xs:string?"/>
    <div class="passage-header">
      <div class="passage-breadcrumb">
        <xsl:if test="$author != ''">
          <xsl:value-of select="$author"/>
          <xsl:text> &#xB7; </xsl:text>
        </xsl:if>
        <strong><xsl:value-of select="$work-title"/></strong>
        <xsl:text> &#xB7; </xsl:text>
        <xsl:value-of select="$chunk-label"/>
      </div>
      <div class="passage-nav">
        <xsl:if test="exists($prev-file)">
          <a href="{$prev-file}" class="nav-btn">&#x2190; prev</a>
        </xsl:if>
        <xsl:if test="exists($cts-range)">
          <span class="urn-chip"><xsl:value-of select="$cts-range"/></span>
        </xsl:if>
        <xsl:if test="exists($next-file)">
          <a href="{$next-file}" class="nav-btn">next &#x2192;</a>
        </xsl:if>
      </div>
    </div>
  </xsl:template>


  <!-- ============================================================
       page:passage-footer
       ============================================================ -->

  <xsl:template name="page:passage-footer">
    <div class="passage-footer">
      <div class="display-opts">
        <span class="opt-label">Show:</span>
        <label class="opt-toggle" for="toggle-linenum">line numbers</label>
      </div>
    </div>
  </xsl:template>

</xsl:stylesheet>

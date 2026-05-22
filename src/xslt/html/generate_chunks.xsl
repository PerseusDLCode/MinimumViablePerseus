<?xml version="1.0" encoding="UTF-8"?>
<!--
  generate_chunks.xsl
  Milestone-based batch generator: produces one HTML file per milestone chunk,
  a toc.html, and index.json.

  This stylesheet is a pure iterator.  It traverses the document, identifies
  chunk boundaries, computes per-chunk metadata, and delegates page assembly to
  the named template page:render defined by the importing driver.  It has no
  knowledge of enrichment parameters ($morph-url, $citation-table, etc.).

  Parameters:
    chunk-unit  (xs:string)  milestone/@unit value to chunk on  [default: 'card']
    output-dir  (xs:string)  directory to write output files to [default: '.']
    catalog-url (xs:string)  relative URL for the Catalog nav link

  Output files are named  {chunk-unit}_{position}.html  (e.g. card_57.html).

  Entry point: use driver.xsl, not this file directly.
    generate-html-from-tei source.xml src/xslt/html/driver.xsl \
        -output-dir /tmp/out -param chunk-unit=card
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

  <xsl:import href="chunker_core.xsl"/>

  <xsl:output method="html" html-version="5" indent="yes"/>

  <!-- ============================================================
       Parameters
       ============================================================ -->

  <xsl:param name="chunk-unit"  as="xs:string" select="'card'"/>
  <xsl:param name="output-dir"  as="xs:string" select="'.'"/>
  <xsl:param name="catalog-url" as="xs:string" select="'/index.html'"/>


  <!-- ============================================================
       Entry point — shim for standalone/fallback use
       ============================================================ -->

  <xsl:template match="/">
    <xsl:call-template name="chunker:run-milestones"/>
  </xsl:template>


  <!-- ============================================================
       chunker:run-milestones
       Core iteration over milestone elements.  Calls page:render
       once per chunk; page:render must be defined by the driver.
       ============================================================ -->

  <xsl:template name="chunker:run-milestones">
    <xsl:variable name="base-urn"   select="local:extract-base-urn(.)"/>
    <xsl:variable name="work-title" select="string((//tei:titleStmt/tei:title)[1])"/>
    <xsl:variable name="author"     select="string((//tei:titleStmt/tei:author)[1])"/>
    <xsl:variable name="doc-lang"   select="string((//tei:text/@xml:lang)[1])"/>
    <xsl:variable name="milestones" select="//tei:milestone[@unit = $chunk-unit]"/>
    <xsl:variable name="home-url"
      select="replace($catalog-url, 'catalog/[^/]+\.html$', 'index.html')"/>

    <xsl:if test="empty($milestones)">
      <xsl:message terminate="yes">
        No milestone elements found with unit="<xsl:value-of select="$chunk-unit"/>".
        Check the chunk-unit parameter.
      </xsl:message>
    </xsl:if>

    <!-- Pre-collect lightweight chunk metadata so every result-document
         can render a complete sidebar TOC without a second traversal. -->
    <xsl:variable name="all-chunks" as="map(*)*">
      <xsl:for-each select="$milestones">
        <xsl:sequence select="map {
          'n'   : string(@n),
          'pos' : position(),
          'file': concat($chunk-unit, '_', position(), '.html')
        }"/>
      </xsl:for-each>
    </xsl:variable>

    <!--
      xsl:iterate lets us accumulate index metadata across chunks and
      write index.json and toc.html in xsl:on-completion once all chunks are done.
    -->
    <xsl:iterate select="$milestones">
      <xsl:param name="index-entries" as="map(*)*" select="()"/>

      <!-- xsl:on-completion must appear before any content instructions -->
      <xsl:on-completion>
        <xsl:result-document
          href  ="{$output-dir}/index.json"
          method="json"
          indent="yes">
          <xsl:sequence select="map {
            'base_urn': ($base-urn, '')[1],
            'title'   : $work-title,
            'chunks'  : array { $index-entries }
          }"/>
        </xsl:result-document>

        <!-- TOC page -->
        <xsl:result-document
          href        ="{$output-dir}/toc.html"
          method      ="html"
          html-version="5"
          indent      ="yes">
          <html>
            <xsl:if test="$doc-lang != ''">
              <xsl:attribute name="lang" select="$doc-lang"/>
            </xsl:if>
            <head>
              <meta charset="utf-8"/>
              <meta name="viewport" content="width=device-width, initial-scale=1"/>
              <title><xsl:value-of select="$work-title"/> &#x2014; Contents | Perseus</title>
              <style><xsl:value-of select="$page-css"/></style>
            </head>
            <body>
              <div class="perseus-shell">
                <header class="site-header">
                  <div class="header-logo">Perseus <span>Digital Library</span></div>
                  <nav class="header-nav">
                    <a href="{$catalog-url}">&#x2190; Catalog</a>
                    <a href="{$home-url}">Home</a>
                  </nav>
                </header>
                <div class="main-area">
                  <aside class="sidebar">
                    <details open="open">
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
                      </div>
                    </details>
                  </aside>
                  <main class="center-col">
                    <div class="passage-header">
                      <div class="passage-breadcrumb">
                        <xsl:if test="$author != ''">
                          <xsl:value-of select="$author"/>
                          <xsl:text> &#xB7; </xsl:text>
                        </xsl:if>
                        <strong><xsl:value-of select="$work-title"/></strong>
                        <xsl:text> &#xB7; Contents</xsl:text>
                      </div>
                    </div>
                    <div class="text-body">
                      <ol class="toc-list">
                        <xsl:for-each select="$index-entries">
                          <li>
                            <a href="{.('file')}">
                              <span class="toc-dot"/>
                              <xsl:value-of select="concat($chunk-unit, ' ', .('n'))"/>
                            </a>
                          </li>
                        </xsl:for-each>
                      </ol>
                    </div>
                  </main>
                  <aside class="sidebar right"/>
                </div>
                <footer class="site-footer">
                  <div class="footer-text">Perseus Digital Library &#xB7; Tufts University</div>
                  <div class="footer-links">
                    <a href="{$catalog-url}">&#x2190; Catalog</a>
                    <a href="{$home-url}">Home</a>
                  </div>
                </footer>
              </div>
            </body>
          </html>
        </xsl:result-document>
      </xsl:on-completion>

      <xsl:variable name="ms"      select="."/>
      <xsl:variable name="ms-next"
        select="following::tei:milestone[@unit = $chunk-unit][1]"/>
      <xsl:variable name="ms-prev"
        select="preceding::tei:milestone[@unit = $chunk-unit][1]"/>

      <!-- Elements strictly between this milestone and the next.
           For the final chunk there is no next milestone, so we take
           all elements after this one. -->
      <xsl:variable name="hits" as="element()*" select="
        if (empty($ms-next))
        then  //element()[. &gt;&gt; $ms]
        else  //element()[. &gt;&gt; $ms][. &lt;&lt; $ms-next]
      "/>
      <!-- Top-level subset: elements with no ancestor also in $hits.
           When $hits is empty the milestones are inline (inside paragraphs
           rather than between block elements).  Fall back to the body's
           direct children and rely on the $start tunnel parameter in
           chunker_core to suppress content that precedes $ms. -->
      <xsl:variable name="top" as="element()*" select="
        if (exists($hits))
        then $hits[not(ancestor::* intersect $hits)]
        else (//tei:body, //tei:text)[1]/child::*
      "/>

      <xsl:variable name="cts-range"
        select="local:chunk-cts-range($top, $ms-next, $base-urn)"/>

      <!-- Use position() for filenames so they are globally unique even
           when @n values restart across structural divisions (e.g. card 1
           in Book 1 and card 1 in Book 2 of the Iliad).  The semantic @n
           value is preserved in the HTML title and the index.json manifest. -->
      <xsl:variable name="pos"       select="position()"/>
      <xsl:variable name="pos-prev"  select="$pos - 1"/>
      <xsl:variable name="pos-next"  select="if ($ms-next) then $pos + 1 else ()"/>
      <xsl:variable name="file-name"
        select="concat($chunk-unit, '_', $pos, '.html')"/>
      <xsl:variable name="prev-file"
        select="if ($ms-prev) then concat($chunk-unit, '_', $pos-prev, '.html') else ()"/>
      <xsl:variable name="next-file"
        select="if ($ms-next) then concat($chunk-unit, '_', $pos-next, '.html') else ()"/>

      <!-- ── Write the chunk HTML file ── -->
      <xsl:result-document
        href        ="{$output-dir}/{$file-name}"
        method      ="html"
        html-version="5"
        indent      ="yes">
        <xsl:call-template name="page:render">
          <xsl:with-param name="chunk"       select="$top"/>
          <xsl:with-param name="start"       select="$ms"/>
          <xsl:with-param name="stop"        select="$ms-next"/>
          <xsl:with-param name="work-title"  select="$work-title"/>
          <xsl:with-param name="author"      select="$author"/>
          <xsl:with-param name="doc-lang"    select="$doc-lang"/>
          <xsl:with-param name="home-url"    select="$home-url"/>
          <xsl:with-param name="chunk-label" select="concat($chunk-unit, ' ', @n)"/>
          <xsl:with-param name="chunk-n"     select="string(@n)"/>
          <xsl:with-param name="cts-range"   select="$cts-range"/>
          <xsl:with-param name="file-name"   select="$file-name"/>
          <xsl:with-param name="prev-file"   select="$prev-file"/>
          <xsl:with-param name="next-file"   select="$next-file"/>
          <xsl:with-param name="all-chunks"  select="$all-chunks"/>
        </xsl:call-template>
      </xsl:result-document>

      <!-- xsl:next-iteration must be the last instruction in the body -->
      <xsl:next-iteration>
        <xsl:with-param name="index-entries" select="(
          $index-entries,
          map {
            'n'   : string(@n),
            'file': $file-name,
            'urn' : ($cts-range, '')[1]
          }
        )"/>
      </xsl:next-iteration>

    </xsl:iterate>
  </xsl:template>

</xsl:stylesheet>

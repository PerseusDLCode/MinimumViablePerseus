<?xml version="1.0" encoding="UTF-8"?>
<!--
  generate_chunks.xsl
  Batch generator: produces one HTML file per milestone chunk, a toc.html,
  and index.json.

  Parameters:
    chunk-unit  (xs:string)  milestone/@unit value to chunk on  [default: 'card']
    output-dir  (xs:string)  directory to write output files to [default: '.']
    catalog-url (xs:string)  relative URL for the Catalog nav link

  Output files are named  {chunk-unit}_{position}.html  (e.g. card_57.html).

  Usage with Saxon on the command line:
    saxon -s:phi1017.phi007.perseus-lat2.xml \
          -xsl:generate_chunks.xsl           \
          chunk-unit=card                    \
          output-dir=/tmp/seneca

    saxon -s:larger.xml      \
          -xsl:generate_chunks.xsl \
          chunk-unit=section  \
          output-dir=/tmp/larger
-->
<xsl:stylesheet
  xmlns:xsl  ="http://www.w3.org/1999/XSL/Transform"
  xmlns:tei  ="http://www.tei-c.org/ns/1.0"
  xmlns:xs   ="http://www.w3.org/2001/XMLSchema"
  xmlns:local="http://local.functions"
  version="3.0"
  exclude-result-prefixes="tei xs local">

  <xsl:import href="chunker_core.xsl"/>

  <xsl:output method="html" html-version="5" indent="yes"/>

  <!-- ============================================================
       Parameters
       ============================================================ -->

  <xsl:param name="chunk-unit"  as="xs:string" select="'card'"/>
  <xsl:param name="output-dir"  as="xs:string" select="'.'"/>
  <xsl:param name="catalog-url" as="xs:string" select="'/index.html'"/>
  <!-- When non-empty, each word in the output is linked to the morphological
       server at this base URL (e.g. http://localhost:5000). -->
  <xsl:param name="morph-url"   as="xs:string" select="''"/>


  <!-- ============================================================
       Main template
       ============================================================ -->

  <xsl:template match="/">
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
        href      ="{$output-dir}/{$file-name}"
        method    ="html"
        html-version="5"
        indent    ="yes">
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
              <xsl:value-of select="$chunk-unit"/>
              <xsl:text> </xsl:text>
              <xsl:value-of select="@n"/>
              <xsl:text> | Perseus</xsl:text>
            </title>
            <xsl:if test="exists($cts-range)">
              <meta name="dc.identifier" content="{$cts-range}"/>
            </xsl:if>
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

                <!-- ── Left sidebar ── -->
                <aside class="sidebar">
                  <details open="open">
                    <summary>Contents</summary>
                    <div class="panel-body">
                      <ol class="toc-list">
                        <xsl:for-each select="$all-chunks">
                          <li>
                            <xsl:if test=".('pos') = $pos">
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

                <!-- ── Center column ── -->
                <main class="center-col">
                  <div class="passage-header">
                    <div class="passage-breadcrumb">
                      <xsl:if test="$author != ''">
                        <xsl:value-of select="$author"/>
                        <xsl:text> &#xB7; </xsl:text>
                      </xsl:if>
                      <strong><xsl:value-of select="$work-title"/></strong>
                      <xsl:text> &#xB7; </xsl:text>
                      <xsl:value-of select="concat($chunk-unit, ' ', @n)"/>
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

                  <!-- CSS-only line-number toggle; must precede .text-body -->
                  <input type="checkbox" class="toggle-input" id="toggle-linenum" checked="checked"/>
                  <div class="text-body">
                    <!-- Single-pass transform: templates check $start/$stop themselves -->
                    <xsl:apply-templates select="$top" mode="chunk">
                      <xsl:with-param name="start"    select="$ms"       tunnel="yes"/>
                      <xsl:with-param name="stop"     select="$ms-next"  tunnel="yes"/>
                      <xsl:with-param name="base-urn" select="$base-urn" tunnel="yes"/>
                      <xsl:with-param name="morph-url" select="$morph-url" tunnel="yes"/>
                    </xsl:apply-templates>
                  </div>
                  <div class="passage-footer">
                    <div class="display-opts">
                      <span class="opt-label">Show:</span>
                      <label class="opt-toggle" for="toggle-linenum">line numbers</label>
                    </div>
                  </div>
                </main>

                <!-- ── Right sidebar ── -->
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

              </div>
              <footer class="site-footer">
                <div class="footer-text">Perseus Digital Library &#xB7; Tufts University</div>
                <div class="footer-links">
                  <a href="{$catalog-url}">&#x2190; Catalog</a>
                  <a href="toc.html">Contents</a>
                </div>
              </footer>
            </div>
          </body>
        </html>
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

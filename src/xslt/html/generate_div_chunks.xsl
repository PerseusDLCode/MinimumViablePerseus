<?xml version="1.0" encoding="UTF-8"?>
<!--
  generate_div_chunks.xsl
  Division-based batch generator: produces one HTML file per structural div
  (e.g. chapter, scene, poem), a toc.html, and index.json.

  Parameters:
    chunk-unit  (xs:string)  @subtype value of the target divs  [default: 'chapter']
    output-dir  (xs:string)  directory to write output files to  [default: '.']
    catalog-url (xs:string)  relative URL for the Catalog nav link

  The stylesheet selects top-level divs whose @subtype matches chunk-unit
  (i.e. divs that are not nested inside another matching div).  It renders
  the full content of each div using chunker_core.xsl without start/stop
  milestone filtering, since the div boundary IS the chunk boundary.

  Output files are named  {chunk-unit}_{position}.html  (e.g. chapter_1.html).
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

  <xsl:param name="chunk-unit"  as="xs:string" select="'chapter'"/>
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
    <xsl:variable name="home-url"
      select="replace($catalog-url, 'catalog/[^/]+\.html$', 'index.html')"/>

    <!-- Top-level divs matching chunk-unit.
         Try @subtype first (e.g. subtype="chapter"); fall back to @type
         (e.g. type="textpart" or type="book") for encodings that do not
         use @subtype.  "Top-level" means not nested inside another matching div. -->
    <xsl:variable name="by-subtype" as="element()*" select="
      //tei:div[@subtype = $chunk-unit]
               [not(ancestor::tei:div[@subtype = $chunk-unit])]
    "/>
    <xsl:variable name="chunks" as="element()*" select="
      if (exists($by-subtype)) then $by-subtype
      else //tei:div[@type = $chunk-unit]
                    [not(ancestor::tei:div[@type = $chunk-unit])]
    "/>

    <xsl:if test="empty($chunks)">
      <xsl:message terminate="yes">
        No div elements found with subtype="<xsl:value-of select="$chunk-unit"/>"
        or type="<xsl:value-of select="$chunk-unit"/>".
        Check the chunk-unit parameter.
      </xsl:message>
    </xsl:if>

    <!-- Pre-collect lightweight chunk metadata so every result-document
         can render a complete sidebar TOC without a second traversal. -->
    <xsl:variable name="all-chunks" as="map(*)*">
      <xsl:for-each select="$chunks">
        <xsl:sequence select="map {
          'n'   : string(@n),
          'pos' : position(),
          'file': concat($chunk-unit, '_', position(), '.html')
        }"/>
      </xsl:for-each>
    </xsl:variable>

    <xsl:iterate select="$chunks">
      <xsl:param name="index-entries" as="map(*)*" select="()"/>

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
              <title><xsl:value-of select="$work-title"/> — Contents | Perseus</title>
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

      <xsl:variable name="div"      select="."/>
      <xsl:variable name="pos"      select="position()"/>
      <xsl:variable name="pos-prev" select="$pos - 1"/>
      <xsl:variable name="pos-next" select="if (position() lt last()) then $pos + 1 else ()"/>

      <xsl:variable name="file-name"
        select="concat($chunk-unit, '_', $pos, '.html')"/>
      <xsl:variable name="prev-file"
        select="if ($pos gt 1) then concat($chunk-unit, '_', $pos-prev, '.html') else ()"/>
      <xsl:variable name="next-file"
        select="if (exists($pos-next)) then concat($chunk-unit, '_', $pos-next, '.html') else ()"/>

      <xsl:variable name="chunk-label"
        select="concat($work-title, ' — ', $chunk-unit, ' ', @n)"/>

      <!-- ── Write the chunk HTML file ── -->
      <xsl:result-document
        href        ="{$output-dir}/{$file-name}"
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
            <title>
              <xsl:value-of select="$work-title"/>
              <xsl:text> &#x2014; </xsl:text>
              <xsl:value-of select="$chunk-unit"/>
              <xsl:text> </xsl:text>
              <xsl:value-of select="@n"/>
              <xsl:text> | Perseus</xsl:text>
            </title>
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
                      <xsl:if test="exists($next-file)">
                        <a href="{$next-file}" class="nav-btn">next &#x2192;</a>
                      </xsl:if>
                    </div>
                  </div>

                  <!-- CSS-only line-number toggle; must precede .text-body -->
                  <input type="checkbox" class="toggle-input" id="toggle-linenum" checked="checked"/>
                  <div class="text-body">
                    <!-- Render the full div content; no start/stop filtering needed -->
                    <xsl:apply-templates select="$div/node()" mode="chunk">
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

      <xsl:next-iteration>
        <xsl:with-param name="index-entries" select="(
          $index-entries,
          map {
            'n'   : string(@n),
            'file': $file-name,
            'urn' : ''
          }
        )"/>
      </xsl:next-iteration>

    </xsl:iterate>
  </xsl:template>

</xsl:stylesheet>

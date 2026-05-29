<?xml version="1.0" encoding="UTF-8"?>
<!--
  generate_protopages.xsl
  Step 1 of the two-step pipeline: TEI → proto-page XML.

  For each div[@type='chapter'] in a Family-1 (hierarchical-div) TEI document
  with a book/chapter/section citation structure, produces one proto-page XML
  file per chapter in a simple, no-namespace vocabulary designed for easy
  Python/Jinja2 consumption.  Proto-pages carry all the semantic data needed
  to render a reading page: CTS URNs, navigation links, publication metadata,
  and structured text.

  The base CTS URN is read from body/@xml:base.  Section URNs are computed as
  {base-urn}:{book}.{chapter}.{section}.

  Parameters:
    output-dir  (xs:string)  Directory for output files  [default: '.']
    sourceURL   (xs:string)  Source URL for the document  [default: '']

  Output files are named  chunk_{book}.{chapter}.xml
  An index.json manifest is also written.

  Usage (direct Saxon invocation):
    saxon -s:data/tlg0003.tlg001.perseus-grc2.xml  \
          -xsl:generate_protopages.xsl              \
          output-dir=/tmp/thucydides-grc

  Usage (Python CLI wrapper):
    python -m tei_tagger.generate_protopages        \
          data/tlg0003.tlg001.perseus-grc2.xml      \
          /tmp/thucydides-grc
-->
<xsl:stylesheet
  xmlns:xsl="http://www.w3.org/1999/XSL/Transform"
  xmlns:tei="http://www.tei-c.org/ns/1.0"
  xmlns:xs ="http://www.w3.org/2001/XMLSchema"
  version="3.0"
  exclude-result-prefixes="tei xs">

  <!-- Default output for the individual chunk files -->
  <xsl:output method="xml" indent="yes" encoding="UTF-8"/>

  <xsl:param name="output-dir" as="xs:string" select="'.'"/>
  <xsl:param name="sourceURL"  as="xs:string" select="''"/>


  <!-- ============================================================
       Root template
       ============================================================ -->

  <xsl:template match="/">
    <xsl:variable name="base-urn"   select="string(//tei:body/@xml:base)"/>
    <xsl:variable name="language"   select="string((//tei:langUsage/tei:language)[1]/@ident)"/>
    <xsl:variable name="chapters"   select="//tei:div[@type='chapter']"/>
    <xsl:variable name="n-chapters" select="count($chapters)"/>

    <!-- Publication metadata — extracted once and shared across all chunks -->
    <xsl:variable name="pub-title"
      select="string(((//tei:titleStmt/tei:title[@type='main'])[1],
                      (//tei:titleStmt/tei:title)[1])[1])"/>
    <xsl:variable name="pub-author"
      select="string((//tei:titleStmt/tei:author)[1])"/>
    <xsl:variable name="pub-editors"
      select="//tei:titleStmt/tei:editor"/>
    <xsl:variable name="pub-place"
      select="string(((//tei:publicationStmt/tei:pubPlace)[1],
                      (//tei:sourceDesc//tei:pubPlace)[1])[1])"/>
    <xsl:variable name="pub-date"
      select="string(((//tei:publicationStmt/tei:date)[1],
                      (//tei:sourceDesc//tei:date)[1])[1])"/>

    <!-- citeStructure metadata for index.json.
         Perseus documents have a body-level outer citeStructure (no @unit);
         the first named level is the book and the second is the chapter.  -->
    <xsl:variable name="book-subtype"
      select="string((//tei:refsDecl[@default='true']/tei:citeStructure/tei:citeStructure/@unit,
                      //tei:refsDecl/tei:citeStructure/tei:citeStructure/@unit)[1])"/>
    <xsl:variable name="chapter-subtype"
      select="string((//tei:refsDecl[@default='true']/tei:citeStructure/tei:citeStructure/tei:citeStructure/@unit,
                      //tei:refsDecl/tei:citeStructure/tei:citeStructure/tei:citeStructure/@unit)[1])"/>

    <xsl:if test="$base-urn = ''">
      <xsl:message terminate="yes">
        No xml:base on body element. Expected a migrated TEI file with
        body/@xml:base carrying the CTS base URN.
      </xsl:message>
    </xsl:if>
    <xsl:if test="$n-chapters = 0">
      <xsl:message terminate="yes">
        No div[@type='chapter'] elements found.
        Check that this document has a book/chapter/section structure.
      </xsl:message>
    </xsl:if>

    <xsl:iterate select="$chapters">
      <xsl:param name="index-entries" as="map(*)*" select="()"/>

      <!-- xsl:on-completion must appear first (after xsl:param) in iterate body -->
      <xsl:on-completion>
        <xsl:result-document href="{$output-dir}/index.json" method="json" indent="yes">
          <xsl:sequence select="map{
            'base_urn':        $base-urn,
            'title':           $pub-title,
            'language':        $language,
            'author':          $pub-author,
            'book_subtype':    $book-subtype,
            'chapter_subtype': $chapter-subtype,
            'chunks':          array{ $index-entries }
          }"/>
        </xsl:result-document>
      </xsl:on-completion>

      <!-- ── per-chapter variables ── -->
      <xsl:variable name="pos"      select="position()"/>
      <xsl:variable name="book-n"   select="string(ancestor::tei:div[@type='book']/@n)"/>
      <xsl:variable name="chap-n"   select="string(@n)"/>
      <xsl:variable name="chunk-urn" select="concat($base-urn, ':', $book-n, '.', $chap-n)"/>
      <xsl:variable name="file-name" select="concat('chunk_', $book-n, '.', $chap-n, '.xml')"/>

      <!-- prev / next by sequence position (O(n) total, not O(n²)) -->
      <xsl:variable name="prev-chap" select="if ($pos gt 1) then $chapters[$pos - 1] else ()"/>
      <xsl:variable name="next-chap" select="if ($pos lt $n-chapters) then $chapters[$pos + 1] else ()"/>
      <xsl:variable name="prev-urn"  select="if (exists($prev-chap)) then
        concat($base-urn, ':',
               $prev-chap/ancestor::tei:div[@type='book']/@n, '.',
               $prev-chap/@n)
        else ''"/>
      <xsl:variable name="next-urn"  select="if (exists($next-chap)) then
        concat($base-urn, ':',
               $next-chap/ancestor::tei:div[@type='book']/@n, '.',
               $next-chap/@n)
        else ''"/>

      <!-- ── write chunk file ── -->
      <xsl:result-document href="{$output-dir}/{$file-name}" method="xml" indent="yes">
        <chunk cts-urn="{$chunk-urn}">
          <xsl:if test="$prev-urn != ''">
            <xsl:attribute name="prev-urn" select="$prev-urn"/>
          </xsl:if>
          <xsl:if test="$next-urn != ''">
            <xsl:attribute name="next-urn" select="$next-urn"/>
          </xsl:if>
          <meta>
            <title><xsl:value-of select="$pub-title"/></title>
            <base-urn><xsl:value-of select="$base-urn"/></base-urn>
            <language><xsl:value-of select="$language"/></language>
            <ctsurn><xsl:value-of select="$base-urn"/></ctsurn>
            <sourceURL><xsl:value-of select="$sourceURL"/></sourceURL>
            <pubInfo>
              <title><xsl:value-of select="$pub-title"/></title>
              <author><xsl:value-of select="$pub-author"/></author>
              <xsl:choose>
                <xsl:when test="exists($pub-editors)">
                  <xsl:for-each select="$pub-editors">
                    <editor><xsl:value-of select="."/></editor>
                  </xsl:for-each>
                </xsl:when>
                <xsl:otherwise>
                  <editor/>
                </xsl:otherwise>
              </xsl:choose>
              <pubPlace><xsl:value-of select="$pub-place"/></pubPlace>
              <pubDate><xsl:value-of select="$pub-date"/></pubDate>
            </pubInfo>
          </meta>
          <content>
            <xsl:apply-templates select="tei:div[@type='section']" mode="section">
              <xsl:with-param name="base-urn" tunnel="yes" select="$base-urn"/>
              <xsl:with-param name="book-n"   tunnel="yes" select="$book-n"/>
              <xsl:with-param name="chap-n"   tunnel="yes" select="$chap-n"/>
            </xsl:apply-templates>
          </content>
        </chunk>
      </xsl:result-document>

      <xsl:next-iteration>
        <xsl:with-param name="index-entries" select="(
          $index-entries,
          map{
            'urn':     $chunk-urn,
            'file':    $file-name,
            'book':    $book-n,
            'chapter': $chap-n
          }
        )"/>
      </xsl:next-iteration>
    </xsl:iterate>
  </xsl:template>


  <!-- ============================================================
       Section template
       ============================================================ -->

  <xsl:template match="tei:div[@type='section']" mode="section">
    <xsl:param name="base-urn" tunnel="yes"/>
    <xsl:param name="book-n"   tunnel="yes"/>
    <xsl:param name="chap-n"   tunnel="yes"/>
    <section n="{@n}"
             cts-urn="{concat($base-urn, ':', $book-n, '.', $chap-n, '.', @n)}">
      <xsl:apply-templates mode="content"/>
    </section>
  </xsl:template>


  <!-- ============================================================
       Content mode — convert TEI prose elements to chunk vocabulary.

       Strategy: convert known elements explicitly; pass text through
       unknown inline elements so no text is silently lost; suppress
       milestone, pb, and editorial notes.
       ============================================================ -->

  <xsl:template match="tei:p" mode="content">
    <!-- @rend (indent hints etc.) is a TEI styling attribute; drop it -->
    <p><xsl:apply-templates mode="content"/></p>
  </xsl:template>

  <xsl:template match="tei:placeName" mode="content">
    <place>
      <xsl:if test="@key">
        <xsl:attribute name="key" select="@key"/>
      </xsl:if>
      <xsl:apply-templates mode="content"/>
    </place>
  </xsl:template>

  <xsl:template match="tei:persName" mode="content">
    <person>
      <xsl:if test="@key">
        <xsl:attribute name="key" select="@key"/>
      </xsl:if>
      <xsl:apply-templates mode="content"/>
    </person>
  </xsl:template>

  <xsl:template match="tei:q | tei:quote" mode="content">
    <q><xsl:apply-templates mode="content"/></q>
  </xsl:template>

  <xsl:template match="tei:del" mode="content">
    <del><xsl:apply-templates mode="content"/></del>
  </xsl:template>

  <xsl:template match="tei:add" mode="content">
    <add><xsl:apply-templates mode="content"/></add>
  </xsl:template>

  <xsl:template match="tei:gap" mode="content">
    <gap/>
  </xsl:template>

  <!-- Suppress milestone, pb, and editorial notes; they carry no reading text -->
  <xsl:template match="tei:milestone | tei:pb | tei:note" mode="content"/>

  <!-- Pass text through unchanged -->
  <xsl:template match="text()" mode="content">
    <xsl:copy/>
  </xsl:template>

  <!-- Default for any unhandled element: pass children through so no text is lost -->
  <xsl:template match="*" mode="content">
    <xsl:apply-templates mode="content"/>
  </xsl:template>

</xsl:stylesheet>

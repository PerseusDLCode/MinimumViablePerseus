<?xml version="1.0" encoding="UTF-8"?>
<!--
  chunker_core.xsl
  Chunk-boundary infrastructure for the TEI-to-HTML pipeline.

  Mode contract
  ─────────────
  • mode="chunk" : owned here. Traverses the document tree, applies
    local:before-stop / local:after-start boundary guards at each node, and
    suppresses nodes outside the current chunk's range. When a node passes the
    boundary test, it delegates to mode="tei-to-html" for rendering.
    Never produces HTML element content directly.

  • mode="tei-to-html" : owned by tei/perseus_base.xsl. Pure rendering library.
    No tunnel parameters cross from mode="chunk" into mode="tei-to-html"; the
    rendering templates are ignorant of $start/$stop. Container templates in
    the rendering library recurse back into mode="chunk" so that boundary
    checking continues for every child node.

  Tunnel parameters available in mode="chunk":
    $start     (node()?)    — milestone that starts this chunk, or empty.
    $stop      (node()?)    — milestone that ends this chunk, or empty.
    $morph-url (xs:string)  — morphological server base URL (rendering concern;
                              flows through to mode="tei-to-html" automatically).
-->
<xsl:stylesheet
  xmlns:xsl  ="http://www.w3.org/1999/XSL/Transform"
  xmlns:tei  ="http://www.tei-c.org/ns/1.0"
  xmlns:xs   ="http://www.w3.org/2001/XMLSchema"
  xmlns:local="http://local.functions"
  version="3.0"
  exclude-result-prefixes="tei xs local">

  <xsl:import href="tei/perseus_base.xsl"/>

  <!-- ============================================================
       Boundary functions
       ============================================================ -->

  <!--
    local:before-stop($node, $stop) → xs:boolean
    True when $node should be included in the current chunk.

    • If $stop is empty (last chunk), always true.
    • If $node IS the stop milestone, false.
    • If $node starts after the stop in document order, false.
    • If $node CONTAINS the stop as a descendant (straddles the boundary),
      true — the catch-all delegates to mode="tei-to-html", whose container
      templates recurse into mode="chunk" so children suppress themselves.
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
    True when $node qualifies as part of the start of the current chunk.

    • If $start is empty (no start filtering), always true.
    • If $node comes after $start in document order, true.
    • If $node IS an element that contains $start as a descendant (straddles
      the start boundary), true.
    • Otherwise, false.
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
    Used by chunkers (generate_chunks.xsl) to compute CTS line-range URNs.
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

  <!-- ============================================================
       Chunk-mode catch-all
       ============================================================ -->

  <!--
    Single entry point for all chunk-mode traversal.
    Applies boundary guards; nodes that pass are delegated to
    mode="tei-to-html" for rendering.  Never emits HTML directly.
    Container templates in mode="tei-to-html" recurse back into mode="chunk"
    so that boundary checking continues for every descendant.
  -->
  <xsl:template match="node()" mode="chunk">
    <xsl:param name="start" tunnel="yes" as="node()?"/>
    <xsl:param name="stop"  tunnel="yes" as="node()?"/>
    <xsl:if test="local:after-start(., $start) and local:before-stop(., $stop)">
      <xsl:apply-templates select="." mode="tei-to-html"/>
    </xsl:if>
  </xsl:template>

</xsl:stylesheet>

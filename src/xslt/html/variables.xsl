<?xml version="1.0" encoding="UTF-8"?>
<xsl:stylesheet xmlns:xsl="http://www.w3.org/1999/XSL/Transform"
    xmlns:xs="http://www.w3.org/2001/XMLSchema"
    xmlns:tei="http://www.tei-c.org/ns/1.0"
    exclude-result-prefixes="xs tei"
    version="3.0">

    <xsl:variable name="page-css" as="xs:string">
*, *::before, *::after { box-sizing: border-box; }

:root {
  --color-bg-primary:       #ffffff;
  --color-bg-secondary:     #f7f7f5;
  --color-text-primary:     #1a1a1a;
  --color-text-secondary:   #555555;
  --color-text-tertiary:    #999999;
  --color-border-primary:   #cccccc;
  --color-border-secondary: #dddddd;
  --color-border-tertiary:  #e8e8e6;
  --font-sans:  system-ui, -apple-system, sans-serif;
  --font-serif: Georgia, 'Times New Roman', serif;
  --font-mono:  'Courier New', Courier, monospace;
  --radius-sm: 3px;
  --radius-md: 4px;
}

/* ── Shell layout ── */
.perseus-shell {
  display: grid;
  grid-template-rows: auto 1fr auto;
  min-height: 100vh;
}
.main-area {
  display: grid;
  grid-template-columns: 220px 1fr 220px;
  align-items: start;
}

/* ── Sidebars ── */
.sidebar {
  background: var(--color-bg-secondary);
  border-right: 1px solid var(--color-border-tertiary);
  padding: 1em;
  font-size: .85em;
  font-family: var(--font-sans);
  min-height: 100%;
}
.sidebar.right {
  border-right: none;
  border-left: 1px solid var(--color-border-tertiary);
}

/* ── Site header ── */
.site-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: .5em 1em;
  border-bottom: 1px solid var(--color-border-primary);
  font-family: var(--font-sans);
  font-size: .9em;
  color: var(--color-text-secondary);
}
.header-logo { font-weight: bold; letter-spacing: .05em; }
.header-logo span { font-weight: normal; }
.header-nav a { margin-left: 1em; text-decoration: none; color: inherit; }
.header-nav a:hover { text-decoration: underline; }

/* ── Site footer ── */
.site-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: .5em 1em;
  border-top: 1px solid var(--color-border-tertiary);
  font-family: var(--font-sans);
  font-size: .8em;
  color: var(--color-text-tertiary);
}
.footer-links a { margin-left: .75em; text-decoration: none; color: inherit; }
.footer-links a:hover { text-decoration: underline; }

/* ── Center column ── */
.center-col { padding: 1em 2em; }

/* ── Passage header / nav ── */
.passage-header {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  margin-bottom: 1.5em;
  padding-bottom: .5em;
  border-bottom: 1px solid var(--color-border-secondary);
  font-family: var(--font-sans);
  font-size: .9em;
  color: var(--color-text-secondary);
}
.passage-breadcrumb strong { color: var(--color-text-primary); }
.passage-nav { display: flex; gap: .5em; }
.nav-btn {
  text-decoration: none;
  color: var(--color-text-secondary);
  border: 1px solid var(--color-border-secondary);
  border-radius: var(--radius-sm);
  padding: .1em .5em;
  font-size: .85em;
}
.nav-btn:hover { background: var(--color-bg-secondary); }

/* ── Text body: padding reserves room for absolute-positioned sidenotes ── */
.text-body { padding-right: 230px; position: relative; }

/* ── Passage footer / display options ── */
.passage-footer {
  margin-top: 1.5em;
  padding-top: .5em;
  border-top: 1px solid var(--color-border-secondary);
  font-family: var(--font-sans);
  font-size: .85em;
  color: var(--color-text-secondary);
}
.display-opts { display: flex; align-items: center; gap: .5em; }

/* ── CSS checkbox hack: toggle-input controls .line-n visibility ── */
.toggle-input { display: none; }
.toggle-input:not(:checked) ~ .text-body .line-n { display: none; }

/* ── Verse lines ── */
p.line {
  display: flex;
  align-items: baseline;
  margin: .1em 0;
  font-family: var(--font-serif);
  font-size: 14px;
  color: var(--color-text-primary);
  position: relative;
}
.line-n {
  min-width: 2.5em;
  color: var(--color-text-tertiary);
  font-size: .8em;
  text-align: right;
  padding-right: .75em;
  flex-shrink: 0;
}
.line-text { flex: 1; }

/* ── Prose paragraphs ── */
p {
  line-height: 1.7;
  margin-bottom: .75em;
  font-family: var(--font-serif);
  font-size: 14px;
  color: var(--color-text-primary);
  position: relative;
}

/* ── Inline notes rendered as sidenotes ── */
.note {
  position: absolute;
  right: -220px;
  width: 210px;
  font-size: .8em;
  color: var(--color-text-secondary);
  line-height: 1.4;
  border-left: 2px solid var(--color-border-secondary);
  padding-left: .5em;
}

/* ── TOC list ── */
.toc-list { list-style: none; padding: 0; margin: 0; line-height: 1.8; }
.toc-list a {
  text-decoration: none;
  color: var(--color-text-secondary);
  display: flex;
  align-items: center;
  gap: .4em;
}
.toc-list a:hover { color: var(--color-text-primary); }
.toc-list li.current > a { font-weight: bold; color: var(--color-text-primary); }
.toc-dot {
  width: 6px; height: 6px;
  border-radius: 50%;
  background: var(--color-border-primary);
  flex-shrink: 0;
}
.toc-list li.current .toc-dot { background: var(--color-text-secondary); }

/* ── Details / summary collapsible panels ── */
details { margin-bottom: .75em; }
summary {
  font-weight: bold;
  cursor: pointer;
  font-size: .9em;
  padding: .25em 0;
  color: var(--color-text-secondary);
  list-style: none;
}
summary::-webkit-details-marker { display: none; }
summary::before { content: '\25B6  '; font-size: .7em; }
details[open] > summary::before { content: '\25BC  '; }
.panel-body { padding: .5em 0; }

/* ── Work-info metadata rows ── */
.meta-row { display: flex; gap: .5em; font-size: .85em; margin-bottom: .35em; }
.meta-label { color: var(--color-text-tertiary); min-width: 5em; }
.meta-value { color: var(--color-text-primary); }

/* ── Sidebar placeholder messages ── */
.placeholder-msg {
  color: var(--color-text-tertiary);
  font-style: italic;
  font-size: .85em;
  margin: 0;
  line-height: 1.4;
}

/* ── Speech blocks ── */
.speech { margin: 1em 0; }
.speaker { font-weight: bold; display: block; margin-bottom: .25em; }

/* ── Editorial marks ── */
.gap { color: #888; font-style: italic; }
.tei-del { text-decoration: line-through; color: red; }
.tei-add { text-decoration: none; color: blue; }

/* ── Word links (morphological server) ── */
a.word { color: inherit; text-decoration: none; border-bottom: 1px dotted #aaa; }
a.word:hover { border-bottom-style: solid; }
    </xsl:variable>

</xsl:stylesheet>

# Minimum Viable Perseus
Minimum Viable Perseus (MVP) is the first phase in the development of Perseus 6, the latest in a series of digital library systems that enable users to read Greek and Latin in rich hypertextual contexts.  Those users range from traditional classical philologists to computational linguists to classical-language students to general humanities scholars and readers.

MVP is a static website generated from the TEI-encoded documents in Perseus's corpus.  It has been designed with several aims:

 - To provide a functional replacement for Perseus 4;

 - To create a version of Perseus that does not impose technical burdens on maintainers and future developers; 

 - To establish a foundation upon which features and functions developed for the Scaife Viewer and Beyond Translation may be included in Perseus.

## MVP Components

* **Normalizers**: XSL stylesheets and Python modules that upgrade Perseus's TEI texts to conform with an established set of practices.
  
* **Indexers**: XSL stylesheets and Python modules that generate tokenizations, citation indexes, and other intermediate files.

* **Compilers**: XSL stylesheets and Python modules that use the TEI texts and the intermediate files to create a website.

## Repository Organization
There is a wiki that contains a variety of documents, including installation instructions.


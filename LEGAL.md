# Legal and publication policy

This repository documents reverse-engineering research. It is not legal advice.

The publication policy here is intentionally conservative:

- do not commit complete vendor BIOS images, full SPI dumps, vendor flash packages, or third-party modified firmware;
- do not commit wholesale decompiled/disassembled firmware trees;
- do commit hashes, offsets, GUIDs, release metadata, source URLs, derived tables, independently written analysis, reproducible scripts, and small excerpts needed to explain a finding;
- identify the source/version of excerpts and keep them no larger than necessary for technical criticism, review, or verification.

## EU context

Directive 2009/24/EC on the legal protection of computer programs contains several relevant exceptions. Article 5(3) permits a person entitled to use a copy of a program to observe, study, or test its functioning in order to determine the ideas and principles underlying it while performing acts they are entitled to perform. Article 6 permits decompilation without authorization only under specified conditions when it is indispensable to obtain information necessary for interoperability of an independently created program; Article 6(2) also restricts how information obtained through that exception may be used or disclosed.

Official text:
https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32009L0024

Directive 2001/29/EC Article 5(3)(d) also permits Member States to provide quotation exceptions for purposes such as criticism or review, subject to source attribution, fair practice, and use only to the extent required by the purpose. National implementation still matters.

Official text:
https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32001L0029

Therefore this repository does **not** assume that "reverse engineering is legal" automatically means "publishing an entire decompiled BIOS is unrestricted." The safer default is to publish analysis and narrowly scoped evidence excerpts, while keeping complete copyrighted firmware/decompilation outside the repository unless there is a separate, well-founded reason to publish it.

## Vendor and third-party material

Names such as MINISFORUM, AMD, AMI and product/model names remain the property of their respective owners. Hashes and technical identifiers are recorded solely to identify analyzed artifacts.

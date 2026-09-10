# Analysis helpers

This directory contains only first-party helper scripts written for this investigation.

Current helpers:

- `pe_semantic_diff.py` — zeroes selected volatile PE metadata, relocation targets and debug payloads before section-level comparison;
- `asm_semantic_compare.py` — normalizes objdump output by abstracting RIP-relative displacements and branch targets before sequence comparison;
- `pcd_db_diff.py` — parses EDK II BuildVersion-7 external PCD databases, decodes scalar DATA defaults, uses stable DynamicEx identities as a renumbering anchor, and performs a value-aware token-sequence diff. It was used to localize the DRFXI 1.12→1.15 `91 → 100` TCC PCD change.

These scripts are intentionally small and conservative. Their output should not be treated as proof of semantic equivalence by itself: PCD-token changes and embedded data constants can still require manual interpretation. In particular, `pcd_db_diff.py` cannot recover source-level PCD CNames when the database has `PcdNameTableOffset == 0`.

Third-party tools such as UEFIExtract, IFRExtractor-RS and ACPICA are **not vendored** here. Research notes should record the exact tool/version used; acquisition/toolchain bundles can remain outside Git history.

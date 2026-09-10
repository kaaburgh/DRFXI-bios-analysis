# Evidence policy

This directory contains **small derived excerpts** used to make individual findings auditable.

It intentionally does not contain complete firmware images, full extracted UEFI trees, or wholesale decompilations/disassemblies. Those remain local acquisition/analysis artifacts identified by hashes in `data/`.

Each evidence file should include enough provenance to reproduce it:

- firmware version and SHA-256;
- source module / FFS / ACPI table / IFR module;
- relevant GUID/offset where known;
- extraction/decompilation tool when material;
- a narrowly scoped excerpt plus independent analysis comments.

If a future finding requires a larger derived artifact, prefer adding a reproduction script and a hash rather than committing the entire vendor-derived output by default.

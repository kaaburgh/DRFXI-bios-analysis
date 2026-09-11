# Analysis helpers

This directory contains only first-party helper scripts written for this investigation.

Current helpers:

- `pe_semantic_diff.py` — zeroes selected volatile PE metadata, relocation targets and debug payloads before section-level comparison;
- `asm_semantic_compare.py` — normalizes objdump output by abstracting RIP-relative displacements and branch targets before sequence comparison;
- `pcd_db_diff.py` — parses EDK II BuildVersion-7 external PCD databases, decodes scalar DATA defaults, uses stable DynamicEx identities as a renumbering anchor, and performs a value-aware token-sequence diff. It was used to localize the DRFXI 1.12→1.15 `91 → 100` TCC PCD change;
- `patch_drfxi_117_clean_hii_unlock.py` — fail-closed, exact-version patcher for the official DRFXI 1.17 image. It exposes the selected UMC/DDR memory tree plus the existing VDDP/FCLK branch and AMI Save/Restore User Defaults without importing donor-board state.

## DRFXI 1.17 clean HII patcher

The patcher accepts only the exact official DRFXI 1.17 `DRFXI.BIN` with SHA-256:

```text
99f3bab5ea491202bf365c23e6416f9d1e8a649ad00f90c1f3e21f1a61e35c51
```

Example:

```bash
python3 scripts/patch_drfxi_117_clean_hii_unlock.py \
  DRFXI.BIN \
  DRFXI_1.17_clean-hii-unlock.BIN
```

A JSON patch report is written next to the output image unless `--report` is supplied.

The script does not use fixed whole-image offsets for the target settings. It validates the known firmware/container hashes and sizes, locates the target FFS/LZMA containers structurally, matches AMITSE question/form records through version-specific semantic keys, verifies expected original access bytes, and preserves all original FFS/section allocations while repacking the two LZMA layers.

The reference static validation is recorded in:

- `docs/findings/clean-hii-unlock.md`
- `data/drfxi-1.17-clean-hii-unlock-validation.json`

The generated reference image was statically validated, but **this is not a flashing recommendation**. No hardware boot/runtime validation has been performed and parser acceptance alone does not establish flash safety.

## General caveat

These scripts are intentionally small and conservative. Their output should not be treated as proof of semantic equivalence by itself: PCD-token changes and embedded data constants can still require manual interpretation. In particular, `pcd_db_diff.py` cannot recover source-level PCD CNames when the database has `PcdNameTableOffset == 0`.

Third-party tools such as UEFIExtract, IFRExtractor-RS and ACPICA are **not vendored** here. Research notes should record the exact tool/version used; acquisition/toolchain bundles can remain outside Git history.

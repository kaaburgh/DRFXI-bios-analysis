# Analysis helpers

This directory contains only first-party helper scripts written for this investigation.

Current helpers:

- `pe_semantic_diff.py` — zeroes selected volatile PE metadata, relocation targets and debug payloads before section-level comparison;
- `asm_semantic_compare.py` — normalizes objdump output by abstracting RIP-relative displacements and branch targets before sequence comparison;
- `pcd_db_diff.py` — parses EDK II BuildVersion-7 external PCD databases, decodes scalar DATA defaults, uses stable DynamicEx identities as a renumbering anchor, and performs a value-aware token-sequence diff. It was used to localize the DRFXI 1.12→1.15 `91 → 100` TCC PCD change;
- `trefi_chain_audit.py` — read-only, standard-library-only audit of the DDR5 tREFI chain in any AMD SPI image. It walks FV/FFS/sections (LZMA and AMD zlib), decompresses PSP `$PS1` images, and reports which UEFI modules or ABL overlays contain the known APCB timing tokens (Tref `0x419FF338` plus Tcl/Trfc1 controls) and tREFI strings, together with the AGESA PI string. It is intended for comparing DRFXI against newer (e.g. FireRangeFL1) images; see `docs/findings/memory-trefi.md`;
- `extract_apcb_regions.py` — read-only and stdlib-only, so it runs with plain Python on Windows. From a full 32 MiB SPI dump it extracts only the APCB entries (types `0x60`/`0x68`), the PSP/BIOS directory tables and the EFS header, plus a manifest with SHA-256 of every 64 KiB block. A board owner can share APCB state without sharing NVRAM, serial numbers, keys or SPD data;
- `lib/x86mod.py` — a small helper class (needs `pefile` + `capstone`) that linear-disassembles an extracted x86-64 PE body, resolves RIP-relative string/data references, finds function starts by `int3` padding, and dumps annotated ranges. Used for the APCB-service feasibility analysis (`docs/checkpoints/2026-11-24-trefi-apcb-service-feasibility.md`);
- `abl_tref_path.py` — read-only (needs `capstone`). It finds the ABL overlay with "Override Timing" in an SPI image and reports the timing getters, APCB tokens and structure offsets. It then follows Tref through the TimingPtr helper into the `UMC::DramTiming12[15:0]` write in "Program UMC Timings", checks that the field offsets match, and checks that Override is called immediately before Program. Verified on DRFXI 1.04/1.12/1.15/1.17 and MS-A2 FRG 1.02/1.04; see `docs/checkpoints/2026-11-24-trefi-abl-path.md`;
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

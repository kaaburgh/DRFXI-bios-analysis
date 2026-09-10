# DRFXI BIOS analysis

Reverse-engineering notes and reproducible evidence for the MINISFORUM DRFXI firmware lineage used by boards including BD790i / BD770i / BD790i X3D and related systems.

## Current scope

The active comparison is DRFXI **1.12 → 1.15 → 1.17**, with older 1.04/1.07 images and a community `795iX3D.bin` dump used as reference material.

Current high-confidence findings include:

- hidden AMD CBS/UMC memory-tuning controls remain present in 1.12, 1.15 and 1.17;
- AMI `Save as User Defaults` / `Restore User Defaults` actions exist in all three versions but are deliberately suppressed in IFR;
- the 1.14 changelog item `Hide Above 4G Decoding` is directly visible in HII/IFR;
- `AMD Variable Protection` appears by 1.15 together with `AmdVariableProtection.efi`;
- 1.17 adds TCG Storage Security modules/forms not mentioned in the published changelog;
- the 1.17 dGPU/iGPU behavior has been localized to new OEM DXE logic operating on `AmdSetupRPL` offset `0x44`;
- the strongest candidate for the 1.16 `Workaround abnormal restart after S3` is a new `AmdCpmOemAcpi` package containing platform-patched PCIe power/wake SSDTs and an explicit PME_Turn_Off → WakeLink → DL_ACTIVE resume handshake;
- a community `795iX3D.bin` image is overwhelmingly based on stock 1.12; its intentional UEFI modification is isolated to `AMITSESetupData`, while the full image also contains donor-board runtime/NVRAM state and should not be treated as a portable flash image.

See [`docs/research-status.md`](docs/research-status.md) for the current research state and [`docs/findings/`](docs/findings/) for topic-oriented findings.

## Repository layout

The layout intentionally separates **living conclusions**, **immutable checkpoints**, **machine-readable facts**, and **small evidence excerpts** so that the research can grow without requiring a large structural rewrite:

```text
docs/
  research-status.md       living project state / next work
  firmware-lineage.md      release lineage and provenance
  findings/                topic-oriented findings that evolve over time
  checkpoints/             dated snapshots preserved as written

data/                      hashes, release metadata and diff summaries

evidence/                  small, reviewable derived excerpts + provenance
scripts/                   first-party analysis/acquisition helpers
```

Raw vendor firmware images, third-party BIOS dumps, complete extracted firmware trees, and wholesale decompilations are **not** committed. Hashes, source URLs, offsets, module GUIDs, derived facts, and narrowly scoped excerpts are sufficient to make findings auditable while keeping the repository small and reducing redistribution/licensing ambiguity.

## Evidence conventions

Each finding should distinguish:

- **confirmed** — directly demonstrated by binary/HII/AML/code evidence;
- **strongly attributable / likely** — evidence fits a changelog item but the exact intermediate release is unavailable;
- **inference** — plausible interpretation requiring another artifact or test;
- **unknown** — explicitly unresolved.

When possible, evidence should include firmware SHA-256, module/FFS identity, VarStore/offset, source-table identity, and enough excerpted context to reproduce the conclusion.

## Legal / provenance note

This repository is a technical research record, not legal advice. It intentionally avoids redistributing complete proprietary BIOS images or wholesale decompiled vendor source. See [`LEGAL.md`](LEGAL.md) for the conservative publication policy used here.

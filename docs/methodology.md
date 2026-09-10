# Methodology and reproducibility

Last updated: 2026-09-10

This document records how firmware evidence is extracted and compared. The goal is to keep conclusions reproducible without committing complete proprietary firmware trees.

## Primary toolchain used in the current analysis

### UEFI / FFS extraction

- UEFIExtract A75
  - source commit: `19a4dab71f1f994cc2a26b6808e0249e0098c366`
  - Linux binary SHA-256: `f1b8d112838adcf741c43dbd87f3dc61f06996239e9801ae62cf46ea1cd2485a`
- UEFIFind A75
  - Linux binary SHA-256: `0c1643e107a32580f3760c635ef1ba3145bf9178b977666869487fb15bd08a42`
- UEFIExtract / UEFIFind A73 retained as an independent cross-check because A73 still contained the experimental AMD Image parser
  - UEFIExtract A73 binary SHA-256: `a2ccf8525f060cf8e6ef6fe6ffe384678e5475fec7f51390532bf6e415fdda57`
  - UEFIFind A73 binary SHA-256: `948b80948602c58b92c985609a3137c07c26a22dad8af5e9475dcb2bcf98c9e1`

### HII / IFR

- IFRExtractor-RS v1.6.1
  - source commit: `b1b9b36c00e3209ff0b1d2a76f10cb17e339473d`
  - Linux binary SHA-256: `0c26953bd3b30bf9e44f4cc1babcec6c938816ccd3637946586f33602caf2d83`
- `bios-tuning`
  - source commit used: `874d44ea836e8fb5374addaed62f71f47ced2b6c`

### PE / TE analysis

- TE2PE source commit: `54fcf1c26f86e03e829a94476bd86d9e5bfb7d3e`
- local first-party helpers:
  - `scripts/pe_semantic_diff.py`
  - `scripts/asm_semantic_compare.py`

### ACPI / AML

- ACPICA / `iasl` release `20260408`
- the Linux tools were built from the official `acpica-unix-20260408.tar.gz`
- official source archive SHA-256: `e66ceb26d6d514ce164fe22f5a4f7ca165cc38349d7a97f41a21f19b364647a2`

The initial attempt to use extensionless GitHub ACPICA release executables produced Windows PE binaries. Those were rejected; native Linux tools were built from the official Unix source archive and `iasl` compile→AML→decompile smoke-tested before use.

## Analysis layers

### 1. Preserve original acquisition artifacts

For each downloaded firmware/package:

- record exact source URL and retrieval context;
- preserve original bytes outside Git;
- compute SHA-256 (and, where useful, SHA-512/CRC);
- validate archive integrity;
- extract package contents without altering originals.

### 2. Identify firmware lineage

For each `DRFXI.BIN`:

- record exact size and cryptographic hash;
- compute the vendor-style additive 16-bit checksum;
- compare against cumulative release notes;
- compare coarse 4 KiB block similarity where useful for parent identification.

### 3. UEFI / FFS structural inventory

- extract firmware volumes and FFS files;
- identify modules by UI names and GUIDs;
- compare added/removed/persistent modules across releases;
- do not assume a changed file hash means changed behavior.

### 4. HII / IFR semantic comparison

- extract HII/IFR from setup-bearing modules;
- compare forms, questions, VarStores, offsets, defaults and suppression/gray-out expressions;
- normalize QuestionId shifts and extractor metadata before calling something a semantic change;
- preserve focused excerpts for claims such as hidden User Defaults or Above 4G Decoding.

### 5. PE / TE code comparison

Raw byte comparison is only the first pass. Before interpreting code churn, normalize or account for:

- PE timestamps/checksums/debug data;
- relocation targets;
- RIP-relative displacement changes;
- branch/call target addresses;
- PCD-token renumbering;
- shared platform-address changes.

Classify resulting differences as:

1. build/relocation noise;
2. PCD-token renumbering;
3. shared platform constant change;
4. real data change;
5. real executable-logic change.

### 6. ACPI / AML analysis

- validate ACPI header length/checksum;
- decompile AML with the pinned ACPICA version;
- cross-reference helper methods across DSDT/SSDTs;
- distinguish raw template NameSegs/method names from values that OEM DXE code patches at runtime;
- use firmware debug strings only as supporting evidence, not proof by themselves.

## Confidence vocabulary

- **confirmed** — directly demonstrated by binary/HII/AML/code evidence;
- **strongly attributable** — a real change closely matches one changelog item, but an intermediate release is missing;
- **likely / inference** — technically plausible interpretation requiring another artifact or test;
- **unknown / unresolved** — evidence is insufficient and the gap is explicit.

## Publication / provenance rule

The repository stores independently written analysis, machine-readable facts, hashes, scripts and small evidence excerpts. Complete BIOS images, SPI dumps, full extracted firmware trees and wholesale decompilations remain outside Git and are referred to by SHA-256.

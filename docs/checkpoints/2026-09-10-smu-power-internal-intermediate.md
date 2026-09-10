# DRFXI 1.12 → 1.15 — `PSP_SMU_FN_FIRMWARE~0x108` intermediate checkpoint

Date: 2026-09-10  
Status: **incomplete / recovered after interrupted analysis**  
Scope: only the 1.15 changelog item:

```text
Update SMU for power limit
```

inside the replaced `PSP_SMU_FN_FIRMWARE~0x108`.

## Starting point already established

The decompressed SMU payloads are both exactly 262,144 bytes:

```text
1.12
version: 0.54.68.0
SHA256: 1a00faf2f497846bd0415c544510f212ea12d4f0753a7b19da24c098b25c8f6b

1.15
version: 0.54.6C.32
SHA256: fd45717e18d448bd0a72779b317123e24e90bf2d1b57b528033bdc9f93bc72ef
```

A raw fixed-offset diff reports ~64.7% differing bytes. The work in this turn shows that this number substantially overstates semantic change because large unchanged regions have moved.

## Firmware architecture / analysis model

An external AMD SMU reverse-engineering corpus (`bc250-collective/amd_smu_reverse_engineering`) documents this SMU family as Xtensa little-endian and imports trimmed SMU firmware into Ghidra at address 0. It also provides Xtensa Ghidra language fixes and a queue/message-table workflow.

That exact BC-250 firmware is not the DRFXI firmware, so this is a structural reference rather than proof that every internal table address/layout is identical.

For the DRFXI payloads, bytes beginning around `0x100` are consistent with executable Xtensa-style data/code rather than x86/ARM/ELF/PE. This turn did not complete an instruction-level decode, so the exact DRFXI core identification remains very likely Xtensa-le, not yet independently proven by successful disassembly.

## Important normalization result: the raw 64.7% diff is misleading

Content-based matching of unique 24/32-byte anchors reveals many long identical regions at shifted offsets.

Representative old → new offset deltas:

```text
old region                dominant new offset delta
0x00000–0x09FFF           +0x0000
around 0x0A000            +0x0020 / +0x0028
0x0B000–0x0DFFF           +0x0020
around 0x0E000            +0x0230
0x0F000–0x13FFF           +0x0300
old 0x1A000...            +0x1000
0x1B000–0x23FFF           +0x1038
0x26xxx–0x2Cxxx           +0x1070
0x31xxx–0x33xxx           +0x10F0
0x35xxx–0x3Axxx           +0x1140
around 0x3Dxxx            +0x11C8
```

Examples of very strong anchor populations:

```text
old 0x10000–0x10FFF: 3526/3526 unique anchors map at +0x300
old 0x11000–0x11FFF: 4003/4003 map at +0x300
old 0x12000–0x12FFF: 4096/4096 map at +0x300

old 0x26000–0x26FFF: 2111/2111 map at +0x1070
old 0x27000–0x27FFF: 1063/1063 map at +0x1070

old 0x38000–0x38FFF: 1060/1060 map at +0x1140
old 0x39000–0x39FFF: 1240/1240 map at +0x1140
old 0x3A000–0x3AFFF:  997/997 map at +0x1140
```

This proves that much of the apparent byte churn is existing code/data displaced by inserted or enlarged regions. A fixed-offset byte diff is unsuitable for finding the power-limit change.

## Layout growth

The end of the main populated payload moves approximately:

```text
1.12: ~0x3DAFD
1.15: ~0x3ECC5
difference: +0x11C8
```

A particularly large discontinuity occurs around the middle:

```text
1.12:
  populated region ends around 0x15A0F
  long zero gap
  populated/code-like data resumes at 0x1A000

1.15:
  corresponding early region ends around 0x15D33
  longer zero gap
  corresponding later code is displaced to about 0x1B000
```

Content anchors independently find the same approximate `+0x1000` shift for old code around `0x1A000`.

## Entropy / region triage

The payload is not uniformly executable code. It contains mixed low-offset data/code, large zero-filled reservations, high-entropy code-like regions, a large populated/code-like second half, and zero padding near the end.

No reliable semantic power-limit region was identified from entropy alone.

## String scan: negative result

ASCII extraction did not expose useful plaintext labels such as `PPT`, `TDP`, `sPPT`, `SetPPTLimit`, `SetSlowPPTLimit`, or `SetSustainedPowerLimit`. Most printable sequences are short accidental strings formed by instructions/data.

Therefore the BIOS-side message names cannot simply be located as strings inside the SMU image; message IDs/dispatch tables must be reconstructed.

## Tooling work completed

The active analysis environment was checked for instruction-level tools. Ghidra, Capstone, radare2/rizin, pypcode, angr/pyvex, unicorn, and an Xtensa-capable objdump were unavailable. Installed LLVM does not include Xtensa.

The GitHub connector could inspect the external AMD SMU reverse-engineering repository and confirmed the availability of Xtensa Ghidra language files and documentation for the queue/message workflow. A direct attempt to fetch that repository's binary reference firmware through the text-oriented connector failed because the file is binary/non-UTF-8.

## Confirmed so far

1. `PSP_SMU_FN_FIRMWARE~0x108` is genuinely replaced between 1.12 and 1.15.
2. The payload has a structured memory image with substantial zero/reserved areas and movable code/data regions.
3. The apparent ~64.7% fixed-offset byte difference is not ~64.7% semantic code replacement.
4. Large old regions survive byte-identically in 1.15 at predictable shifted addresses.
5. Multiple insertion/growth points exist; cumulative displacement reaches roughly `+0x11C8`.
6. Simple ASCII search is not a useful way to locate PPT/TDP/sPPT handling.
7. Instruction-level Xtensa analysis is the missing piece.

## Current hypotheses

- **Architecture — high confidence, not yet independently decoded:** Xtensa little-endian.
- **Nature of 1.15 update — high confidence:** real added/changed code/data exists, but much of the raw diff is layout movement.
- **`Update SMU for power limit` — unresolved internally:** no specific SMU handler/table/algorithm has yet been tied to PPT/TDP/sPPT.

There is not enough evidence yet to decide whether the vendor update is primarily a changed message handler, changed power-policy constants/tables, changed limit validation/clamping, changed PPTable ingestion, or a broader SMU release that incidentally contains the required fix.

## What remains to do

The next investigation should first obtain a working Xtensa-le instruction-level analysis path, preferably Ghidra headless with the known AMD SMU Xtensa language fixes.

Then, without reverse-engineering the entire firmware:

1. import both 256 KiB payloads at the same base address;
2. identify the SMU message queue/handler tables using the established AMD-SMU workflow;
3. enumerate handler pointers and message IDs in both versions;
4. derive/correlate BIOS-side message IDs for `SetPPTLimit`, `SetSlowPPTLimit`, `SetSustainedPowerLimit` and close relatives;
5. map corresponding 1.12/1.15 handler functions through the address shifts already discovered;
6. compare only those handlers and their directly referenced limit tables/data;
7. classify the change as code, data/constants, validation logic, or no semantic change in those handlers.

If the named handlers are unchanged, the next narrow target should be the table-transfer / PPTable path rather than broad firmware reverse engineering.

## Recommended immediate next step

Do not resume with more raw byte-diffing. Prepare a reproducible Xtensa/Ghidra analysis toolchain (or run Ghidra headless on the Ubuntu node), then perform a bounded message-table reconstruction for the two DRFXI SMU payloads.

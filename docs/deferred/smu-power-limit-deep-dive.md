# Deferred deep dive: `Update SMU for power limit`

Last updated: 2026-09-10

Status: **paused / deferred**.

This branch concerns the 1.15 changelog item:

```text
Update SMU for power limit
```

The current evidence is sufficient to establish that `PSP_SMU_FN_FIRMWARE~0x108` is materially replaced between DRFXI 1.12 and 1.15, but not to identify the exact internal SMU handler/table/algorithm responsible for the vendor's `for power limit` wording.

## Current evidence boundary

Known SMU payloads:

```text
1.12
version: 0.54.68.0
SHA256: 1a00faf2f497846bd0415c544510f212ea12d4f0753a7b19da24c098b25c8f6b

1.15
version: 0.54.6C.32
SHA256: fd45717e18d448bd0a72779b317123e24e90bf2d1b57b528033bdc9f93bc72ef
```

Both decompressed payloads are 262,144 bytes.

A naive fixed-offset diff reports ~64.7% differing bytes, but content-anchor matching proves that this strongly overstates semantic change: many large old regions survive byte-identically in 1.15 at shifted offsets. Representative displacement plateaus include `+0x300`, `+0x1038`, `+0x1070`, `+0x1140`, with cumulative layout growth reaching roughly `+0x11C8` near the end of the populated image.

Therefore further raw byte-diffing is not a useful next step.

The payload is very likely Xtensa little-endian AMD SMU firmware. An external AMD SMU reverse-engineering workflow (`bc250-collective/amd_smu_reverse_engineering`) provides Ghidra Xtensa language fixes and a message-queue reconstruction method, but DRFXI has not yet been independently decoded instruction-by-instruction.

The current checkpoint is preserved at:

```text
docs/checkpoints/2026-09-10-smu-power-internal-intermediate.md
```

## Why this branch is paused

Continuing now requires a qualitatively heavier reverse-engineering environment rather than another cheap binary-diff pass:

```text
Ghidra 12.1+ / headless
JDK 21
Xtensa-le language support / AMD SMU fixes
message-table reconstruction scripts
```

The Ghidra distribution itself is roughly a 0.5-0.6 GB download and about 1 GB installed; with JDK, projects and cache, a practical persistent environment is roughly 1-2 GB.

More importantly, the analysis cost is no longer the disk footprint. The remaining work likely spans several bounded investigations: validate Xtensa decoding, reconstruct queue/message tables, correlate message IDs with BIOS-side power-limit commands, function-match 1.12↔1.15, then inspect only the handlers/tables that actually changed.

This is worth doing when either:

- another DRFXI/AMD firmware question also requires Ghidra/Xtensa;
- a reusable `drfxi-re` reverse-engineering environment is being set up anyway;
- stronger evidence appears that specifically requires the internal SMU implementation.

## Resume plan

When this branch is resumed, do **not** restart with raw byte comparison.

The first bounded task should be:

1. install/validate a reproducible Ghidra headless + Xtensa-le environment;
2. import both 256-KiB SMU payloads at base address 0;
3. verify decoding using recognizable AMD SMU control-flow/message-queue structure;
4. reconstruct only the message queue/handler tables;
5. identify the SMU-side handlers corresponding to BIOS-side `SetPPTLimit`, `SetSlowPPTLimit`, `SetSustainedPowerLimit` and close relatives;
6. compare only those handlers and directly referenced constants/tables across 1.12 and 1.15.

If the named handlers are semantically unchanged, the next narrow target is the PPTable/table-transfer path and power-policy constants consumed by those handlers.

## Confidence snapshot

**Confirmed:** `PSP_SMU_FN_FIRMWARE~0x108` is genuinely replaced and contains real added/changed code/data.

**Confirmed:** much of the apparent 64.7% raw diff is layout movement rather than semantic replacement.

**High-confidence attribution:** this firmware replacement is the binary object referred to by `Update SMU for power limit`.

**Unresolved:** exact internal handler/table/algorithm responsible for the power-limit behavior.

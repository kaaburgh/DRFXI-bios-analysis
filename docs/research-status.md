# Research status

Last updated: 2026-09-10

This is the **living checkpoint** for the investigation. Dated reports under `docs/checkpoints/` are immutable snapshots and may contain conclusions that were later refined.

## Firmware corpus

Primary official images currently analyzed:

| Version | Date | DRFXI.BIN SHA-256 | Vendor 16-bit checksum | Status |
|---|---|---|---|---|
| 1.12 | 2025-02-13 | `246e7f54a12a8c7279ef68433602264b8ecbabcde828c9c9008f571c270845b9` | `9A63` | acquired |
| 1.15 | 2026-01-05 | `3afaba6d916b3897d1d98bd5913008b38e89b6c51b2c6963c7109793541d8d88` | `A4C4` | acquired |
| 1.17 | 2026-08-28 | `99f3bab5ea491202bf365c23e6416f9d1e8a649ad00f90c1f3e21f1a61e35c51` | `4B54` | acquired |

Reference images:

- 1.04 and 1.07 distribution images were also acquired and structurally validated.
- community `795iX3D.bin`: `c63971eedd2e03005aaeba2786aa7834b38c8ac006978e9a011156ee61122b15`.

Missing but confirmed releases:

- 1.13 — 2025-09-28, checksum `BF21`
- 1.14 — 2025-11-13, checksum `419D`
- 1.16 — 2026-06-03, checksum `1EA3`

The exact 1.16 distribution file has not been recovered. This means every 1.15→1.17 attribution must distinguish what is known from what is only temporally inferred.

## Current high-confidence findings

### HII / IFR

- The principal `CbsSetupDxeRPL` HII/IFR content is semantically unchanged across 1.12, 1.15 and 1.17 after extractor metadata/noise is removed.
- Hidden AMD CBS/UMC controls therefore remain present in newer releases, including DRAM primary/secondary/tertiary timings, ODT/drive strengths, Power Down, TSME, training, ECC and related controls.
- `Save as User Defaults` and `Restore User Defaults` exist in all three versions but are nested under unconditional `SuppressIf` expressions.
- No evidence yet establishes an ASUS-style multi-slot named OC profile manager; the confirmed feature is AMI user-default save/restore.
- `Above 4G Decoding` is visible in 1.12 and only the already-suppressed copy remains in 1.15/1.17. This directly matches the 1.14 changelog.
- `AMD Variable Protection` appears by 1.15 at `AmdPbsSetupDxe` VarOffset `0x91`, default Enabled, together with new `AmdVariableProtection.efi`.

### Community 795iX3D modification

- The image is overwhelmingly based on stock 1.12.
- 398/399 parsed FFS files in the main UEFI volume are byte-identical to stock 1.12.
- The only intentional UEFI change is `AMITSESetupData` (`FE612B72-203C-47B1-8560-A66D946EB371`).
- After inner decompression, exactly 60 bytes differ; every change sets bit `0x04`, consistent with a bulk AMIBCP access-level/visibility change.
- The full image also contains donor-board NVRAM/APOB/APCB/boot/security state, so it should be treated as a reference SPI readback, not a clean portable flash image.

### 1.17 dGPU / iGPU behavior

- New executable logic is localized to `OemDxe.efi`.
- It scans PCIe for a display-class device, accesses `AmdSetupRPL`, and changes offset `0x44` (`iGPU Configuration`).
- Observed transitions match the 1.17 changelog behavior: presence/absence of a dGPU can force iGPU Disabled or UMA_SPECIFIED and trigger a hard reset.

### DMI

A raw SMBIOS/DMI data FFS shows real string changes between 1.12 and 1.15, including:

- `MotherBoard Series` → `DeskMini Series`
- `MotherBoard` → `MINISFORUM`
- `Shenzhen Meigao Electronic Equipment Co.,Ltd` → `Meigao Innovation Technology (Shen Zhen) Co., Ltd`

The manufacturer-name change directly corresponds to the 1.14 changelog; some adjacent DMI changes cannot be assigned to 1.14 vs 1.15 without those intermediate binaries.

### 1.16 flash-driver candidate

Between 1.15 and 1.17, `ReFlash.efi`, `FlashDriver.efi`, and `FlashDriverSmm.efi` change materially. `ReFlash` also loses much of the older partial-update/NVRAM-reset UI and changes its post-flash reboot behavior. This is strongly attributable to the 1.16 changelog item `Add AMI flash driver EIP`, but the missing 1.16 binary prevents exact temporal proof.

### 1.16 S3 workaround candidate

The strongest candidate is **not** a patch in the obvious legacy S3 modules; those mostly show PCD-token renumbering. Instead, 1.17 contains a new `AmdCpmOemAcpi.efi` package absent from 1.15.

Important evidence:

- its DEPEX explicitly depends on `EfiS3SaveStateProtocolGuid`;
- it carries four new SSDTs: `GPIO`, `EXTGPP00`, `GPP_PME_`, `PT`;
- `PT` provides 58 generated PCIe power-transition nodes with `_PRW`, `_DSW`, `_PS0`, `_PS3`, and `PWRS` resources;
- `_PS3` conditionally performs a `CpmSendPmeTurnOff` hardware handshake and records a D3-transition marker;
- the matching `_PS0` enables `CpmWakeLink`, polls for PCIe `DL_ACTIVE` / training completion for up to ~500 ms, then disables WakeLink;
- `GPP_PME_` provides a dynamically retargeted edge-triggered GPE handler for PCIe PME/wake processing;
- `AmdCpmOemAcpi` patches placeholder PCIe NameSegs and the raw `_E10` handler name at runtime according to platform data.

This is high-confidence S3/PCIe power-resume machinery. Associating it specifically with 1.16's `Workaround abnormal restart after S3` is medium/high confidence because the 1.17 changelog only describes graphics behavior; exact temporal proof still requires 1.16.

**Status:** this branch is intentionally paused. The existing evidence is sufficient for the current research goal; the deferred follow-up plan is recorded in [`findings/s3-workaround.md`](findings/s3-workaround.md#deferred-follow-up-roadmap).

### Undocumented 1.17 functionality

1.17 introduces:

- `TcgStorageSecurity.efi`
- `SmmTcgStorageSec.efi`
- `TcgStorageDynamicSetupVar`
- two `TCG Storage device Security Configuration` forms

This functionality is not mentioned in the known 1.16/1.17 changelog and is currently classified as a confirmed released change with undocumented provenance.

## Methodological finding: raw module counts overstate change

Initial exact-file comparison reported 181 changed PE modules for 1.12→1.15 and 118 for 1.15→1.17. These counts substantially overstate semantic change because PI/platform updates renumber PCD tokens and alter build/relocation metadata in many otherwise-equivalent modules.

Future code comparison therefore classifies differences as:

1. build/relocation noise;
2. PCD-token renumbering;
3. global platform-constant changes;
4. real data changes;
5. real executable-logic changes.

## Active open questions

Highest-value unresolved work outside the paused S3 branch:

1. obtain 1.16 to resolve 1.16-vs-1.17 attribution across several findings;
2. locate the actual `Set TCC to 100` / `Update SMU for power limit` changes in APCB/AGESA/SMU/config/default data;
3. determine the exact implementation of the Intel LAN OPROM POST-hang fix, with `Bds.efi` currently the strongest remaining code candidate;
4. classify remaining normalized PE/FFS changes as changelog-explained, likely-related, or undocumented;
5. derive a clean, version-aware unlock strategy for memory controls and Save/Restore User Defaults without transplanting donor-board state.

## Deferred branches

### S3 / PCIe power-resume

Do not continue this branch by default. Resume only when it becomes useful again or when new evidence, especially DRFXI 1.16, appears.

The next-step roadmap is maintained in [`findings/s3-workaround.md`](findings/s3-workaround.md#deferred-follow-up-roadmap). The highest-value future step is still recovery of the 1.16 image; deeper static analysis without it has diminishing returns.

## Rule for future updates

Update this file when conclusions change. Preserve the original dated checkpoints under `docs/checkpoints/` rather than rewriting history.

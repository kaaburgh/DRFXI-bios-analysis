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

The missing intermediate binaries limit exact temporal attribution. In particular, 1.12→1.15 observations may include changes from 1.13, 1.14, 1.15, or undocumented work between those releases.

## Current high-confidence findings

### HII / IFR

- The principal `CbsSetupDxeRPL` HII/IFR content is semantically unchanged across 1.12, 1.15 and 1.17 after extractor metadata/noise is removed.
- Hidden AMD CBS/UMC controls remain present in newer releases, including DRAM primary/secondary/tertiary timings, ODT/drive strengths, Power Down, TSME, training, ECC and related controls.
- `Save as User Defaults` and `Restore User Defaults` exist in all three versions but are nested under unconditional `SuppressIf` expressions.
- No evidence yet establishes an ASUS-style multi-slot named OC profile manager; the confirmed feature is AMI user-default save/restore.
- `Above 4G Decoding` is visible in 1.12 and only the already-suppressed copy remains in 1.15/1.17. This directly matches the 1.14 changelog.
- `AMD Variable Protection` appears by 1.15 at `AmdPbsSetupDxe` VarOffset `0x91`, default Enabled, together with new `AmdVariableProtection.efi`.

### 1.15 TCC / SMU power changes

`Set TCC to 100` is localized end-to-end at BIOS→SMU level.

The early PEI `PcdPeim` database contains the only changed pre-existing scalar default after semantic token normalization:

```text
1.12 local token: 209 (0xD1)
1.15 local token: 212 (0xD4)
same descriptor:  0x0400009C
PCD type:         DATA / UINT32
Database offset:  0x9C
Static default:   91 -> 100
```

Three newly inserted ordinary Dynamic BOOLEAN tokens account for the `+3` local-token shift.

The consumer trace found two direct reads in `SmuV13Dxe`:

1. RVA `0x1B99`: reads token 209/212, passes the value to the SMU request with message ID `0x3F`, and references `BIOSSMC_MSG_SetTjMax %x`.
2. RVA `0x2D1D`: reads the same PCD into a PPTable/default-infrastructure field whose diagnostic dump labels it `TjMax`.

`AodPei` can overwrite this PCD when `Platform Thermal Throttle Ctrl` is Manual, using `Platform Thermal Throttle Limit` as the replacement value.

Assessment: **very high confidence** that the `91 -> 100` PCD change is the implementation of `Set TCC to 100`:

```text
PcdPeim default 91 -> 100
    ↓
SmuV13Dxe PcdGet32
    ↓
BIOSSMC_MSG_SetTjMax
```

The source-level PCD CName is unavailable because `PcdNameTableOffset = 0`. The path also does not prove that every supported CPU accepts 100°C as its final silicon limit; downstream SMU policy may clamp or reinterpret the request.

Separately, `PSP_SMU_FN_FIRMWARE~0x108` is materially replaced between 1.12 and 1.15: embedded version `0.54.68.0 → 0.54.6C.32`, both decompressed images 256 KiB. Raw fixed-offset diff is 64.68%, but content-based normalization proves that large regions are preserved at shifted offsets and much of that figure is layout movement. Internal localization of the `Update SMU for power limit` behavior is intentionally deferred until a reusable Ghidra/Xtensa-le environment is justified.

See `findings/smu-power-limit.md`, `findings/tcc-pcd-consumer.md`, and `deferred/smu-power-limit-deep-dive.md`.

### Intel LAN OPROM POST-logo fix

Known 1.13 changelog item:

```text
Fix hang at POST logo caused by Intel LAN OPROM
```

A focused 1.12→1.15 BDS/Option-ROM pass substantially narrows the search:

- `LanRomDriver`, `UefiPxeBcDxe`, `SnpDxe`, `NetworkStackSetupScreen`, and `RomLayoutDxe` PE images are byte-identical.
- `OptionRomPolicy` differs by exactly 11 bytes, all `+3` PCD-token renumberings; its logic and Option-ROM policy strings are unchanged.
- `PciBus` differs by exactly two bytes, both one token moving `0x3D0→0x3D4`; its executable semantics are unchanged.
- `Bds.efi` grows substantially (`76,928→100,096` bytes; `.text +0x4410`), but content anchors show old code surviving at shifted addresses rather than a wholesale rewrite.
- A conspicuous new BDS path checks PCI base class `0x03`, references `PciRoot(0x0)/Pci(0x8,0x1)`, manages `AmiGopOutputDp`, and performs device-path/`ConnectController` work. It is strongly identified as display/GOP code, not LAN.
- The identifiable BDS Network Controller path checks PCI base class `0x02` at RVA `0x2A95` and `0x2D31` in both versions and is semantically unchanged after helper-address normalization.
- No newly introduced literal Intel vendor-ID `0x8086` special case was found in the changed candidates.

This **downgrades the earlier hypothesis that BDS growth itself points to the LAN fix**. A subtle generic BDS connect/dispatch/order workaround remains possible, but broad BDS reverse engineering is no longer the best next move.

The major unresolved artifact is the actual physical Intel LAN PCI Option-ROM payload. A top-level `PCIR` scan cannot exclude compressed/AMI-encapsulated ROM data, so byte identity of `LanRomDriver.efi` does not prove the real LAN OPROM binary is unchanged.

Next step: identify the exact FFS/raw/compressed object carrying the Intel LAN Option ROM in 1.12 and 1.15, compare that object, and trace only its dispatch route. See `findings/intel-lan-oprom.md` and `checkpoints/2026-09-10-intel-lan-oprom-bds.md`.

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

The manufacturer-name change directly corresponds to the 1.14 changelog; adjacent DMI changes cannot be assigned to 1.14 vs 1.15 without those intermediate binaries.

### 1.16 flash-driver candidate

Between 1.15 and 1.17, `ReFlash.efi`, `FlashDriver.efi`, and `FlashDriverSmm.efi` change materially. `ReFlash` loses much of the older partial-update/NVRAM-reset UI and changes its post-flash reboot behavior. This is strongly attributable to the 1.16 changelog item `Add AMI flash driver EIP`, but the missing 1.16 binary prevents exact temporal proof.

### 1.16 S3 workaround candidate

1.17 contains a new `AmdCpmOemAcpi.efi` package absent from 1.15. Its DEPEX depends on `EfiS3SaveStateProtocolGuid`, and its new SSDTs implement PCIe PME/power/resume behavior including a `CpmSendPmeTurnOff → CpmWakeLink → DL_ACTIVE` handshake.

This is high-confidence S3/PCIe power-resume machinery and a medium/high-confidence match for 1.16's `Workaround abnormal restart after S3`, but exact temporal proof still requires 1.16.

**Status:** intentionally paused. Deferred follow-up is recorded in `findings/s3-workaround.md`.

### Undocumented 1.17 functionality

1.17 introduces `TcgStorageSecurity.efi`, `SmmTcgStorageSec.efi`, `TcgStorageDynamicSetupVar`, and two `TCG Storage device Security Configuration` forms. This functionality is not mentioned in the known 1.16/1.17 changelog and is currently classified as a confirmed released change with undocumented provenance.

## Methodological findings

Raw module counts substantially overstate semantic change because PI/platform updates renumber PCD tokens and alter build/relocation metadata in many otherwise-equivalent modules.

Code comparison therefore separates:

1. build/relocation noise;
2. PCD-token renumbering;
3. global platform-constant changes;
4. real data changes;
5. real executable-logic changes.

The TCC analysis provides an end-to-end normalization example: three inserted Dynamic tokens shift local token `209 -> 212`, while the descriptor and consumer semantics remain stable.

The Intel-LAN pass provides a second example: large raw BDS growth was initially suspicious, but content anchors and focused class-specific control-flow comparison separated unrelated new GOP code from unchanged network handling.

## Active open questions

Highest-value unresolved work outside deferred branches:

1. identify the exact physical Intel LAN Option-ROM object and determine whether the 1.13 POST-logo fix changed the payload or only its dispatch route;
2. obtain 1.13 / 1.14 / 1.16 to resolve intermediate-release attribution;
3. classify remaining normalized PE/FFS changes as changelog-explained, likely-related, or undocumented;
4. derive a clean, version-aware unlock strategy for memory controls and Save/Restore User Defaults without transplanting donor-board state.

Optional TCC follow-up is no longer on the critical path: recover the source-level PCD CName or verify effective thermal limits dynamically on hardware.

## Deferred branches

### `Update SMU for power limit` internals

Do not continue with raw byte diffing. Resume when a reusable Ghidra 12.1+/Xtensa-le toolchain is justified by enough reverse-engineering work. See `deferred/smu-power-limit-deep-dive.md`.

### S3 / PCIe power-resume

Do not continue this branch by default. Resume when useful again or when new evidence, especially DRFXI 1.16, appears. See `findings/s3-workaround.md`.

## Rule for future updates

Update this file when conclusions change. Preserve original dated checkpoints under `docs/checkpoints/` rather than rewriting history.

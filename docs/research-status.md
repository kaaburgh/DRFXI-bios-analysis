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
- Hidden AMD CBS/UMC controls remain present in newer releases, including DRAM primary/secondary/tertiary timings, ODT/drive strengths, Power Down, TSME, training, ECC and related controls.
- `Save as User Defaults` and `Restore User Defaults` exist in all three versions but are nested under unconditional `SuppressIf` expressions.
- No evidence yet establishes an ASUS-style multi-slot named OC profile manager; the confirmed feature is AMI user-default save/restore.
- `Above 4G Decoding` is visible in 1.12 and only the already-suppressed copy remains in 1.15/1.17. This directly matches the 1.14 changelog.
- `AMD Variable Protection` appears by 1.15 at `AmdPbsSetupDxe` VarOffset `0x91`, default Enabled, together with new `AmdVariableProtection.efi`.

### 1.15 TCC / SMU power changes

Both 1.15 changelog entries now have strong binary anchors, and the TCC consumer path is closed at BIOS→SMU level.

`Set TCC to 100` is localized in the early PEI `PcdPeim` database:

```text
1.12 local token: 209 (0xD1)
1.15 local token: 212 (0xD4)
same descriptor:  0x0400009C
PCD type:         DATA / UINT32
Database offset:  0x9C
Static default:   91 -> 100
```

This is the only changed pre-existing scalar default after semantic token normalization. Three newly inserted ordinary Dynamic BOOLEAN tokens account for the `+3` local-token shift.

The consumer trace found exactly two direct native-PCD `Get32` literal-token sites, both in `SmuV13Dxe`:

1. RVA `0x1B99`: reads token 209/212, passes the value as the SMU request argument with message ID `0x3F`, and references the firmware diagnostic identity `BIOSSMC_MSG_SetTjMax %x`.
2. RVA `0x2D1D`: reads the same PCD and stores it at offset `+0x10` of a PPTable/default-infrastructure structure whose diagnostic dump labels that field `TjMax`.

`AodPei` provides the corresponding PEI writer. If AOD `Platform Thermal Throttle Ctrl` (VarOffset `0xB1`) is Manual, it reads `Platform Thermal Throttle Limit` (VarOffset `0xB2`) and calls `PcdPpi->Set32` on the same target token. Thus the static platform value can be replaced by an explicit lower thermal limit before DXE.

Current assessment: **very high confidence** that the `91 -> 100` PCD change is the code/data implementation of `Set TCC to 100`:

```text
PcdPeim default 91 -> 100
    ↓
SmuV13Dxe PcdGet32
    ↓
BIOSSMC_MSG_SetTjMax
```

The exact source-level PCD CName is still absent because `PcdNameTableOffset = 0`. This does not block the consumer-path attribution. It also does not prove that every supported CPU ultimately accepts 100°C as its effective silicon limit; downstream SMU policy can still clamp or reinterpret the request.

Separately, `PSP_SMU_FN_FIRMWARE~0x108` is materially replaced between 1.12 and 1.15. Its embedded version field changes `0.54.68.0 → 0.54.6C.32`, and 64.68% of the decompressed 256-KiB firmware differs. This remains the strongest binary match for `Update SMU for power limit`; the exact internal SMU routine/table is not yet localized.

See [`findings/smu-power-limit.md`](findings/smu-power-limit.md), [`findings/tcc-pcd-consumer.md`](findings/tcc-pcd-consumer.md), and [`checkpoints/2026-09-10-tcc-pcd-consumer.md`](checkpoints/2026-09-10-tcc-pcd-consumer.md).

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

Between 1.15 and 1.17, `ReFlash.efi`, `FlashDriver.efi`, and `FlashDriverSmm.efi` change materially. `ReFlash` also loses much of the older partial-update/NVRAM-reset UI and changes its post-flash reboot behavior. This is strongly attributable to the 1.16 changelog item `Add AMI flash driver EIP`, but the missing 1.16 binary prevents exact temporal proof.

### 1.16 S3 workaround candidate

1.17 contains a new `AmdCpmOemAcpi.efi` package absent from 1.15. Its DEPEX depends on `EfiS3SaveStateProtocolGuid`, and its new SSDTs implement PCIe PME/power/resume behavior including a `CpmSendPmeTurnOff → CpmWakeLink → DL_ACTIVE` handshake.

This is high-confidence S3/PCIe power-resume machinery and a medium/high-confidence match for 1.16's `Workaround abnormal restart after S3`, but exact temporal proof still requires 1.16.

**Status:** this branch is intentionally paused. Deferred follow-up is recorded in [`findings/s3-workaround.md`](findings/s3-workaround.md#deferred-follow-up-roadmap).

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

The TCC analysis provides a concrete end-to-end normalization example: three inserted Dynamic tokens shift the local token number `209 -> 212`, while the unchanged descriptor identifies the same PCD and the matched consumer instructions preserve exactly the same semantics.

## Active open questions

Highest-value unresolved work outside the paused S3 branch:

1. identify the internal change(s) in `PSP_SMU_FN_FIRMWARE~0x108` responsible for the 1.15 `Update SMU for power limit` wording;
2. obtain 1.16 to resolve 1.16-vs-1.17 attribution across several findings;
3. determine the exact implementation of the Intel LAN OPROM POST-hang fix, with `Bds.efi` currently the strongest remaining code candidate;
4. classify remaining normalized PE/FFS changes as changelog-explained, likely-related, or undocumented;
5. derive a clean, version-aware unlock strategy for memory controls and Save/Restore User Defaults without transplanting donor-board state.

Optional TCC follow-up is no longer on the critical path: recover the source-level PCD CName from matching debug/source metadata or verify effective thermal limits dynamically on hardware.

## Deferred branches

### S3 / PCIe power-resume

Do not continue this branch by default. Resume only when useful again or when new evidence, especially DRFXI 1.16, appears. See [`findings/s3-workaround.md`](findings/s3-workaround.md#deferred-follow-up-roadmap).

## Rule for future updates

Update this file when conclusions change. Preserve original dated checkpoints under `docs/checkpoints/` rather than rewriting history.

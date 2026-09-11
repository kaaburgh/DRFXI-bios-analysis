# Changelog ↔ firmware evidence mapping

Last updated: 2026-09-11

This file tracks how published changelog items map to actual HII/data/code changes. It deliberately separates direct evidence from plausible attribution.

| Release item | Current evidence | Confidence | Remaining gap |
|---|---|---|---|
| 1.13 `Update PI 1.0.0.3h` | AMD documentation identifies the relevant Ryzen 7045 branch as `DragonRangeFL1PI 1.0.0.3h` and lists it as the mitigation level for CVE-2024-36311. Across 1.12→1.15, a genuine `AmdVariableProtection` + `GenerateTimeBaseVariable` cluster appears, separate AMI `HardwareSignatureEntry` appears, and PCI MMCONFIG moves `F0000000→E0000000`. The immediate `NvramDxe` VariablePolicy/VarCheck provider remains semantically unchanged after PCD/build normalization. | **high** for identifying the upstream PI revision; **low/medium** for assigning individual 1.12→1.15 deltas to that landing | missing 1.13/1.14 binaries and no AMD source/version manifest; next evidence-driven target is the SMM communication-buffer component associated with CVE-2024-36311 |
| 1.13 Intel LAN OPROM POST-hang fix | generic firmware dispatch/load/notify/network paths were closed negative; exact problem NIC is unknown; X710-DA2/I40e is the best board-specific candidate found but unproven | low/medium attribution, investigation paused | obtain the actual problem NIC/ROM, or use an X710-DA2 Option ROM as a surrogate before resuming |
| 1.14 DMI manufacturer update | SMBIOS/DMI data shows exact manufacturer/product string changes by 1.15 | high | cannot separate every neighboring DMI change between 1.14 and 1.15 |
| 1.14 `Hide Above 4G Decoding` | visible 1.12 HII copy disappears; only permanently suppressed copy remains in 1.15/1.17 | **confirmed** | none for behavior; intermediate binary would only confirm exact landing release |
| 1.15 `Set TCC to 100` | PcdPeim default `91→100` is consumed by `SmuV13Dxe` and sent through `BIOSSMC_MSG_SetTjMax` | **very high / effectively localized** | optional source-level PCD CName or runtime effective-limit validation |
| 1.15 `Update SMU for power limit` | embedded `PSP_SMU_FN_FIRMWARE~0x108` changes `0.54.68.0→0.54.6C.32`; fixed-offset churn includes substantial layout movement | medium | internal behavior attribution deferred until a reusable Xtensa-le reverse-engineering environment is justified |
| 1.15 `Update DMI` | additional SMBIOS/DMI product strings changed by 1.15 | high | distinguish 1.14-vs-1.15 portions |
| 1.16 S3 abnormal-restart workaround | new `AmdCpmOemAcpi` package; DEPEX on S3 Save State; new SSDTs implement PCIe PME_Turn_Off → WakeLink → DL_ACTIVE power-resume flow; related FADT handling changes | **strongly attributable** | missing 1.16 binary prevents exact temporal proof |
| 1.16 `Add AMI flash driver EIP` | `ReFlash`, `FlashDriver`, `FlashDriverSmm` change materially; ReFlash UI and post-flash reboot flow change | strong | missing 1.16 binary; deeper code attribution still desirable |
| 1.17 dGPU/iGPU behavior | new `OemDxe` code scans PCI display devices, manipulates `AmdSetupRPL` offset `0x44` (`iGPU Configuration`), and hard-resets when required | **confirmed** | annotate exact function/callback boundaries |

## Released changes not individually explained by known changelog

### AMD Variable Protection

By 1.15, `AmdPbsSetupDxe` exposes a new default-enabled `AMD Variable Protection` option at offset `0x91`. The new `AmdVariableProtection.efi` is a real VariablePolicy/VarCheck consumer protecting AMD setup variables, while the new `GenerateTimeBaseVariable.efi` application generates authenticated create/delete payloads for the same `AmdVariableProtection` variable GUID.

This is a coherent feature cluster and is plausible platform-integration work associated with the PI update. It is **not yet proven to have landed specifically in 1.13 / DragonRangeFL1PI 1.0.0.3h**.

### HardwareSignatureEntry

By 1.15, AMI `HardwareSignatureEntry` is newly present. Direct GUID/string evidence and matching public AMI source-family code identify it as HardwareChange/FACS hardware-signature management. No immediate dependency connects it to AMD Variable Protection, so it should not be folded into that feature merely because both appear in the same 1.12→1.15 interval.

### TCG Storage Security

By 1.17, the firmware adds `TcgStorageSecurity.efi`, `SmmTcgStorageSec.efi`, a new dynamic setup VarStore and two `TCG Storage device Security Configuration` forms. No known 1.16/1.17 changelog line explicitly describes this feature.

## Interpretation rule

Do not equate "changed file" with "changed behavior." A large amount of firmware byte churn has been traced to PCD-token renumbering, relocation/build metadata and shared platform constants. Changelog mapping should rely on normalized code/data evidence whenever possible.

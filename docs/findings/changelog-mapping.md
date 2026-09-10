# Changelog ↔ firmware evidence mapping

Last updated: 2026-09-10

This file tracks how published changelog items map to actual HII/data/code changes. It deliberately separates direct evidence from plausible attribution.

| Release item | Current evidence | Confidence | Remaining gap |
|---|---|---|---|
| 1.13 `Update PI 1.0.0.3h` | very broad PE churn; many modules differ only by PCD-token renumbering; new `AmdVariableProtection.efi`, `GenerateTimeBaseVariable.efi`, `HardwareSignatureEntry.efi` appear by 1.15 | medium | missing 1.13/1.14 binaries prevent temporal isolation; need normalized PI component comparison |
| 1.13 Intel LAN OPROM POST-hang fix | obvious LAN ROM/network modules are byte-identical or near-identical; `Bds.efi` changes materially | low/medium | need normalized BDS/Option-ROM dispatch analysis |
| 1.14 DMI manufacturer update | SMBIOS/DMI data shows exact manufacturer/product string changes by 1.15 | high | cannot separate every neighboring DMI change between 1.14 and 1.15 |
| 1.14 `Hide Above 4G Decoding` | visible 1.12 HII copy disappears; only permanently suppressed copy remains in 1.15/1.17 | **confirmed** | none for behavior; intermediate binary would only confirm exact landing release |
| 1.15 `Set TCC to 100` | no obvious semantic change in `SmuV13Dxe` HII/code; current candidates are configuration/default/APCB/AGESA data | unresolved | find actual data/default change |
| 1.15 `Update SMU for power limit` | `SmuV13Dxe`/PEI diffs largely PCD renumbering; code already contains PPT/SustainedPower messages | unresolved | inspect APCB/AGESA/SMU configuration blobs/defaults |
| 1.15 `Update DMI` | additional SMBIOS/DMI product strings changed by 1.15 | high | distinguish 1.14-vs-1.15 portions |
| 1.16 S3 abnormal-restart workaround | new `AmdCpmOemAcpi` package; DEPEX on S3 Save State; new SSDTs implement PCIe PME_Turn_Off → WakeLink → DL_ACTIVE power-resume flow; related FADT handling changes | **strongly attributable** | missing 1.16 binary prevents exact temporal proof |
| 1.16 `Add AMI flash driver EIP` | `ReFlash`, `FlashDriver`, `FlashDriverSmm` change materially; ReFlash UI and post-flash reboot flow change | strong | missing 1.16 binary; deeper code attribution still desirable |
| 1.17 dGPU/iGPU behavior | new `OemDxe` code scans PCI display devices, manipulates `AmdSetupRPL` offset `0x44` (`iGPU Configuration`), and hard-resets when required | **confirmed** | annotate exact function/callback boundaries |

## Released changes not explained by known changelog

### AMD Variable Protection

By 1.15, `AmdPbsSetupDxe` exposes a new default-enabled `AMD Variable Protection` option at offset `0x91`, and the firmware gains `AmdVariableProtection.efi`. This may be part of PI 1.0.0.3h, but no known changelog line names it.

### TCG Storage Security

By 1.17, the firmware adds `TcgStorageSecurity.efi`, `SmmTcgStorageSec.efi`, a new dynamic setup VarStore and two `TCG Storage device Security Configuration` forms. No known 1.16/1.17 changelog line explicitly describes this feature.

## Interpretation rule

Do not equate "changed file" with "changed behavior." A large amount of firmware byte churn has been traced to PCD-token renumbering, relocation/build metadata and shared platform constants. Changelog mapping should rely on normalized code/data evidence whenever possible.

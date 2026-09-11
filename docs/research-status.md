# Research status

Last updated: 2026-09-11

This is the **living checkpoint** for the investigation. Dated reports under `docs/checkpoints/` are historical snapshots and may contain conclusions later refined here.

## Firmware corpus

Primary official images currently analyzed:

| Version | Date | DRFXI.BIN SHA-256 | Vendor 16-bit checksum | Status |
|---|---|---|---|---|
| 1.12 | 2025-02-13 | `246e7f54a12a8c7279ef68433602264b8ecbabcde828c9c9008f571c270845b9` | `9A63` | acquired |
| 1.15 | 2026-01-05 | `3afaba6d916b3897d1d98bd5913008b38e89b6c51b2c6963c7109793541d8d88` | `A4C4` | acquired |
| 1.17 | 2026-08-28 | `99f3bab5ea491202bf365c23e6416f9d1e8a649ad00f90c1f3e21f1a61e35c51` | `4B54` | acquired |

Reference images:

- 1.04 and 1.07 distribution images are also acquired and structurally validated.
- community `795iX3D.bin`: `c63971eedd2e03005aaeba2786aa7834b38c8ac006978e9a011156ee61122b15`.

Missing but confirmed releases:

- 1.13 — 2025-09-28, checksum `BF21`
- 1.14 — 2025-11-13, checksum `419D`
- 1.16 — 2026-06-03, checksum `1EA3`

The missing intermediate binaries remain the main limit on exact temporal attribution: a 1.12→1.15 delta may belong to 1.13, 1.14, 1.15, or undocumented work between them.

## Current high-confidence findings

### HII / IFR

- Principal `CbsSetupDxeRPL` HII/IFR content is semantically unchanged across 1.12, 1.15 and 1.17 after extractor metadata/noise is removed.
- Hidden AMD CBS/UMC controls remain present in newer releases, including DRAM timings, ODT/drive strengths, Power Down, TSME, training, ECC and related controls.
- `Save as User Defaults` and `Restore User Defaults` exist in all three versions but remain under unconditional `SuppressIf` expressions.
- No evidence establishes an ASUS-style multi-slot named OC-profile manager; the confirmed facility is AMI user-default save/restore.
- `Above 4G Decoding` is visible in 1.12; by 1.15/1.17 only the already-suppressed copy remains. This directly matches the 1.14 changelog.

### 1.13 `Update PI 1.0.0.3h`

The first bounded PI pass is complete.

Official AMD documentation identifies the relevant Ryzen 7045 / Dragon Range branch as **DragonRangeFL1 / DragonRangeFL1PI** and explicitly names `1.0.0.3h`. AMD's security bulletin lists `DragonRangeFL1_1.0.0.3h` as the mitigation level for CVE-2024-36311, an SMM communications-buffer TOCTOU validation issue, with release date 2025-03-18.

This establishes with high confidence that the MINISFORUM changelog's `PI 1.0.0.3h` is AMD Dragon Range PI, not vendor-local numbering.

Across the available 1.12→1.15 boundary, the three newly named PE modules were classified:

#### AMD Variable Protection cluster

`AmdVariableProtection.efi` is a genuine new AMD-specific variable-policy consumer. It:

- depends on Variable Write, PCD and either EDKII VariablePolicy or VarCheck;
- protects AMD setup variables including `AMD_PBS_SETUP`, `AmdSetupRPL` and `AodSetupRpl`;
- manages the separate `AmdVariableProtection` variable, GUID `40578F3D-65EE-49ED-8BC5-5A32BBEAE745`;
- uses embedded authenticated create/delete payloads and runtime `GetVariable`/`SetVariable`;
- corresponds to the new default-enabled `AMD Variable Protection` setup item at `AmdPbsSetupDxe` offset `0x91`.

`GenerateTimeBaseVariable.efi` is a 692-KiB EFI application, not a DXE driver. It contains the same variable name/GUID and prints `mCreatePayload` / `mDeletePayload` C arrays after building authenticated-variable payloads. It is strongly identified as the companion payload-generation utility for `AmdVariableProtection`, not an automatically dispatched boot component.

Focused 1.12 searches found no equivalent AMD protection layer, while generic VariablePolicy/VarCheck infrastructure was already present.

The immediate generic provider `NvramDxe` is the same size in both versions and differs by only 28 bytes; inspected differences reduce to PCD-token renumbering plus build date/time. No VariablePolicy/VarCheck semantic change was found. The new AMD component is therefore a new **consumer on top of an effectively unchanged policy engine**.

#### `HardwareSignatureEntry`

`HardwareSignatureEntry.efi` is a separate new AMI DXE feature. Direct strings/GUIDs and public AMI source with the same module name and exact FFS GUID identify it as HardwareChange / ACPI FACS hardware-signature management: it records hardware configuration data and updates the hardware signature around the boot transition.

1.12 lacks both its HardwareChange protocol GUID and `HardwareConfigData` variable string, so the functionality appears genuinely newly integrated by 1.15.

No immediate dependency connects `HardwareSignatureEntry` to the AMD Variable Protection cluster.

#### ECAM/MMCONFIG

A real platform-wide PCI MMCONFIG/ECAM relocation remains established:

```text
1.12: 0xF0000000
1.15: 0xE0000000
```

It occurs in at least `AmdNbioIOMMUDxe` and `PciRootBridge`. The first PI pass found no immediate dependency tying this relocation to the three newly added modules, so it remains a **separate platform-init delta**.

#### CVE-2024-36311 mapping boundary

A second bounded pass attempted to use CVE-2024-36311 as an implementation fingerprint before touching DRFXI SMM binaries.

Direct public evidence establishes only:

- TOCTOU (`CWE-367`);
- an SMM communications buffer as the affected object class;
- high-privilege local attacker model;
- out-of-bounds read/write impact;
- Dragon Range mitigation level `DragonRangeFL1PI 1.0.0.3h`.

The authoritative AMD/CVE record does **not** publish a communication GUID, handler GUID, module name, function, source path, communication structure name beyond the generic description, exact race shape, or patch. Focused GitHub/public searches found mirrors of the advisory but no researcher write-up, PoC or implementation fingerprint.

Generic EDK2 components such as `PiSmmCommunication`, `PiSmmCore`, and `SmmMemLib` demonstrate the relevant class of communication-buffer validation code, but there is no public evidence tying CVE-2024-36311 specifically to those implementations. Therefore the CVE branch is intentionally paused rather than expanded into a generic SMM diff.

Resume this path only with a concrete handler/module/GUID/patch fingerprint, a strong cross-platform pre/post mitigation comparison, or recovered 1.13 plus independent narrowing evidence.

See `checkpoints/2026-09-11-pi-1.0.0.3h-first-pass.md`, `checkpoints/2026-09-11-pi-1.0.0.3h-cve-2024-36311.md`, and `findings/changelog-mapping.md`.

### 1.13 Intel LAN OPROM POST-logo fix

**Paused.**

The probable Intel Option ROM belongs to an external/add-in NIC rather than the onboard Realtek path. The generic firmware chain has been followed through PCI ROM parsing/policy, EFI decompression, LoadImage/Security2/PE-COFF/StartImage, protocol installation/notification, DriverBinding/ConnectController, plus the Legacy/CSM alternative. No relevant 1.12→1.15 semantic delta was found in those generic paths.

Public BD790i context makes **Intel X710-DA2 / `I40eUndiDxe`** the strongest board-specific candidate found, but the exact problem NIC/PCI ID remains unknown. Source-guided I40e analysis narrowed actual firmware dependencies to PciIo config/MMIO/DMA and Device Path; those implementations were also negative except for the separate platform-wide ECAM relocation above.

Do not resume generic firmware reverse engineering for this branch. The next justified artifact is the exact problem NIC/ROM, or an X710-DA2 Option ROM as a surrogate.

See `findings/intel-lan-oprom.md` and `checkpoints/2026-09-11-intel-lan-oprom-source-dependencies-closure.md`.

### 1.15 TCC / SMU power changes

`Set TCC to 100` is localized end-to-end:

```text
PcdPeim default 91 -> 100
    ↓
SmuV13Dxe PcdGet32
    ↓
BIOSSMC_MSG_SetTjMax
```

Three inserted Dynamic BOOLEAN tokens explain the local-token shift. `AodPei` may override the default when manual thermal-throttle settings are used. Confidence is very high.

Separately, `PSP_SMU_FN_FIRMWARE~0x108` is materially replaced between 1.12 and 1.15 (`0.54.68.0 → 0.54.6C.32`). Content normalization shows significant layout movement, so internal attribution for `Update SMU for power limit` remains intentionally deferred until a reusable Xtensa-le reverse-engineering environment is justified.

See `findings/tcc-pcd-consumer.md`, `findings/smu-power-limit.md`, and `deferred/smu-power-limit-deep-dive.md`.

### Community 795iX3D modification

- The image is overwhelmingly based on stock 1.12.
- 398/399 parsed FFS files in the main UEFI volume are byte-identical to stock 1.12.
- The only intentional UEFI change is `AMITSESetupData` (`FE612B72-203C-47B1-8560-A66D946EB371`).
- After inner decompression, exactly 60 bytes differ; each sets bit `0x04`, consistent with a bulk AMIBCP access/visibility change.
- The full image also contains donor-board NVRAM/APOB/APCB/boot/security state and should be treated as a reference SPI readback, not a clean portable flash image.

### 1.17 dGPU / iGPU behavior

- New executable logic is localized to `OemDxe.efi`.
- It scans PCIe for a display-class device, accesses `AmdSetupRPL` offset `0x44` (`iGPU Configuration`), and changes/reset behavior according to dGPU presence.
- This matches the 1.17 graphics changelog with high confidence.

### DMI

Raw SMBIOS/DMI data shows real 1.12→1.15 string changes including manufacturer/product updates. The base-board manufacturer change directly corresponds to 1.14; neighboring DMI changes cannot be separated between 1.14 and 1.15 without intermediate binaries.

### 1.16 flash-driver candidate

Between 1.15 and 1.17, `ReFlash.efi`, `FlashDriver.efi`, and `FlashDriverSmm.efi` change materially. This remains strongly attributable to `Add AMI flash driver EIP`, though missing 1.16 prevents exact temporal proof.

### 1.16 S3 workaround candidate

1.17 adds `AmdCpmOemAcpi.efi`; its S3 dependency and new SSDTs implement PCIe PME/power/resume behavior including `CpmSendPmeTurnOff → CpmWakeLink → DL_ACTIVE`. This is a strong candidate for the 1.16 S3 workaround, but the branch is intentionally paused pending 1.16 or runtime evidence.

### Undocumented 1.17 functionality

1.17 introduces `TcgStorageSecurity.efi`, `SmmTcgStorageSec.efi`, a new dynamic setup VarStore and TCG Storage Security forms. No known 1.16/1.17 changelog item explicitly names this functionality.

## Methodological findings

Raw module counts substantially overstate semantic change. Comparisons must distinguish:

1. build/relocation noise;
2. PCD-token renumbering;
3. global platform-constant changes;
4. real data changes;
5. real executable-logic changes.

Examples now include:

- TCC: `209→212` token renumbering with stable consumer semantics around a real `91→100` default change;
- Intel LAN: large BDS growth separated into unrelated GOP code plus unchanged network path;
- PI first pass: `NvramDxe` hashes differ, but only 28 bytes change and normalize to PCD/build metadata while the real behavior change is a newly added consumer module.

## Active open questions

Highest-value unresolved work outside paused branches:

1. recover official 1.13 / 1.14 / 1.16 binaries to resolve temporal attribution;
2. classify remaining normalized PE/FFS changes only when driven by a concrete changelog or unexplained released feature;
3. derive a clean, version-aware unlock strategy for hidden memory controls and Save/Restore User Defaults without transplanting donor-board state.

## Deferred / paused branches

- PI 1.0.0.3h / CVE-2024-36311: wait for a concrete implementation fingerprint, strong cross-platform pre/post mitigation evidence, or recovered 1.13 plus independent narrowing evidence.
- Intel LAN OPROM: wait for exact NIC/ROM or X710-DA2 ROM surrogate.
- `Update SMU for power limit` internals: wait for justified reusable Xtensa-le tooling.
- S3 / PCIe power-resume: wait for DRFXI 1.16 or useful runtime evidence.

## Rule for future updates

Update this file when conclusions change. Preserve historical dated checkpoints rather than rewriting them after later evidence changes the interpretation.

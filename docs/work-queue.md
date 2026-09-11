# Research work queue

Last updated: 2026-09-11

This file records which branches are active, complete enough to stop, or intentionally deferred. Topic details remain in `docs/findings/`; immutable snapshots remain in `docs/checkpoints/`.

## Ready for next bounded investigation

### DRFXI 1.13 `Update PI 1.0.0.3h` — CVE-directed SMM validation pass

The first bounded PI pass is complete.

Confirmed from the 1.12→1.15 boundary:

- `AmdVariableProtection.efi` is a genuinely new AMD VariablePolicy/VarCheck consumer protecting AMD setup variables;
- `GenerateTimeBaseVariable.efi` is its companion EFI application for generating authenticated create/delete payloads for the same `AmdVariableProtection` variable;
- `HardwareSignatureEntry.efi` is a separate AMI HardwareChange/FACS hardware-signature feature, not part of the AMD variable-protection dependency cluster;
- the immediate generic VariablePolicy/VarCheck provider `NvramDxe` has only PCD-token/build-time differences and no relevant semantic delta;
- PCI MMCONFIG/ECAM `0xF0000000→0xE0000000` remains a separate platform-init delta rather than part of the three-module cluster.

External AMD documentation now identifies the changelog version precisely as **DragonRangeFL1PI 1.0.0.3h** for Ryzen 7045/Dragon Range. AMD lists that PI revision as the mitigation level for **CVE-2024-36311**, an SMM communications-buffer TOCTOU validation issue, with a 2025-03-18 release date.

This does not prove that the three new modules or the ECAM relocation landed specifically in 1.0.0.3h.

Recommended next task: use the public CVE/PI mapping to derive a **small candidate set of SMM communication components/GUIDs first**, then compare only those validation paths 1.12→1.15. Do not scan all changed SMM modules. Stop if the vulnerable component cannot be mapped narrowly from public AMD/EDK2 evidence.

See `docs/checkpoints/2026-09-11-pi-1.0.0.3h-first-pass.md` and `docs/findings/changelog-mapping.md`.

## Completed enough to stop

### PI 1.0.0.3h — first new-module triage

The three newly named PE modules are classified and do not form a single functional cluster. The first immediate dependency edge is normalized. Do not repeat broad triage of those three modules; continue only through a new evidence-backed dependency such as the CVE-directed SMM path above.

### `Set TCC to 100`

Static consumer path is closed:

```text
PcdPeim default 91 -> 100
    ↓
SmuV13Dxe PcdGet32
    ↓
BIOSSMC_MSG_SetTjMax
```

Further work is optional only: source-level PCD CName or runtime effective-limit validation.

See `docs/findings/tcc-pcd-consumer.md`.

## Deferred / paused deep dives

### Intel LAN OPROM POST-hang fix

**Paused on 2026-09-11.**

The generic firmware-side path has been followed far enough that further broad reverse engineering has low expected value. The exact Intel NIC / PCI Device ID behind the MINISFORUM changelog is still unknown. Public BD790i evidence makes **Intel X710-DA2 / `I40eUndiDxe`** the strongest board-specific candidate found so far, but it is not proven to be the original reproducer.

The next justified development of this branch is external-artifact-driven: obtain the **actual X710-DA2 Option ROM** (or, preferably, the exact original problem NIC/ROM if it can be identified), then trace its real entrypoint / DriverBinding / hardware-init dependencies against 1.12→1.15. Do not resume generic PciBus/BDS/LoadImage/Security2/CSM/protocol-notify analysis without such an artifact.

See `docs/findings/intel-lan-oprom.md` and `docs/checkpoints/2026-09-11-intel-lan-oprom-source-dependencies-closure.md`.

### `Update SMU for power limit`

Paused. The replacement of `PSP_SMU_FN_FIRMWARE~0x108` is established, and raw-diff normalization shows extensive layout movement, but internal handler/table attribution now requires a reusable Ghidra/Xtensa-le reverse-engineering environment.

Do not resume with more raw byte diffing.

See `docs/deferred/smu-power-limit-deep-dive.md` and `docs/checkpoints/2026-09-10-smu-power-internal-intermediate.md`.

### S3 / PCIe power-resume

Paused after the AML/ACPICA investigation. Resume primarily when DRFXI 1.16 is recovered or when runtime ACPI evidence becomes useful.

See `docs/findings/s3-workaround.md`.

## Other valuable future branches

- recover missing official firmware 1.13 / 1.14 / 1.16;
- classify remaining normalized PE/FFS changes as changelog-explained, likely-related, or undocumented;
- derive a clean, version-aware unlock for hidden memory controls and AMI Save/Restore User Defaults without transplanting donor-board state.

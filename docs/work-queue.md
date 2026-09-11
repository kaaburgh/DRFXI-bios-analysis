# Research work queue

Last updated: 2026-09-11

This file records which branches are active, complete enough to stop, or intentionally deferred. Topic details remain in `docs/findings/`; immutable snapshots remain in `docs/checkpoints/`.

## Ready for next bounded investigation

### DRFXI 1.13 `Update PI 1.0.0.3h` — isolate concrete PI/platform deltas

Known changelog item from DRFXI 1.13:

```text
Update PI 1.0.0.3h
```

Because 1.13 and 1.14 binaries are missing, the available boundary is **1.12→1.15** and temporal attribution must remain explicit.

Existing evidence already shows that raw module churn badly overstates semantic change: 181 named PE modules differ bytewise across 1.12→1.15, but many inspected differences reduce to PCD-token renumbering, relocation/build noise, or global platform constants. Three named PE modules are genuinely added by 1.15:

- `AmdVariableProtection.efi`
- `GenerateTimeBaseVariable.efi`
- `HardwareSignatureEntry.efi`

A real platform-wide PCI MMCONFIG/ECAM relocation `0xF0000000 -> 0xE0000000` has also been observed in `AmdNbioIOMMUDxe` and `PciRootBridge` while investigating the Intel-LAN branch. It is not Intel-specific and is at least as plausibly part of the PI/platform update.

Recommended next task: do a **bounded normalized PI-component triage**, not a general firmware diff. Start from the three added modules and the MMCONFIG relocation, identify their immediate protocol/variable/DEPEX dependencies and nearby changed providers/consumers, and determine which deltas form a coherent PI/platform-update cluster versus unrelated 1.14/1.15 work. Stop after the first evidence-backed cluster is localized.

Use `docs/findings/changelog-mapping.md`, `data/module-diff-summary.csv`, `data/pcd-db-1.12-to-1.15-diff.json`, and the current research status as the handoff.

## Completed enough to stop

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

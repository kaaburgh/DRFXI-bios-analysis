# Research work queue

Last updated: 2026-09-10

This file records which branches are active, complete enough to stop, or intentionally deferred. Topic details remain in `docs/findings/`; immutable snapshots remain in `docs/checkpoints/`.

## Ready for next bounded investigation

### Intel LAN OPROM POST-hang fix

Known changelog item from DRFXI 1.13:

```text
Fix hang at POST logo caused by Intel LAN OPROM
```

Current negative evidence from 1.12→1.15:

- `LanRomDriver.efi` — byte-identical;
- `UefiPxeBcDxe.efi` — byte-identical;
- `SnpDxe.efi` — byte-identical;
- `NetworkStackSetupScreen.efi` — byte-identical;
- `RomLayoutDxe.efi` — byte-identical;
- `OptionRomPolicy.efi` changes only minimally and looks consistent with PCD-token renumbering;
- `PciBus.efi` likewise does not expose an obvious LAN-specific fix.

`Bds.efi` remains the strongest unresolved executable candidate: it grows materially from 1.12 to 1.15 and has substantial real code differences.

Because 1.13 and 1.14 binaries are missing, any 1.12→1.15 finding must distinguish direct code evidence from temporal attribution to 1.13.

Recommended next task: bounded, BDS/LAN-only semantic diff, first identifying Option ROM dispatch / POST-logo / network-ROM paths and then comparing only those functions.

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

## Deferred deep dives

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

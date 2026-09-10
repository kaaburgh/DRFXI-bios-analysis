# Research work queue

Last updated: 2026-09-10

This file records which branches are active, complete enough to stop, or intentionally deferred. Topic details remain in `docs/findings/`; immutable snapshots remain in `docs/checkpoints/`.

## Ready for next bounded investigation

### Intel LAN OPROM POST-hang fix — isolate the physical ROM

Known changelog item from DRFXI 1.13:

```text
Fix hang at POST logo caused by Intel LAN OPROM
```

The first focused BDS/dispatch pass is complete. Current evidence from 1.12→1.15:

- `LanRomDriver`, `UefiPxeBcDxe`, `SnpDxe`, `NetworkStackSetupScreen`, and `RomLayoutDxe` are byte-identical;
- `OptionRomPolicy` differs only by 11 `+3` PCD-token renumberings;
- `PciBus` differs only by two accesses to one renumbered token (`0x3D0→0x3D4`);
- the explicit BDS Network Controller (`PCI base class 0x02`) path is semantically unchanged;
- a major new BDS block was localized to display/GOP/device-path management (`class 0x03`, `AmiGopOutputDp`), so BDS growth itself is no longer evidence for the LAN fix;
- no new direct Intel vendor-ID `0x8086` branch was found.

The actual Intel LAN PCI Option-ROM payload has not yet been isolated. A top-level `PCIR` scan is insufficient because it may be compressed or AMI-encapsulated.

Recommended next task: identify the exact FFS/raw/compressed object that carries the Intel LAN Option ROM in 1.12 and 1.15, compare it, and trace only the dispatch route for that exact object. Resume BDS comparison only if the ROM payload proves unchanged.

See `docs/findings/intel-lan-oprom.md` and `docs/checkpoints/2026-09-10-intel-lan-oprom-bds.md`.

Because 1.13 and 1.14 binaries are missing, any 1.12→1.15 finding must continue to distinguish direct code evidence from temporal attribution to 1.13.

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

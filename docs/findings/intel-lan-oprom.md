# Intel LAN OPROM POST-hang investigation

Last updated: 2026-09-10

Relevant 1.13 changelog item:

```text
Fixup hang Post logo by intel lan OPROM
```

## Negative result

The obvious network/Option-ROM payload candidates do not show a meaningful replacement between 1.12 and 1.15.

Observed byte-identical modules include:

```text
LanRomDriver.efi
UefiPxeBcDxe.efi
SnpDxe.efi
NetworkStackSetupScreen.efi
RomLayoutDxe.efi
```

`OptionRomPolicy` and `PciBus` show only tiny immediate-value differences consistent with PCD-token renumbering rather than a new algorithm.

## Strongest remaining candidate

`Bds.efi` changes substantially:

```text
1.12: 76,928 bytes
1.15: 100,096 bytes
```

This makes BDS / device-enumeration / Option-ROM dispatch policy a stronger candidate than an updated Intel LAN ROM payload itself.

## Current conclusion

The changelog wording should not currently be interpreted as "Intel LAN OPROM binary was updated." Evidence instead suggests that the workaround may live in boot/dispatch policy surrounding when or how that Option ROM executes.

This remains unresolved until `Bds.efi` and related PCI/Option-ROM dispatch paths are normalized and compared semantically.

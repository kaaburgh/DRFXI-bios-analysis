# Flash-driver and TCG Storage changes by 1.17

Last updated: 2026-09-10

## Flash-driver path

Between official DRFXI 1.15 and 1.17, the following modules change materially:

```text
ReFlash.efi
FlashDriver.efi
FlashDriverSmm.efi
```

`ReFlash.efi` shrinks from roughly 59 KiB to 44 KiB, and its IFR/UI surface changes substantially.

Removed or reduced paths include several older user controls around:

- partial image update;
- boot-block update;
- Reset NVRAM;
- explicit confirmation/proceed flows.

The completion text also changes from a manual "press any key to reboot" flow to automatic reboot wording.

## Changelog attribution

The immediately preceding 1.16 changelog includes:

```text
Add AMI flash driver EIP
```

The coordinated real changes in `ReFlash`, `FlashDriver`, and `FlashDriverSmm` are therefore strongly attributable to that item.

This is not marked fully proven because the 1.16 binary itself is unavailable: a 1.15→1.17 comparison cannot formally separate changes introduced in 1.16 from additional 1.17 work.

## TCG Storage Security addition

1.17 also adds functionality not named in the known 1.16/1.17 changelog:

```text
TcgStorageSecurity.efi
SmmTcgStorageSec.efi
```

Setup gains a new VarStore associated with:

```text
TcgStorageDynamicSetupVar
GUID 2798F49D-F760-480B-8055-916940C27740
Size 0x4A
```

and two forms named approximately:

```text
TCG Storage device Security Configuration
```

Strings/code include concepts such as `ProgrammaticResetEnable` and `LockOnReset`.

## Current classification

- Flash-driver changes: **strongly attributable** to 1.16 `Add AMI flash driver EIP`.
- TCG Storage Security: **confirmed released functionality with undocumented provenance** in the currently known changelog.

A larger AMI platform/EIP update could explain both, but that relationship has not yet been demonstrated.

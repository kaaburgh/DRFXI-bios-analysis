# Intel LAN OPROM POST-hang investigation

Last updated: 2026-09-10

Relevant 1.13 changelog item:

```text
Fixup hang Post logo by intel lan OPROM
```

The 1.13 and 1.14 binaries are still missing, so the binary comparison available here is 1.12→1.15. Any implementation observed only across that interval cannot be assigned temporally to 1.13 without additional evidence.

## Current summary

The original hypothesis that `Bds.efi` was the strongest candidate simply because it grows substantially is now downgraded.

A focused comparison establishes that the obvious network/Option-ROM support modules are unchanged, `OptionRomPolicy` and `PciBus` contain only token-renumbering noise, and the explicit BDS Network Controller path is semantically unchanged. A large newly inserted BDS block was instead localized to display/GOP/device-path management.

The 1.13 fix therefore remains unresolved. The highest-value next target is the actual physical Intel LAN PCI Option-ROM object and the dispatch route for that exact object.

## Byte-identical network / ROM-support modules

The following PE images are exactly identical between 1.12 and 1.15:

```text
LanRomDriver
size   169952
SHA256 6e2dd29f159edf01187fb6b518dbafa388c2c0512f4beeb1c25d2f5613b4ea75

UefiPxeBcDxe
size   64960
SHA256 c185ecfe9a643a82e9c8728f7ceb1a002112c5b14763983ea0218ed235cab6fd

SnpDxe
size   22048
SHA256 48fc6790588d499e37cc0e3a6c50f6532efcf84fc7fff0a784757f1a990b7d0e

NetworkStackSetupScreen
size   1152
SHA256 d2e5bfb2ca4700746134adc18fd627398cf7a22dba2eb23c4cbb873fc92b6c60

RomLayoutDxe
size   4448
SHA256 76a7a922a009b6b93d305c995ff33498fa720d572937a90117f96bfb70bed41c
```

This excludes an ordinary PE-code update in these modules. It does **not** yet prove that every compressed/raw Intel LAN Option-ROM payload elsewhere in the firmware is unchanged.

## `OptionRomPolicy`: semantic negative result

PE size remains 36,384 bytes.

```text
1.12 SHA256 cca026848f370a6caf46e29e897f6cf8c855bdd5a89028ebab82f11c39503587
1.15 SHA256 cdb0b6239d8d53cdc49f4d22658634fb8177355f9de37d7b2a2dc246edfbe5b7
```

Exactly 11 bytes differ. Every change is a PCD token immediate moving by `+3`, for example `0x2B0→0x2B3`, `0x377→0x37A`, etc. Surrounding calls and control flow are unchanged.

The module's Option-ROM policy strings are unchanged, including:

```text
Network Class
Disable OPROM
UEFI OPROM
Legacy OPROM
Network Device behind the bridge.
Controls the execution of UEFI and Legacy Network OpROM
```

No semantic 1.13 workaround is visible here.

## `PciBus`: semantic negative result

PE size remains 73,344 bytes.

```text
1.12 SHA256 7f320fe70d95a3d8bf7c99de142740fb0659d790049edaee01b18103f3b60363
1.15 SHA256 d656f21414256a5aa2524f8773318e9d381bb5cb706f58d160e12ab968f231a3
```

Only two bytes differ, at two accesses to the same renumbered token:

```text
0x3D0 -> 0x3D4
```

The following indirect call remains the same. No changed PCI/Option-ROM control flow was found.

## `Bds.efi`: real growth, but major new code is graphics/GOP

BDS FFS GUID:

```text
8F4B8F82-9B91-4028-86E6-F4DB7D4C1DFF
```

```text
1.12
size   76928
SHA256 184493a59bf9db882ad12550b1efb1f49aa81792d8479b01646a2ba7bccb649c

1.15
size   100096
SHA256 fe579a1b0c9e856bc6c600ba31aa98f88d2772aeae2d87d70f68ee87e2f2de99
```

Section growth:

```text
.text  0xEF30  -> 0x13340  (+0x4410)
.data  0x2410  -> 0x3350   (+0x0F40)
```

Content-anchor matching shows that much of the old BDS code survives byte-identically at shifted addresses. Representative displacement plateaus include about `+0x08A0`, `+0x3F20`, `+0x4340`, and finally `+0x4410`. This is inserted/enlarged code/data rather than a wholesale BDS rewrite.

A conspicuous new 1.15 path was localized. It:

- reads the AMI `Setup` variable;
- enumerates `EFI_PCI_IO_PROTOCOL` handles;
- reads PCI config base class at offset `0x0B`;
- explicitly checks class `0x03` (Display Controller);
- resolves device paths and PCI locations;
- references `PciRoot(0x0)/Pci(0x8,0x1)`;
- manages the UEFI variable `AmiGopOutputDp`;
- invokes `ConnectController` for matched display-class paths.

Representative new class checks occur around RVA `0xC1FC` and `0xC44D`.

This is strong firmware-internal evidence that a major part of the BDS growth is GOP/display-output management, not the Intel LAN OPROM fix. BDS growth by itself is therefore no longer evidence for the 1.13 workaround.

## Explicit BDS Network Controller path is unchanged

An existing BDS routine around RVA `0x29FC–0x2DD1` reads PCI base class and explicitly checks Network Controller class `0x02` at the same locations in both releases:

```asm
0x2A95: cmp byte ptr [rbp+0x20],0x02
...
0x2D31: cmp byte ptr [rbp+0x20],0x02
```

After normalizing RIP-relative references and helper functions displaced by the new BDS blocks, the only differences in this routine are helper target addresses:

```text
old 0x7AD8 -> new 0xB9F8
old 0x7734 -> new 0xB654
old 0x76B8 -> new 0xB5D8
```

No branch, class test, policy condition, or operation changes in this identifiable network path.

This is a strong negative result: the direct BDS Network Controller handling examined here did not receive the workaround.

## No direct Intel vendor-ID special case found

A focused literal search found no newly introduced comparison against PCI vendor ID `0x8086` in the changed candidates.

One apparent new `86 80` occurrence in BDS was disassembled and is part of a RIP-relative displacement, not a vendor-ID comparison. `OptionRomPolicy` has no new occurrence, while `PciBus` has the same occurrences in both versions.

This rules out the simplest implementation pattern (`VendorId == 0x8086`) in the inspected code, but does not exclude identification by BDF, class/subclass, device path, protocol, ROM metadata, or another table.

## Physical Intel LAN Option-ROM payload is still missing

A top-level scan for an uncompressed `PCIR` header did not identify a plain PCI ROM image. This is **not** proof that the LAN OPROM is absent: it may be compressed or AMI-encapsulated in another FFS/raw object.

Consequently, the byte-identical `LanRomDriver` PE should not be conflated with proof that the actual Intel LAN Option-ROM payload is unchanged.

This is now the main unresolved artifact.

## Assessment

**Confirmed:**

- the obvious network PE modules are unchanged;
- `OptionRomPolicy` and `PciBus` changes normalize entirely to PCD-token renumbering;
- the explicit BDS Network Controller path is semantically unchanged;
- a major new BDS block is display/GOP code, not LAN;
- no new direct Intel `0x8086` special case was found.

**Medium-confidence remaining hypothesis:** the workaround may still be a subtle generic BDS connect/dispatch/order/POST-logo change outside the direct class-0x02 path.

**Open alternative:** the actual compressed/raw Intel LAN Option-ROM payload may itself have changed, but that object has not yet been isolated.

## Next bounded step

Identify the **physical Intel LAN PCI Option-ROM object and its dispatch route** rather than continuing broad BDS reverse engineering.

1. Inspect FFS/raw/compressed sections and AMI ROM-layout metadata in 1.12 and 1.15 for the object carrying the Intel LAN Option ROM.
2. Identify it using PCI ROM/PCIR metadata, Intel vendor/device IDs, decompressed payload characteristics, or ROM-layout mapping.
3. Compare that exact object between releases.
4. Determine which `PciBus`/AMI/BDS path dispatches that exact ROM.
5. Only if the ROM is unchanged, compare the smallest dispatch gate for its exact handle/BDF to decide whether the workaround is a skip/order/connection change.

Checkpoint: `docs/checkpoints/2026-09-10-intel-lan-oprom-bds.md`.
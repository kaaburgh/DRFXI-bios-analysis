# DRFXI 1.13 Intel LAN OPROM — closed-chain checkpoint

Date: 2026-09-11

Scope: only the changelog item:

```text
Fixup hang Post logo by intel lan OPROM
```

Binary comparison boundary: **DRFXI 1.12 → 1.15**. Versions 1.13 and 1.14 remain unavailable, so temporal attribution to 1.13 is not yet possible from binary evidence alone.

## Executive checkpoint

The generic firmware-controlled path for an external Intel LAN EFI Option ROM has now been traced far enough that the obvious dispatch mechanisms are closed by negative evidence.

No relevant semantic 1.12→1.15 delta was found in:

```text
external PCI ROM
  → AA55 / PCIR parser
  → AMI Option-ROM policy
  → EFI CodeType 3 selection
  → optional EFI decompression
  → Relative Offset Range device path
  → LoadImage
  → Security2
  → PE/COFF load
  → StartImage
  → external ROM entrypoint
  → protocol database insertion
  → synchronous protocol notification
  → generic Driver Binding / ConnectController infrastructure
```

The obvious Legacy/CSM route is also unlikely: this `PciBus` only dispatches `PCIR CodeType == 3`, and no static `EFI_LEGACY_BIOS_PROTOCOL` provider was found after full UEFI decompression.

The first major unknown executable is therefore the **external Intel NIC Option ROM itself** and the firmware state/dependencies it consumes after entry.

## Input firmware

```text
1.12 DRFXI.BIN
SHA256 246e7f54a12a8c7279ef68433602264b8ecbabcde828c9c9008f571c270845b9

1.15 DRFXI.BIN
SHA256 3afaba6d916b3897d1d98bd5913008b38e89b6c51b2c6963c7109793541d8d88
```

## Physical ROM / onboard-LAN conclusion

A full decompression/extraction pass found no embedded Intel LAN PCIR Option ROM. The only valid embedded PCIR candidate isolated was AMD graphics (`1002:164e`).

`LanRomDriver` identifies as Realtek UEFI UNDI, with Realtek strings and `0x10ec` / `0x8125` evidence. The working interpretation is therefore that the changelog's Intel LAN OPROM most likely belongs to an **add-in Intel PCIe NIC**.

Confidence: medium-high, because the exact original NIC model is still unknown.

## Module-level negatives

Byte-identical or semantically unchanged relevant modules/paths include:

- `LanRomDriver`
- `UefiPxeBcDxe`
- `SnpDxe`
- `NetworkStackSetupScreen`
- `RomLayoutDxe`
- broader nearby UEFI network stack (IP/DHCP/UDP/TCP/VLAN/ARP modules inspected)
- `OptionRomPolicy` after PCD-token normalization
- `PciBus` after PCD-token normalization
- `AmiBoardInfo2` inspected policy path
- `PciDxeInit` consumer of the same Option-ROM policy

`OptionRomPolicy` superficial differences are PCD-token renumbering. No semantic change was found in the actual callbacks reached from `PciBus`.

## BDS negative results

`Bds.efi` grows substantially in 1.15, but a conspicuous newly inserted path was localized to display/GOP handling:

- PCI base class `0x03`;
- `AmiGopOutputDp`;
- display device-path matching;
- two new `ConnectController` sites belonging to that path.

The identifiable BDS Network Controller path (`PCI base class 0x02`) is semantically unchanged. Its immediate `EfiBootManagerPolicyProtocol.ConnectDeviceClass(Network)` predecessor is also unchanged after normalization.

All old BDS `ConnectController` sites have semantic counterparts in 1.15. No new LAN-specific connect path was found.

No new direct Intel PCI vendor-ID (`0x8086`) conditional was found in the inspected candidates.

## External PCI Option-ROM parser and policy gate

The relevant `PciBus` path:

1. obtains PCI-device ROM buffer/size;
2. validates `0xAA55`;
3. follows `+0x18` to `PCIR`;
4. validates the structure;
5. invokes AMI Option-ROM policy;
6. executes EFI images with `PCIR CodeType == 3`.

Relevant regions:

```text
policy gate       ~0x9b70..0x9bf6
parser/dispatcher ~0x9bf8..0x9f17
```

These regions are byte-identical 1.12→1.15.

The corresponding `AmiOpromPolicyProtocol` / `AmiCsmOpromPolicyProtocol` provider callbacks in `OptionRomPolicy` are unchanged.

## EFI post-policy path

After policy acceptance, `PciBus`:

- accepts EFI subsystem 11/12;
- supports compression type 0/1;
- builds a Relative Offset Range media device-path node;
- appends it to the PCI device path;
- calls `LoadImage` with a non-NULL `SourceBuffer`;
- then calls `StartImage` on success.

The path is byte-identical.

### DxeCore normalized comparisons

```text
CoreLoadImageCommon       0x897c..0x8dc0   293 instructions, 0 normalized differences
LoadImage                 0x8dc0..0x8eb8    70 instructions, 0 differences
StartImage                0x8eb8..0x9104   137 instructions, 0 differences
PE/COFF load region       0x112d0..0x11840 366 instructions, 0 differences
ConnectController         0x5e94..0x66a4   579 instructions, 0 differences
```

`EFI_DECOMPRESS_PROTOCOL` relevant functions are exact matches.

`LoadFile` / `LoadFile2` are not used on this path because `PciBus` supplies a non-NULL source buffer.

### Security2

`EFI_SECURITY2_ARCH_PROTOCOL.FileAuthentication()` is provided by `SecurityStubDxe`. Relevant callbacks and immediate helpers are byte-identical; remaining differences reduce to unrelated PCD/build noise.

Thus no firmware-side semantic change was found before `StartImage` transfers control to the external Option-ROM entrypoint.

## Legacy/CSM route

`PciBus` contains an explicit:

```asm
cmp byte ptr [PCIR+0x14], 0x03
```

Only EFI CodeType 3 reaches its loader. CodeType 0 is not dispatched by this path.

A full scan for `EFI_LEGACY_BIOS_PROTOCOL` found consumers/presence checks but no static provider:

- BDS uses `GetBbsInfo`, not `CheckPciRom` / `InstallPciRom`;
- `OptionRomPolicy` reacts to protocol appearance but does not provide it;
- other references are consumers/checks;
- no clear protocol installation site or normal AMI CSMCORE provider was found.

The Legacy/CSM workaround hypothesis is therefore low-confidence.

## Protocol-install / notify route after external entry

A remaining possibility was that the Intel EFI driver installs a protocol and firmware synchronously runs a changed notify callback before returning.

DxeCore does support such synchronous behavior, but the machinery is semantically unchanged:

```text
0x4e7c..0x5070  protocol-entry helpers             147/147 equal
0x5070..0x5290  InstallProtocolInterface            147/147
0x5290..0x54ec  InstallMultipleProtocolInterfaces   173/173
0x54ec..0x5704  UninstallProtocolInterface          154/154
0x9760..0x9854  RegisterProtocolNotify               65/65
0x9854..0x9a7c  ReinstallProtocolInterface          144/144
0x9a7c..0x9e58  CreateEvent/SignalEvent/...         258/258
0xd394..0xd55c  RaiseTPL/RestoreTPL/notify          117/117
```

No direct firmware `RegisterProtocolNotify` was found for the most obvious external LAN-driver protocols:

- `EFI_DRIVER_BINDING_PROTOCOL`
- `EFI_SIMPLE_NETWORK_PROTOCOL`
- `EFI_NETWORK_INTERFACE_IDENTIFIER_PROTOCOL`
- `EFI_PXE_BASE_CODE_PROTOCOL`

The direct network notifications that were found concern other protocols and reside in byte-identical network modules.

Therefore a changed synchronous AMI notify callback is not supported by current evidence.

## Closed generic chain

The following mechanisms should not be re-investigated without new concrete evidence:

```text
PciBus AA55/PCIR parser
AMI Option-ROM policy
BDS class-0x02 network path
BDS generic ConnectController sites
EFI decompression
LoadImage / LoadFile / LoadFile2
Security2
PE/COFF loader
StartImage
Legacy CheckPciRom / InstallPciRom path
DxeCore protocol insertion
RegisterProtocolNotify / SignalEvent / RestoreTPL dispatch
generic ConnectController / Driver Binding infrastructure
```

All were either shown not to participate or shown to have no relevant semantic 1.12→1.15 delta.

## Current hypotheses

### A. External ROM sees changed firmware state and avoids the hanging branch

Confidence: **medium**.

The Intel ROM may consume protocols, UEFI variables, PCI configuration/attributes, controller protocols, device paths, or platform-specific services. A change in one such input could change the ROM's behavior while all generic loader infrastructure remains identical.

### B. Exact NIC / ROM family is now the key missing artifact

Confidence: **medium-high as a research constraint**.

The original Intel NIC model, PCI Device ID, and Option-ROM family are still unknown. Without them, further generic firmware enumeration is increasingly speculative.

### C. Hidden Legacy/CSM provider/path

Confidence: **low**.

Possible in principle, but unsupported by the firmware extraction and code paths found so far.

## Not proven

- exact Intel NIC / PCI Device ID;
- EFI-only vs combined ROM layout;
- actual Intel Option-ROM binary/source family;
- whether the hang occurred inside entrypoint, `DriverBinding.Supported`, `DriverBinding.Start`, or a later driver callback;
- which firmware dependency consumed by the ROM changed 1.12→1.15;
- exact attribution of any future 1.12→1.15 candidate to 1.13 rather than 1.14/1.15.

## Next narrow step

Stop generic firmware reverse engineering.

Identify the Intel NIC / Option-ROM family implicated by the changelog, ideally obtaining a representative matching EFI LAN Option ROM. Then derive from that image only its real external dependencies:

- `LocateProtocol` / `OpenProtocol` targets;
- UEFI variables;
- PCI I/O reads/writes/attributes;
- device-path assumptions;
- Boot Services calls;
- platform-specific protocol consumers.

Only those dependency producers/state should then be compared across DRFXI 1.12→1.15.

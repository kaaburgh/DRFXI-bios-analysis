# Intel LAN OPROM POST-hang investigation

Last updated: 2026-09-11

Relevant 1.13 changelog item:

```text
Fixup hang Post logo by intel lan OPROM
```

The 1.13 and 1.14 binaries are still missing, so the available binary boundary is **DRFXI 1.12 → 1.15**. Any implementation difference found across that interval can only be treated as a candidate for the 1.13 fix unless the behavior itself identifies the change.

Firmware inputs used for the focused comparison:

```text
1.12 DRFXI.BIN
SHA256 246e7f54a12a8c7279ef68433602264b8ecbabcde828c9c9008f571c270845b9

1.15 DRFXI.BIN
SHA256 3afaba6d916b3897d1d98bd5913008b38e89b6c51b2c6963c7109793541d8d88
```

## Current summary

The firmware-controlled dispatch chain that would normally carry an external Intel LAN EFI Option ROM from PCI discovery to execution has now been followed and compared end-to-end far enough to close the obvious generic paths.

No relevant semantic 1.12→1.15 delta has been found in:

```text
external PCI ROM
  → AA55 / PCIR parsing
  → AMI Option-ROM policy
  → optional EFI decompression
  → Relative Offset Range device path
  → LoadImage
  → Security2 authentication
  → PE/COFF loading
  → StartImage
  → external ROM entrypoint
  → generic protocol installation / notification machinery
  → generic Driver Binding / ConnectController infrastructure
```

The Legacy/CSM alternative has also become unlikely: this `PciBus` implementation dispatches only `PCIR CodeType == 3` EFI images, does not dispatch `CodeType == 0` legacy images, and no static provider of `EFI_LEGACY_BIOS_PROTOCOL` was found after full firmware decompression.

The strongest current interpretation is therefore:

1. the changelog's "Intel LAN OPROM" most likely belongs to an **external/add-in Intel PCIe NIC**, not the onboard LAN implementation in `DRFXI.BIN`;
2. the generic firmware paths that discover, admit, load, start, and service that EFI Option ROM are semantically unchanged across 1.12→1.15;
3. the first important unknown executable is the **Intel Option ROM itself** and the firmware state/protocols/variables/PCI attributes that it consumes after entry.

The fix remains unresolved, but the search space is now much smaller and several initially plausible mechanisms are closed by negative evidence.

## 1. The onboard LAN path is Realtek, not Intel

A full UEFI extraction/decompression pass did not find an embedded Intel LAN PCIR Option ROM in either firmware image. The only valid embedded PCIR candidate isolated during the scan was AMD graphics (`1002:164e`).

`LanRomDriver` is not Intel code. Its strings and literal IDs identify it as Realtek UEFI UNDI code, including:

```text
Realtek Ethernet Controller
Realtek UEFI UNDI Driver
RtkUndiDxe
RtUefiEDK2
```

The image contains repeated `0x10ec` and `0x8125` literals and no corresponding new Intel `0x8086` special case. This is consistent with the board's onboard wired LAN being Realtek.

This shifts the working model from "the firmware contains an Intel LAN ROM blob" to "the problematic Intel LAN Option ROM is supplied by an add-in Intel NIC".

Confidence: **medium-high**, because the exact NIC/model from the original bug report is still unknown.

## 2. Byte-identical network / ROM-support modules

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

The broader nearby UEFI network stack was also checked and found byte-identical, including the relevant IP/DHCP/UDP/TCP/VLAN/ARP modules. This strongly excludes an ordinary LAN/PXE/SNP stack update as the workaround.

## 3. `OptionRomPolicy`: semantic negative result

PE size remains 36,384 bytes.

```text
1.12 SHA256 cca026848f370a6caf46e29e897f6cf8c855bdd5a89028ebab82f11c39503587
1.15 SHA256 cdb0b6239d8d53cdc49f4d22658634fb8177355f9de37d7b2a2dc246edfbe5b7
```

Exactly 11 bytes differ. Every difference is a PCD token immediate moving by `+3`; surrounding calls and control flow are unchanged.

The module's relevant strings are also unchanged:

```text
Network Class
Disable OPROM
UEFI OPROM
Legacy OPROM
Network Device behind the bridge.
Controls the execution of UEFI and Legacy Network OpROM
```

The specific callbacks/readers/wrappers reached from the PCI Option-ROM policy path were later compared directly and are byte-identical as executable code.

`AmiBoardInfo2`, another plausible board/slot-policy dependency, similarly showed only PCD-token renumbering noise in the inspected path.

Conclusion: no semantic implementation change for the workaround was found in the ordinary AMI Option-ROM policy layer.

## 4. `PciBus`: external-ROM parser and policy gate are unchanged

PE size remains 73,344 bytes.

```text
1.12 SHA256 7f320fe70d95a3d8bf7c99de142740fb0659d790049edaee01b18103f3b60363
1.15 SHA256 d656f21414256a5aa2524f8773318e9d381bb5cb706f58d160e12ab968f231a3
```

The superficial binary delta is only two accesses to one renumbered PCD token (`0x3D0 → 0x3D4`).

More importantly, the actual external PCI ROM path was localized and compared. It:

1. obtains the device ROM buffer/size from the PCI device context;
2. validates `0xAA55`;
3. follows the pointer at `+0x18` to `PCIR`;
4. validates the `PCIR` structure;
5. calls AMI Option-ROM policy;
6. processes EFI images when `PCIR CodeType == 3`.

Relevant regions:

```text
policy gate       ~RVA 0x9b70..0x9bf6
parser/dispatcher ~RVA 0x9bf8..0x9f17
```

Both are byte-identical 1.12→1.15.

### AMI policy protocol route

The path uses:

```text
AmiOpromPolicyProtocolGuid
542D6248-4198-4960-9F59-2384646D63B4

AmiCsmOpromPolicyProtocolGuid
DC14E697-775A-4C3B-A11A-EDC38E1BE3E6
```

The provider callbacks actually reached in `OptionRomPolicy` are unchanged. A second consumer in `PciDxeInit` was also compared and is byte-identical.

This closes the simple explanation that 1.13 changed the admission policy and merely stopped starting the problematic Intel ROM.

## 5. `Bds.efi`: growth is real, but the prominent new code is graphics/GOP

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

Content-anchor matching shows that much old code survives byte-identically at shifted addresses. A conspicuous new 1.15 block was localized to display/GOP management. It:

- reads the AMI `Setup` variable;
- enumerates `EFI_PCI_IO_PROTOCOL` handles;
- reads PCI base class at offset `0x0B`;
- explicitly checks class `0x03` (Display Controller);
- resolves device paths and PCI locations;
- references `PciRoot(0x0)/Pci(0x8,0x1)`;
- manages `AmiGopOutputDp`;
- invokes `ConnectController` for matched display-class paths.

Representative class checks occur around `0xC1FC` and `0xC44D`.

Therefore the large BDS growth cannot be used as evidence for the LAN fix.

## 6. Explicit BDS Network Controller path and its immediate predecessor are unchanged

The identifiable BDS network routine around `0x29FC–0x2DD1` reads PCI base class and checks class `0x02` in both versions:

```asm
0x2A95: cmp byte ptr [rbp+0x20],0x02
...
0x2D31: cmp byte ptr [rbp+0x20],0x02
```

After normalizing shifted helper targets, no branch, class test, policy condition, or operation changes.

The immediate `EfiBootManagerPolicyProtocol.ConnectDeviceClass()` predecessor around `0x2afc` was also compared. Its Network-class branch and call into the same network routine are semantically unchanged.

All old BDS `ConnectController` call sites found in 1.12 have semantic counterparts in 1.15. The two genuinely new `ConnectController` calls in 1.15 belong to the class-`0x03` GOP path described above.

Conclusion: no direct BDS network/connect/reachability workaround was found.

## 7. No direct Intel vendor-ID special case found

A focused search found no newly introduced comparison against PCI vendor ID `0x8086` in the changed candidates.

An apparent new `86 80` byte sequence in BDS disassembles as part of a RIP-relative displacement, not a vendor comparison. `OptionRomPolicy` has no new Intel literal, while `PciBus` has the same occurrences in both releases.

This rules out the simplest implementation pattern:

```c
if (VendorId == 0x8086) {
    skip_or_special_case_option_rom();
}
```

It does not exclude indirect identification through BDF, device path, class/subclass, ROM metadata, protocol presence, or state.

## 8. Post-policy EFI Option-ROM dispatch path is closed by negative evidence

After the AMI policy gate allows an EFI image, `PciBus`:

- accepts EFI subsystem 11/12;
- supports compression type 0/1;
- builds a Media Device Path **Relative Offset Range** node (`04 08 18 00`);
- records the image offsets within the PCI ROM;
- appends that node to the PCI device path;
- calls `gBS->LoadImage()` with a **non-NULL `SourceBuffer`** pointing to the ROM image or decompressed buffer;
- on success calls `gBS->StartImage()`.

This `PciBus` region is byte-identical.

### Decompression

Compressed EFI images use `EFI_DECOMPRESS_PROTOCOL`, provided by `DxeCore` in this firmware. The relevant `GetInfo`, `Decompress`, and backend functions were compared and are exact matches.

### `LoadImage` / PE-COFF / `StartImage`

The following DxeCore regions were normalized and compared:

```text
CoreLoadImageCommon       0x897c..0x8dc0   293 instructions, 0 normalized differences
LoadImage                 0x8dc0..0x8eb8    70 instructions, 0 differences
StartImage                0x8eb8..0x9104   137 instructions, 0 differences
PE/COFF load region       0x112d0..0x11840 366 instructions, 0 differences
ConnectController         0x5e94..0x66a4   579 instructions, 0 differences
```

`LoadFile` / `LoadFile2` are not used for this path because `PciBus` passes a non-NULL `SourceBuffer`.

### Security2 boundary

`DxeCore` invokes `EFI_SECURITY2_ARCH_PROTOCOL.FileAuthentication()` before the image is loaded. The provider is `SecurityStubDxe`.

The relevant Security/Security2 callbacks and immediate helpers are byte-identical. Remaining differences reduce to PCD/build noise; a TCG-related path was intentionally kept out of scope.

### Boundary into the external ROM

`DxeCore::StartImage` eventually calls the loaded image entrypoint. At that point execution leaves the firmware image under analysis and enters the external Intel NIC Option ROM.

So the direct EFI path is now closed as:

```text
PCIR EFI image
  → policy
  → optional decompression
  → Relative Offset Range device path
  → LoadImage
  → Security2
  → PE/COFF loader
  → StartImage
  → external Intel ROM entrypoint
```

No relevant firmware-side semantic change was found before the external entrypoint.

## 9. Legacy/CSM path is unlikely in these builds

The `PciBus` parser explicitly checks:

```asm
cmp byte ptr [PCIR+0x14], 0x03
```

Only `CodeType == 3` reaches the EFI loader. `CodeType == 0` legacy x86 images are not dispatched by this `PciBus` path; they are skipped while the PCIR image chain is advanced or terminated.

A full decompressed-image scan for standard `EFI_LEGACY_BIOS_PROTOCOL` usage found consumers/presence checks but no static provider in either release.

Relevant findings:

- BDS locates the protocol and calls method `+0x30`, corresponding to `GetBbsInfo`, not `CheckPciRom` or `InstallPciRom`;
- AMITSE and another consumer use other methods/presence checks;
- `OptionRomPolicy` registers for protocol appearance but does not provide it;
- no clear `InstallProtocolInterface` / `InstallMultipleProtocolInterfaces` site installs this protocol;
- a typical AMI CSMCORE image/provider was not found.

A hidden/proprietary/dynamically constructed provider cannot be ruled out absolutely by static analysis, but there is no positive evidence for an active Legacy Option-ROM execution route here.

Conclusion: the hypothesis that the Intel LAN hang was fixed in `CheckPciRom` / `InstallPciRom` / CSM execution is now low-confidence.

## 10. Protocol installation and synchronous notification path is also unchanged

A remaining hypothesis was that the external Intel EFI driver enters through `StartImage`, installs protocols, and triggers an AMI firmware callback synchronously before returning.

This is architecturally possible and was verified in DxeCore: protocol installation signals registered notify events, and pending notify functions may execute as TPL is restored.

The corresponding DxeCore machinery was normalized and compared:

```text
0x4e7c..0x5070  protocol-entry helpers             147/147 instructions equal
0x5070..0x5290  InstallProtocolInterface            147/147
0x5290..0x54ec  InstallMultipleProtocolInterfaces   173/173
0x54ec..0x5704  UninstallProtocolInterface          154/154
0x9760..0x9854  RegisterProtocolNotify               65/65
0x9854..0x9a7c  ReinstallProtocolInterface          144/144
0x9a7c..0x9e58  CreateEvent/SignalEvent/...         258/258
0xd394..0xd55c  RaiseTPL/RestoreTPL/notify          117/117
```

All apparent raw changes normalize to shifted data references; executable semantics are unchanged.

A focused static search also did not find direct firmware notify registration for the most obvious protocols an Intel LAN EFI driver would install/use:

- `EFI_DRIVER_BINDING_PROTOCOL`
- `EFI_SIMPLE_NETWORK_PROTOCOL`
- `EFI_NETWORK_INTERFACE_IDENTIFIER_PROTOCOL`
- `EFI_PXE_BASE_CODE_PROTOCOL`

The direct network-stack notifications that were found concern other protocols such as IPsec/DHCP and live in byte-identical network modules.

Conclusion: there is no evidence that the 1.13 workaround is a changed synchronous firmware callback triggered by ordinary network-driver protocol installation.

## Closed-chain assessment

The following generic firmware-controlled mechanisms have now been investigated and do **not** show the relevant semantic delta:

```text
external add-in PCI ROM discovery
  → AA55 / PCIR parsing
  → Option-ROM policy admission
  → EFI image selection (CodeType 3)
  → optional decompression
  → image/device-path construction
  → LoadImage
  → Security2
  → PE/COFF loading
  → StartImage
  → generic protocol database insertion
  → synchronous RegisterProtocolNotify event delivery
  → generic Driver Binding / ConnectController infrastructure
```

The obvious Legacy/CSM alternate route is also unsupported by the examined firmware.

This is the main result of the investigation so far: **the generic dispatch chain is substantially closed by negative evidence**.

## Current hypotheses

### A. The external Intel Option ROM takes a different branch because some firmware state changed

**Confidence: medium.**

The same Intel ROM can behave differently even if the loader and generic protocol infrastructure are identical. During its entrypoint or `DriverBinding.Supported/Start`, it may consume:

- firmware protocols;
- UEFI variables;
- PCI config/attributes;
- controller protocols;
- device paths;
- Boot Services state;
- platform-specific services.

A 1.12→1.15 change in one of those inputs could keep the external ROM out of the old hanging path without any visible delta in the generic loader.

### B. The exact Intel NIC / Option-ROM family matters and has not yet been identified

**Confidence: medium-high as a research constraint.**

The exact NIC model, PCI Device ID, and ROM binary/source family are still unknown. Without them, continuing to enumerate unrelated firmware services becomes increasingly speculative.

### C. A hidden Legacy/CSM route exists despite the static negative evidence

**Confidence: low.**

Possible in principle, but no provider or dispatch path has been found and `PciBus` itself only executes EFI CodeType 3.

### D. The fix is in the already-examined generic loader/policy/BDS/network path

**Confidence: low.**

The relevant code is either byte-identical or semantically identical after normalization.

## What is still not proven

- the exact Intel NIC model / PCI Device ID involved in the original report;
- whether its Option ROM was EFI-only or a combined ROM;
- the Option ROM binary/source family;
- which protocols/variables/PCI state that ROM actually consumes;
- whether the hang occurred inside its EFI entrypoint, `DriverBinding.Supported`, `DriverBinding.Start`, or a later callback;
- which specific 1.12→1.15 state change corresponds to the workaround;
- whether any future candidate belongs to 1.13 specifically rather than 1.14/1.15.

## Next bounded step

Do **not** continue broad reverse engineering of BDS, generic PCI init, CSM, `LoadImage`/`StartImage`, Security2, or generic protocol-notify machinery.

The next useful step is to identify the **actual Intel NIC / Option-ROM family** implicated by the changelog or obtain a representative matching Intel EFI LAN Option ROM.

Then statically derive only its real dependencies:

```text
entrypoint
DriverBinding.Supported
DriverBinding.Start
  → LocateProtocol / OpenProtocol
  → GetVariable
  → PCI_IO reads/writes / attributes
  → device-path operations
  → Boot Services calls
  → platform-specific protocol consumers
```

Only the producers/state of those concrete dependencies should then be compared across DRFXI 1.12→1.15.

Historical checkpoint: `docs/checkpoints/2026-09-10-intel-lan-oprom-bds.md`.
Latest closed-chain checkpoint: `docs/checkpoints/2026-09-11-intel-lan-oprom-closed-chain.md`.

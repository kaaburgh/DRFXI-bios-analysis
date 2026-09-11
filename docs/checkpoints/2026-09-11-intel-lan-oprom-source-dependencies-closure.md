# DRFXI 1.13 Intel LAN OPROM — source-guided dependency checkpoint

Date: 2026-09-11

Scope: only `Fixup hang Post logo by intel lan OPROM`, with DRFXI 1.12→1.15 as the available binary boundary.

This checkpoint starts after the generic external-OPROM dispatch/load/notify paths were already closed negative. It uses Intel's published/open PREBOOT UNDI source families as surrogates for the external NIC ROM in order to ask which firmware state the ROM actually consumes.

## Exact reproducer remains unknown

No public report naming the exact Intel NIC / PCI Device ID behind the MINISFORUM changelog was found.

Public BD790i evidence does show that **Intel X710-DA2** is a realistic add-in card for this board: a 2024 homelab discussion proposes the BD790i specifically with X710-DA2 for OPNsense, and another published BD790i system description uses X710-DA2. This is context, not proof of the changelog reproducer.

Candidate ranking:

1. X710 / XL710 / XXV710 (`I40eUndiDxe`) — low-to-medium confidence; strongest board-specific candidate.
2. I210 / I350 / 8257x/8258x (`GigUndiDxe`) — low.
3. X520 / X540 / X550 / 82599 (`XGigUndiDxe`) — low.
4. E810 (`IceUndiDxe`) — low.

Intel's current Boot Utility confirms that these adapter families can carry UEFI drivers / Intel Boot Agent in programmable PCI option-ROM flash.

## Source family

Pinned public source surrogate:

`Eric6666/IntelUndiPkg@0624fc4c9c6d4f1b54b73703b41f0fe46bf86036`

Its README states that the sources were extracted from Intel PREBOOT `APPS\\EFI\\OPENSRC`. Relevant families are `GigUndiDxe`, `XGigUndiDxe`, `I40eUndiDxe`, and `IceUndiDxe`.

For X710-class devices, `I40eUndiDxe/Brand.c` contains X710 entries under Intel vendor `0x8086`, including X710 device ID `0x1572` variants.

## Real I40e dependencies

### DriverBinding.Supported

`I40eUndiDriverSupported()` consumes:

- controller `EFI_PCI_IO_PROTOCOL` via `OpenProtocol(... BY_DRIVER)`;
- `PciIo->Pci.Read()` of PCI config header;
- VendorId/DeviceId matching (`0x8086` + supported Intel device ID);
- RemainingDevicePath;
- ordinary `CloseProtocol()` cleanup.

There is no motherboard-vendor protocol or UEFI variable dependency in this path.

### DriverBinding.Start

Relevant path:

```text
Open EFI_PCI_IO_PROTOCOL + EFI_DEVICE_PATH_PROTOCOL
  -> I40ePciInit
  -> I40eFirstTimeInit
  -> controller protocol setup
  -> if child requested and NIC firmware supported:
       InitUndiStructures
       I40eInitHw
       install child protocols
       OpenProtocol(PciIo, BY_CHILD_CONTROLLER)
```

Concrete firmware-facing dependencies are therefore:

- PciIo config, attributes and MMIO;
- PciIo DMA allocation/map/unmap;
- controller/base Device Path + RemainingDevicePath;
- Boot Services allocation/event/protocol operations;
- optional HII Database/String services later in Start.

No normal `GetVariable`/`SetVariable` dependency was found in the source-guided entry/Supported/Start path.

### DMA shape

I40e uses PciIo `AllocateBuffer`, `FreeBuffer`, `Map`, and `Unmap`, including `EfiPciIoOperationBusMasterCommonBuffer`. The other mainstream Intel UNDI source families have the same broad PCI/DMA shape, so this dependency remains relevant even if X710 is not the original reproducer.

## Firmware comparison of those dependencies

### PciIo implementation

`PciBus.efi` was already normalized as semantically unchanged apart from PCD-token renumbering. No change to the direct PciIo implementation that would explain Intel-specific behavior is supported.

### IOMMU backend

`EDKII_IOMMU_PROTOCOL` (`4E939DE9-D948-4B0F-88ED-E6E1CE517C1E`) is provided by `AmdNbioIOMMUDxe`.

Located protocol table in both 1.12 and 1.15:

```text
Revision       0x00010000
SetAttribute   RVA 0x5424
Map            RVA 0x5490
Unmap          RVA 0x5614
AllocateBuffer RVA 0x56f4
FreeBuffer     RVA 0x5780
```

These protocol methods and their directly used mapping/translation helpers are semantically unchanged.

**Negative result:** no 1.12→1.15 change to DMA Map/Unmap semantics was found.

### Real underlying state delta: MMCONFIG / ECAM relocation

`AmdNbioIOMMUDxe` does contain a genuine repeated constant change:

```text
1.12: PCI MMCONFIG base 0xF0000000
1.15: PCI MMCONFIG base 0xE0000000
```

Representative occurrences are around RVAs `0x1d54`, `0x26ed..0x27e9`, `0x5157`, `0x57c1/0x57cc`, and `0x595b/0x5964`. Code around the `0x5157` occurrence accesses PCI configuration offsets while constructing IOMMU-side state.

`PciRootBridge` contains the same platform-wide `F0000000 -> E0000000` relocation.

Assessment:

- this is a real semantic/state delta on a path that plausible Intel UNDI drivers ultimately depend on;
- it could change the PCI/IOMMU state seen by a NIC driver even though PciIo and IOMMU service methods themselves are unchanged;
- it is **not Intel-specific**;
- because DRFXI 1.13 separately says `Update PI 1.0.0.3h`, the MMCONFIG relocation is at least as plausibly a PI/platform-init change as the specific LAN workaround.

Confidence that this is *the* LAN fix: **low**.

### Device Path producer

The external NIC controller path produced by `PciBus` has no known semantic code delta because `PciBus` itself was already closed negative.

The relevant root-bridge ACPI Device Path construction was checked narrowly in `PciRootBridge`: the code around the `PNP0A03` ACPI root node (`mov 0x0A0341D0`, around RVA `0xF75`) and its surrounding construction region are byte-identical between 1.12 and 1.15.

No static evidence for a changed controller/root Device Path supplied to Intel DriverBinding was found.

### HII Database / String

The optional I40e HII path uses `EFI_HII_DATABASE_PROTOCOL` and `EFI_HII_STRING_PROTOCOL` after controller initialization.

Both GUIDs reside in the same extracted `HiiDatabase` PE, and that PE is **byte-identical**:

```text
size   99,360 bytes
SHA256 33bb4eecf07342b69b35960f4b1ec8517f4fa96e56c2f847f54b557d43061216
```

Thus HII services do not provide the 1.12→1.15 workaround.

## Checkpoint

### Confirmed

- Exact original Intel NIC is not identified from public evidence.
- X710-DA2 is a realistic BD790i add-in NIC and the strongest board-specific candidate found, but not proven to be the reproducer.
- Intel PREBOOT source families provide a concrete source surrogate for dependencies.
- X710/I40e DriverBinding primarily consumes PciIo config/attributes/MMIO/DMA and controller Device Path, not AMI-specific protocols or UEFI variables.
- Direct PciIo implementation is unchanged.
- `AmdNbioIOMMUDxe` IOMMU Map/Unmap/Allocate/Free methods are unchanged.
- Device Path construction checked on the relevant root path is unchanged.
- HII Database/String provider is byte-identical.
- A real platform-wide PCI MMCONFIG/ECAM relocation `F0000000 -> E0000000` exists in both IOMMU/root-bridge code.

### Best remaining firmware-side candidate from actual ROM dependencies

The MMCONFIG relocation is the only concrete 1.12→1.15 state delta found on an actual dependency of plausible Intel UNDI families. It has a plausible indirect mechanism through PCI/IOMMU state, but attribution to the LAN-specific changelog item is **low confidence** because it is platform-wide and overlaps the separate PI update.

### Not proven

- exact NIC / Device ID / ROM binary;
- whether the hang occurred in entrypoint, Supported, Start, NIC firmware handshake, DMA initialization or another internal Intel-driver loop;
- whether MMCONFIG relocation has any causal connection to the LAN hang;
- whether a different state producer changed only in 1.13, because 1.13/1.14 binaries are unavailable.

## Next narrow step

Further generic firmware reverse engineering now has low expected value.

Highest-value next evidence is **the actual reproducer artifact**:

1. identify the exact Intel NIC / PCI IDs from a MINISFORUM support report or reproduction;
2. obtain/read that card's actual option-ROM image/version;
3. map its concrete entrypoint/Supported/Start implementation against the Intel source family;
4. if hardware is available, reproduce on 1.12 vs 1.15 and capture where execution stops (before Start, during NIC firmware initialization, or during DMA/hardware init).

Without this artifact, the MMCONFIG relocation should remain a recorded candidate rather than be promoted to a conclusion.

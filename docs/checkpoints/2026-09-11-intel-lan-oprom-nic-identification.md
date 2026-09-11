# Intel LAN OPROM — NIC / ROM family identification log

Date: 2026-09-11

Scope: only DRFXI 1.13 changelog item `Fixup hang Post logo by intel lan OPROM`.

This is an in-process research log. Generic firmware dispatch paths already closed in `docs/findings/intel-lan-oprom.md` are not being reopened.

## Starting state

Established before this pass:

- The likely Intel LAN OPROM is on an external/add-in PCIe NIC, not the onboard Realtek RTL8125 path.
- EFI ROM parsing/admission, decompression, LoadImage/StartImage, Security2/PE-COFF, generic ConnectController, Legacy/CSM, and synchronous protocol-notify infrastructure have no relevant 1.12→1.15 semantic delta.
- The nearby UEFI network stack is byte-identical.

## External evidence collected so far

### Direct evidence for the exact original MINISFORUM bug

No public bug report naming the exact NIC / PCI Device ID has yet been found. Searches for the exact changelog wording and close variants did not produce an original report.

This is an important evidence boundary: the candidate ranking below is contextual inference, not attribution of the actual MINISFORUM reproducer.

### BD790i + Intel add-in NIC evidence

A Feb 2024 /r/homelab post and mirrored OPNsense discussion specifically discuss using an **Intel X710-DA2** in the BD790i PCIe x16 slot for OPNsense. A separate published Spark-cluster description later documents a BD790i master node actually equipped with an Intel X710-DA2. These are direct evidence that X710-class Intel NICs are realistic BD790i add-in devices, but **not evidence that X710 caused the 1.13 POST-logo bug**.

A later BD795i discussion mentions an **Intel 82575EB** NIC on BIOS 1.12, again showing old Intel server NICs are plausible in this board family, but not tying the device to the 1.13 POST-logo hang.

Current candidate ranking from public context only:

1. X710 / XL710 / XXV710 (`I40eUndiDxe` family): plausible, **low-to-medium confidence**; strongest board-specific public candidate so far.
2. I210 / I350 / older 8257x/8258x Gigabit (`GigUndiDxe` family): plausible, **low confidence**.
3. X520 / X540 / X550 / 82599 (`XGigUndiDxe` family): plausible, **low confidence**.
4. E810 (`IceUndiDxe`): possible but less likely for the original BD790i-era user scenario, **low confidence**.

### Intel ROM/source-family evidence

Intel's Ethernet Connections Boot Utility contains UEFI drivers / Intel Boot Agent images used to program PCI option-ROM flash on supported Intel adapters. Intel's supported product list spans I210/I350, X520/X550, X710/XL710/XXV710 and newer families.

A public GitHub import (`Eric6666/IntelUndiPkg`, commit `0624fc4c9c6d4f1b54b73703b41f0fe46bf86036`) states that its source trees were extracted from Intel PREBOOT `APPS\\EFI\\OPENSRC` packages. It contains four relevant open-source UEFI UNDI families:

- `GigUndiDxe`
- `XGigUndiDxe`
- `I40eUndiDxe`
- `IceUndiDxe`

This gives us source-family surrogates for static dependency analysis without guessing generic UEFI behavior.

## I40e / X710-family concrete dependency extraction

Because X710-DA2 is the strongest board-specific candidate found so far, `I40eUndiDxe` was inspected first.

### DriverBinding.Supported

`I40eUndiDriverSupported()` does **not** depend on a vendor-specific motherboard protocol or UEFI variable. Its relevant firmware-facing inputs are:

1. `EFI_PCI_IO_PROTOCOL`, opened on the controller with `EFI_OPEN_PROTOCOL_BY_DRIVER`;
2. PCI configuration space read through `PciIo->Pci.Read()` from offset 0 for a `PCI_CONFIG_HEADER`;
3. Intel vendor/device matching through `IsDeviceIdSupported()`;
4. the Remaining Device Path passed by the firmware;
5. normal `CloseProtocol()` cleanup when probing a not-yet-owned controller.

The source comments explicitly describe the supported controller as a network-class PCI device with Intel vendor ID `0x8086` and a supported adapter Device ID.

If the controller had already been partially initialized because the NIC's own firmware was considered unsupported, Supported returns `EFI_ALREADY_STARTED` to prevent another DriverBinding Start call. That state is internal to the Intel UNDI driver/NIC firmware interaction, not an AMI-specific callback.

### DriverBinding.Start

The controller-start path is:

```text
Open EFI_PCI_IO_PROTOCOL + EFI_DEVICE_PATH_PROTOCOL
  -> I40ePciInit
  -> I40eFirstTimeInit
  -> InitControllerProtocols
  -> [when child requested and NIC firmware supported]
       InitUndiStructures
       I40eInitHw
       install child protocols
       open PciIo BY_CHILD_CONTROLLER
```

Concrete firmware-facing dependencies before/while hardware initialization therefore include:

- `EFI_PCI_IO_PROTOCOL`;
- `EFI_DEVICE_PATH_PROTOCOL` on the PCI controller;
- Boot Services allocation/event/protocol operations;
- the Remaining Device Path / base controller Device Path;
- PCI config/attributes and MMIO exposed through `EFI_PCI_IO_PROTOCOL`;
- DMA services exposed through that same PciIo protocol.

No `GetVariable()` / `SetVariable()` dependency was found in the I40e entry/Supported/Start path. Repository-wide searches did not identify normal runtime-variable access in this driver family; runtime-service usage found was debug-time `GetTime` support.

### PciIo operations concretely consumed by I40e

The I40e sources use the following PciIo capabilities in the initialization/runtime support code:

- `Pci.Read` for PCI configuration / VendorId / DeviceId;
- `Attributes(Get)` to save original PCI attributes;
- `Attributes(Supported)` to obtain supported command attributes;
- setting the required PCI decode/bus-master attributes during PCI init;
- MMIO access through PciIo memory operations for NIC registers;
- `AllocateBuffer` / `FreeBuffer`;
- `Map` / `Unmap` with `EfiPciIoOperationBusMasterCommonBuffer` and bus-master read operations for DMA;
- controller/child ownership via `OpenProtocol` with BY_DRIVER and BY_CHILD_CONTROLLER.

`I40eUndiDxe/Dma.c` directly demonstrates the DMA dependency: it allocates common buffers through PciIo, maps them as bus-master common buffers, checks that the whole requested area was mapped, and unmaps/frees them later.

### Produced protocols (not pre-existing firmware inputs)

After initialization, the Intel driver installs standard child/controller protocols such as:

- NII pointer;
- `EFI_NETWORK_INTERFACE_IDENTIFIER_PROTOCOL` 3.1;
- child `EFI_DEVICE_PATH_PROTOCOL` with a MAC-address node appended;
- Driver Stop / Adapter Information / HII-related protocols.

These are outputs of the Intel driver. The generic synchronous protocol-notify machinery and direct firmware notifications for DriverBinding/SNP/NII/PXE were already checked and are not a 1.12→1.15 delta.

### HII dependencies

The optional HII setup path locates `EFI_HII_DATABASE_PROTOCOL` and `EFI_HII_STRING_PROTOCOL`. This happens after controller initialization and only on the first PF partition in the inspected source. It is therefore lower priority than PCI/DMA/device-path state for a POST-logo hang during controller start, but it remains a concrete dependency if earlier candidates close negative.

## Concrete DMA/IOMMU backend comparison

The I40e DMA dependency was followed into the firmware instead of reopening generic PCI analysis.

EDK2's standard `EDKII_IOMMU_PROTOCOL` GUID is:

```text
4E939DE9-D948-4B0F-88ED-E6E1CE517C1E
```

and its interface provides `SetAttribute`, `Map`, `Unmap`, `AllocateBuffer`, and `FreeBuffer`. Standard EDK2 PciBus implementations may delegate PciIo DMA operations through this protocol.

A full decompressed-image GUID scan of DRFXI 1.12 and 1.15 found the same relevant modules referencing the IOMMU GUID, including `AmdNbioIOMMUDxe`, `PciBus`, `PciRootBridge`, `Bds`, and `NvmeSmm`.

### Provider: `AmdNbioIOMMUDxe`

`AmdNbioIOMMUDxe` installs the IOMMU protocol. The located protocol vtable is unchanged between 1.12 and 1.15:

```text
Revision       0x00010000
SetAttribute   RVA 0x5424
Map            RVA 0x5490
Unmap          RVA 0x5614
AllocateBuffer RVA 0x56f4
FreeBuffer     RVA 0x5780
```

The relevant protocol methods and their immediate DMA-translation helpers were disassembled and compared. **No semantic code change was found in SetAttribute/Map/Unmap/AllocateBuffer/FreeBuffer or their directly used translation helpers.**

This is a strong negative result for the simple mechanism "1.13 fixed Intel UNDI by changing DMA Map/Unmap semantics".

### Real state delta underneath the unchanged methods: PCI MMCONFIG / ECAM base

`AmdNbioIOMMUDxe` is not byte-identical. Most byte differences are PCD-token renumbering, but one genuine platform-state change recurs consistently:

```text
PCI MMCONFIG / ECAM base
1.12: 0xF0000000
1.15: 0xE0000000
```

Representative changed constants occur around RVAs `0x1d54`, `0x26ed..0x27e9`, `0x5157`, `0x57c1/0x57cc`, and `0x595b/0x5964`. The function around the `0x5157` delta uses the MMCONFIG base while reading PCI configuration offsets such as `0x44/0x48` and constructing internal IOMMU state before publishing/using the IOMMU service.

The same `F0000000 -> E0000000` platform change is visible in `PciRootBridge`, which strongly indicates a **system-wide PCI MMCONFIG relocation**, not an Intel-NIC special case.

Interpretation:

- **Confirmed semantic/state delta:** the platform PCI ECAM window changed between 1.12 and 1.15.
- **Confirmed negative:** the IOMMU DMA service API implementation consumed by a plausible Intel UNDI driver did not change semantically.
- **Possible mechanism:** corrected/different ECAM state can alter what IOMMU/root-bridge initialization sees and therefore indirectly alter DMA/controller state presented to an external Intel UNDI driver.
- **Attribution confidence to the LAN fix: low.** The matching root-bridge-wide change and the 1.13 changelog's separate `Update PI 1.0.0.3h` entry make this at least as plausibly a platform-init update as the specific Intel-LAN workaround.

This delta should therefore be preserved as a concrete candidate dependency/state change, but **not promoted to the Intel LAN fix without a reproducer, exact 1.13 binary, or additional causal evidence**.

## Cross-family implication

The source-family search shows that `GigUndiDxe`, `XGigUndiDxe`, `I40eUndiDxe`, and `IceUndiDxe` all use the same broad PCI/DMA shape: `EFI_PCI_IO_PROTOCOL`, PCI attributes/config, and PciIo DMA allocation/mapping. Therefore the IOMMU/MMCONFIG dependency is not unique to X710; it remains relevant even if the original card belonged to another mainstream Intel server-NIC UNDI family.

That weakens its value for identifying the exact card but strengthens it as the one concrete firmware state boundary shared by plausible Intel OPROM families.

## Current narrowing

The source-guided investigation has now produced one real 1.12→1.15 state delta on a dependency the Intel ROM actually consumes, but not a convincing LAN-specific implementation delta.

Current priority order:

1. `EFI_PCI_IO_PROTOCOL` direct implementation: already essentially negative because `PciBus` code is semantic-identical.
2. DMA/IOMMU service methods: **negative**; identical relevant provider methods.
3. underlying PCI/IOMMU initialization state: **MMCONFIG F0000000→E0000000**, real delta, low confidence as LAN-fix attribution.
4. controller Device Path / RemainingDevicePath state: still to close narrowly.
5. HII Database/String: lower priority because reached after hardware initialization in I40e Start.

## Next action in this pass

Check only the two remaining concrete dependencies without reopening generic PCI initialization:

1. determine whether the actual controller Device Path producer code changed; because `PciBus` is already semantic-identical, distinguish code change from merely runtime topology/BDF state;
2. hash/compare the HII Database/String provider(s) used by Intel UNDI setup code, only to close this lower-priority dependency.

Then checkpoint. If both are negative, the next highest-value external artifact is the exact Intel NIC/ROM or reproduction hardware; further generic firmware RE would have sharply diminishing evidence value.

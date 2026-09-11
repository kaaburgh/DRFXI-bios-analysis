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

## Current narrowing

The I40e source changes the firmware-side question substantially. For an X710-family reproducer, the most relevant motherboard-controlled inputs after the already-closed generic dispatch chain are not arbitrary network-stack protocols. They are primarily:

1. **the PciIo-visible controller state**: PCI attributes/config/MMIO and DMA mapping behavior;
2. **the controller Device Path / Remaining Device Path** passed to DriverBinding;
3. secondarily HII protocols used later in Start.

Because the `PciBus.efi` executable itself was previously shown to have no semantic code delta except PCD token renumbering, a changed PciIo method implementation is not currently supported. The remaining concrete possibility is a changed **state/provider underneath those same methods** — especially DMA/IOMMU-visible state or controller/device-path state — rather than a new Intel-specific dispatch branch.

## Next action in this pass

Check only the providers/state implied by the concrete I40e dependencies:

1. determine whether the PciIo DMA Map/Unmap path delegates to an IOMMU protocol/provider on this firmware, and if so compare that provider 1.12→1.15;
2. check whether the controller Device Path producer/state relevant to an add-in network card changed without reopening broad BDS/PCI initialization;
3. inspect HII Database/String providers only if the higher-priority PCI/DMA state is negative.

Do not reopen PciBus policy, LoadImage/StartImage, Security2, CSM, BDS, generic protocol notify or the byte-identical network stack.

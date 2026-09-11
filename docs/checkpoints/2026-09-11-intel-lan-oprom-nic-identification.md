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

### BD790i + Intel add-in NIC evidence

A Feb 2024 /r/homelab post specifically discusses using an **Intel X710-DA2** in the BD790i PCIe x16 slot for OPNsense. This is direct evidence that X710-class Intel NICs are a realistic BD790i use case, but it is **not evidence that this card caused the changelog bug**.

A later BD795i discussion mentions an **Intel 82575EB** NIC on BIOS 1.12, again showing old Intel server NICs are plausible in this board family, but not tying the device to the 1.13 POST-logo hang.

Current candidate ranking from public context only:

1. X710 / XL710 / XXV710 (`i40e` UEFI UNDI family): plausible, **low-to-medium confidence**.
2. I210 / I350 / older 8257x/8258x Gigabit (`GigUndi` family): plausible, **low confidence**.
3. X520 / X540 / X550 / 82599 (`XGigUndi` family): plausible, **low confidence**.
4. E810 (`IceUndi`): possible but less likely for the original BD790i-era user scenario, **low confidence**.

### Intel ROM/source-family evidence

Intel's current Ethernet Connections Boot Utility explicitly contains UEFI drivers / Intel Boot Agent images used to program PCI option-ROM flash on supported Intel adapters. Intel's supported product list spans I210/I350, X520/X550, X710/XL710/XXV710 and newer families.

A public GitHub import (`Eric6666/IntelUndiPkg`, commit `0624fc4...`) states that its source trees were extracted from Intel PREBOOT `APPS\\EFI\\OPENSRC` packages. It contains four relevant open-source UEFI UNDI families:

- `GigUndiDxe`
- `XGigUndiDxe`
- `I40eUndiDxe`
- `IceUndiDxe`

This gives us source-family surrogates for static dependency analysis without guessing generic UEFI behavior.

## Next action in this pass

Inspect entrypoint + DriverBinding.Supported/Start for the candidate families, beginning with `I40eUndiDxe` because X710-DA2 is the strongest board-specific public candidate found so far. Extract only actual firmware dependencies (OpenProtocol/LocateProtocol, variables, PCI_IO operations, device-path helpers, Boot Services), then compare producers/state in DRFXI 1.12→1.15 only where those dependencies are concrete.

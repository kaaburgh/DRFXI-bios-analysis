# 1.17 dGPU / iGPU auto-detection

Last updated: 2026-09-10

Published 1.17 behavior:

- automatically detect dGPU;
- turn off iGPU when graphics configuration changes;
- alter when the iGPU setup item is modifiable.

## Code localization

The relevant new logic is in `OemDxe.efi`.

Observed image sizes:

- 1.15: 6,976 bytes
- 1.17: 7,648 bytes

The 1.17 `.text` section grows materially and contains a new function that performs PCI configuration-space discovery of display-class hardware.

## Variable mapping

The function constructs/uses the UEFI variable GUID:

```text
AmdSetupRPL
3A997502-647A-4C82-998E-52EF9486A247
```

The observed variable size is `0x6D5`, matching the corresponding IFR VarStore.

Within that structure, the function reads and writes byte offset `0x44`.

HII/IFR maps this exact offset to:

```text
iGPU Configuration
VarStore: AmdSetupRPL
VarOffset: 0x44

Auto                 = 0x0F
iGPU Disabled        = 0x00
UMA_SPECIFIED        = 0x01   [default]
UMA_GAME_OPTIMIZED   = 0x03
```

## Reconstructed behavior

The executable flow is consistent with:

```text
if dGPU appears and iGPU Configuration != Disabled:
    set iGPU Configuration = 0x00
    SetVariable(AmdSetupRPL)
    request hard reset

if dGPU disappears and iGPU Configuration == Disabled:
    set iGPU Configuration = 0x01 (UMA_SPECIFIED)
    SetVariable(AmdSetupRPL)
    request hard reset
```

The function also uses CMOS index `0x66` through ports `0x70/0x71` as state associated with graphics-configuration change detection.

A successful state transition ends in a hard reset using I/O port `0xCF9` with value `0x06`.

## Confidence

This is a **confirmed code-level mapping** of the 1.17 changelog item, not merely a correlation based on module names or strings.

The remaining work is annotation-level: identify the exact UEFI callback/event registration around the function and give symbolic names to all helper/protocol calls. That is not required to establish the basic behavior above.

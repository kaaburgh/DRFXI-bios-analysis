# DRFXI 1.12 → 1.15 — Intel LAN OPROM / POST-logo checkpoint

Date: 2026-09-10

Scope: only the DRFXI 1.13 changelog item:

```text
Fix hang at POST logo caused by Intel LAN OPROM
```

The 1.13 and 1.14 binaries are unavailable, so this checkpoint compares 1.12→1.15. Any observed change can only be called a candidate for the 1.13 fix unless its semantics directly identify the behavior.

## Result

The initial hypothesis that the LAN fix probably sits in `Bds.efi` because BDS grows substantially is weakened.

Confirmed in this bounded pass:

- `LanRomDriver`, `UefiPxeBcDxe`, `SnpDxe`, `NetworkStackSetupScreen`, and `RomLayoutDxe` PE images are byte-identical.
- `OptionRomPolicy` differs by exactly 11 bytes, all explained by `+3` PCD-token renumbering; its policy logic and strings are unchanged.
- `PciBus` differs by exactly two bytes, both the same token changing `0x3D0→0x3D4`; its executable semantics are unchanged.
- `Bds.efi` grows from 76,928 to 100,096 bytes (`.text +0x4410`, `.data +0x0F40`), but content anchors show old code surviving at shifted addresses rather than a wholesale rewrite.
- A major newly inserted BDS path is display/GOP/device-path handling: it checks PCI base class `0x03`, references `PciRoot(0x0)/Pci(0x8,0x1)`, manages `AmiGopOutputDp`, and uses device-path/`ConnectController` operations.
- The identifiable existing BDS Network Controller path checks PCI base class `0x02` at RVA `0x2A95` and `0x2D31` in both releases and is semantically unchanged after normalizing displaced helper calls.
- No newly introduced literal Intel vendor-ID (`0x8086`) branch was found in BDS, `OptionRomPolicy`, or `PciBus`.

### Relevant hashes

```text
Bds
1.12 184493a59bf9db882ad12550b1efb1f49aa81792d8479b01646a2ba7bccb649c
1.15 fe579a1b0c9e856bc6c600ba31aa98f88d2772aeae2d87d70f68ee87e2f2de99

OptionRomPolicy
1.12 cca026848f370a6caf46e29e897f6cf8c855bdd5a89028ebab82f11c39503587
1.15 cdb0b6239d8d53cdc49f4d22658634fb8177355f9de37d7b2a2dc246edfbe5b7

PciBus
1.12 7f320fe70d95a3d8bf7c99de142740fb0659d790049edaee01b18103f3b60363
1.15 d656f21414256a5aa2524f8773318e9d381bb5cb706f58d160e12ab968f231a3
```

### Network-function normalization

The only normalized differences in BDS RVA approximately `0x29FC–0x2DD1` are helper targets displaced by inserted BDS code:

```text
old 0x7AD8 -> new 0xB9F8
old 0x7734 -> new 0xB654
old 0x76B8 -> new 0xB5D8
```

No changed network-class condition or branch was found.

## Important unresolved point

The actual physical Intel LAN PCI Option-ROM binary has **not** yet been isolated. A top-level scan for plain uncompressed `PCIR` headers is insufficient because the ROM may be compressed or AMI-encapsulated.

Therefore byte identity of `LanRomDriver.efi` does not prove that the real Intel LAN OPROM payload is unchanged.

## Confidence

**Confirmed:** the obvious Option-ROM/network executable candidates and the explicit BDS Network Controller path do not contain the fix; a substantial part of BDS growth is unrelated GOP/display functionality.

**Medium-confidence hypothesis:** a smaller generic BDS connect/dispatch/order change could still implement the POST-logo workaround without an Intel-specific literal or class-0x02 code change.

**Open alternative:** the actual compressed/raw Intel LAN OPROM itself changed.

## Next narrow step

Identify the exact Intel LAN PCI Option-ROM FFS/raw/compressed object in both images, compare that object, and trace only its dispatch route. Do not broaden into more BDS reverse engineering unless the ROM payload proves identical.
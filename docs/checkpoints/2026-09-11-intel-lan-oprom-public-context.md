# Intel LAN OPROM POST-hang — public compatibility context

Date: 2026-09-11

Scope: supporting evidence for DRFXI 1.13 `Fixup hang Post logo by intel lan OPROM`. This file deliberately separates public/general evidence from direct evidence about the original BD790i reproducer.

## Direct BD790i reproducer evidence

No public report was found that names the exact Intel NIC / PCI Device ID behind the MINISFORUM changelog entry. Exact and close-variant searches for the changelog wording did not locate the originating bug report.

Therefore no Intel family is currently proven.

## Board-specific candidate context

Public BD790i usage shows X710-class cards are realistic:

- Reddit, Feb 2024: `Minisforum BD790i w/Intel X710-DA2 as OpnSense Router/Firewall?`
  https://www.reddit.com/r/homelab/comments/1agoogs/

This is evidence for plausibility of X710-DA2 on BD790i, **not evidence that it caused the 1.13 bug**.

## Intel's own description of the bug class

Intel support article `System Hangs on Boot after Upgrading Intel Boot Agent`:

https://www.intel.com/content/www/us/en/support/articles/000006885/ethernet-products.html

Intel describes a scenario in which, after updating the Intel Boot Agent / PXE image stored on an Intel Network Adapter, the computer hangs during boot because the **system BIOS does not support the newer PXE image**. Intel's primary remedy is a system BIOS update; removing the Intel adapter allows the machine to boot for the update.

This is highly relevant to the semantic interpretation of MINISFORUM's wording: `Fixup hang Post logo by intel lan OPROM` is fully consistent with a motherboard-BIOS compatibility workaround for an Option ROM physically resident on an add-in Intel NIC.

It does not identify which Intel family was involved.

## Cross-family historical examples

The general failure mode is not X710-specific.

### I350

A documented user case (`Intel i350-T2 NIC stops computer from booting`) describes a BIOS hang with an Intel I350-T2 until its boot-ROM configuration is changed.

https://forums.tomshardware.com/threads/intel-i350-t2-nic-stops-computer-from-booting.2426426/

Another Dell report describes I350-T4 causing a hang immediately after the BIOS splash screen.

https://www.dell.com/community/Optiplex-Desktops/Intel-I350-T4-network-card-hangs-after-BIOS-splash-cursor/m-p/7197958

### X520 / X540

Lenovo documents System x3100 M5 / x3250 M5 hanging on the POST screen when Intel X520/X540 adapters are installed. The resolution is a UEFI update; disabling the PCI Option ROM is a workaround.

https://support.lenovo.com/us/en/solutions/ht116370

## Consequence for candidate ranking

- X710/I40e remains the strongest **BD790i-specific public candidate** only because an X710-DA2 pairing is directly documented for this board.
- I350/GigUndi and X520/X540/XGigUndi have equally credible *generic* historical evidence for Intel NIC Option-ROM-induced POST hangs.
- Therefore the changelog wording itself cannot be used to promote X710 above these families with high confidence.

Current confidence:

```text
X710 / I40e        low-to-medium (board-specific plausibility)
I350 / GigUndi     low             (generic failure precedent)
X520/X540/XGig     low             (generic POST-hang precedent)
E810 / IceUndi     low             (supported family, weaker era/context fit)
```

The important conclusion is family-independent: an external Intel NIC Option ROM can expose exactly the BIOS compatibility failure described by the MINISFORUM changelog, and Intel itself recommends a motherboard BIOS update for this class of problem.

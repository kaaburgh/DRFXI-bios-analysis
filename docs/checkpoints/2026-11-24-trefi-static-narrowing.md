# DRFXI 1.15 / 1.17: DDR5 tREFI not editable, static narrowing

Date: 2026-11-24

Question: why tREFI cannot be edited on DRFXI 1.15 / 1.17, and whether the external claim that tREFI on AMD mobile parts became editable only with Ryzen 9000 / "newer AGESA" is reflected in these images.

Method: read-only static analysis of the official images (hashes below) plus the 1.04/1.07/1.12 images and the community 795iX3D dump as history controls. UEFI modules were extracted with uefi-firmware-parser. A first-party walker in `scripts/trefi_chain_audit.py` covers the same 362 (1.15) and 366 (1.17) named modules. PSP `$PS1` images were zlib-decompressed. IFR was parsed from the `CbsSetupDxeRPL` HII package. Disassembly used capstone (x86-64 for UEFI, Thumb-2 for ABL). No hardware, no flashing, no variable writes.

- 1.15 `3afaba6d916b3897d1d98bd5913008b38e89b6c51b2c6963c7109793541d8d88`
- 1.17 `99f3bab5ea491202bf365c23e6416f9d1e8a649ad00f90c1f3e21f1a61e35c51`

## Results

| Layer | 1.15 | 1.17 | Evidence class |
|---|---|---|---|
| IFR question for tREFI (`CbsSetupDxeRPL`, `AodDxe`) | none | none | confirmed |
| `AmdSetupRPL` field for tREFI | none: timing block `0x116`–`0x162` ends at Trdwr, then drive strengths at `0x164` | same | confirmed |
| UEFI writer of APCB token `0x419FF338` | none | none | confirmed |
| AOD (`AodSmm`) Trefi entry | none (25 timings) | none | confirmed |
| Static APCB contains `0x419FF338` | no | no | confirmed |
| ABL reads `0x419FF338` ("Override Tref") | yes, ABL 4C.11.90.20 | yes, byte-identical ABL | confirmed |
| Final `UMC::DramTiming12[Tref]` programming from the override | not traced | not traced | unknown |

History: the ABL consumer exists in 1.04 (PI 1.0.0.3a, ABL 32.3.90.20) and in 1.07/1.12 (PI 1.0.0.3d, ABL 35.23.90.20). A UEFI producer is absent in every analyzed image. This is a long-standing platform-layer omission, not a 1.15/1.17 regression.

Besides Tref, the ABL also reads three more override tokens (`0x4F641FDE` Tcksrx, `0xE9868CF1` Tcksre, `0x7A4972A9` Tpd) that no UEFI module ever writes. All 26 tokens that CBS does write (Memory Target Speed plus 25 timings) are consumed by ABL overlays.

## Conclusion

tREFI is not editable because the DRFXI CBS/AOD front end (generated AGESA CBS code plus HII) never exposes or writes it. Unlocking hidden menus cannot help. The PSP ABL in the same images already contains a tREFI override input keyed by APCB token `0x419FF338`.

This narrows the "newer AGESA" difference for Fire Range most plausibly to the CBS/AOD layer. That is an inference that needs a Fire Range image to confirm. It also leaves one unknown: whether ABL applies the override value to the effective register.

## Not done / limits

- The ABL downstream path from the timing-structure store (`+0x218`) to the `DramTiming12` write was not traced. The source of the override gate (`[ctx+0x20]`) is not established.
- No Fire Range or desktop ComboAM5 image was available for comparison.
- No runtime evidence (ZenTimings, SPI readback after saving manual timings) is available.
- Nothing here recommends writing an APCB token or patching firmware.

See `../findings/memory-trefi.md` for the living version, `../../evidence/memory/trefi-chain-excerpts.txt` and `../../data/trefi-token-map.csv`.

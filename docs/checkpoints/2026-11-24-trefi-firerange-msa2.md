# tREFI: Dragon Range vs Fire Range on the same board (Minisforum MS-A2)

Date: 2026-11-24

Follow-up to [`2026-11-24-trefi-static-narrowing.md`](2026-11-24-trefi-static-narrowing.md). Goal: find a Fire Range ("newer AGESA") image and check the tREFI chain layer by layer.

## Artifacts

Minisforum MS-A2 ships two official BIOS lines for the same board (`F1WSA`): `DRG` for Ryzen 7000 (Dragon Range) and `FRG` for Ryzen 9000 (Fire Range). Both `1.02` packages carry the same date (2025-06-16) and identical changelogs, so they form a matched pair that differs mainly in AGESA family.

Packages came from Minisforum's public download index. Hashes, URLs, vendor checksums, AGESA strings and ABL versions are in [`../../data/reference-firmware-hashes.csv`](../../data/reference-firmware-hashes.csv). The images are not committed.

Release notes in the packages:

- `DRG 1.00`: "Update PI 1.0.0.3h". `DRG 1.03` (2025-12-16) is still on 1.0.0.3h.
- `FRG 1.03` (2026-04-01): "Update PI 1.0.0.0F". `FRG 1.04` (2026-10-13): "Update PI 1.0.0.0G".

## Results (`scripts/trefi_chain_audit.py` plus manual disassembly)

| Image | AGESA | ABL | AOD `Tref Ctrl` / `Tref` question | UEFI writer of `0x419FF338` | ABL reads `0x419FF338` |
|---|---|---|---|---|---|
| DRFXI 1.15 / 1.17 | DragonRangePI-FL1 1.0.0.3h | 4C.11.90.20 | no | none | yes |
| MS-A2 DRG 1.02 / 1.03 | DragonRangePI-FL1 1.0.0.3h | 4C.11.90.20 (same overlay hash as DRFXI) | no | none | yes |
| MS-A2 FRG 1.02 | FireRangePI 1.0.0.0 | 51.15.0.20 | **yes** (`AodDxe`) | **`AodSmm`** | yes |
| MS-A2 FRG 1.04 | FireRangePI 1.0.0.0g | 64.24.0.20 | **yes** | **`AodSmm`** | yes |

Details:

- **Fire Range `AodDxe`** has the UTF-16 strings `Tref Ctrl`, `Tref`, `Specifies the Tref` and `Specify the tRef time. Valid Value: 0 ~ 0xFFFF. The value is in hex.`
- **Fire Range `AodSmm`** has the names `AodMemTimingTrefCtlDdr` and `AodMemTimingTrefDdr`. Right after the Twrrd/Trdwr token writes, the producer code continues:

  ```text
  cmp byte [rbx+0x3c], r13b      ; block gate (inferred: analogous to CBS 0x116)
  cmp byte [rbx+0x20f], r13b     ; Tref Ctrl == manual
  movzx r9d, word [rbx+0x210]    ; Tref value
  mov r8d, 0x419ff338            ; same token the Dragon Range ABL reads
  call r14                       ; APCB token write
  ```

  The Tref fields sit at the end of the AOD variable (`0x20F`/`0x210`), not inside the original timing block. That fits a feature appended later in the AOD layer.
- **The Fire Range AOD parameter set grows** from 64 to 106 `AodMem*` names relative to Dragon Range. The additions include Tref, separate TrcdRd/TrcdWr, 2D-training and DFE options, `AodMemOcMode`/`AodMemOcProfile` and several per-P-state drive/ODT names. FRG 1.02 and FRG 1.04 have identical sets.
- **`CbsSetupDxeRPL` has no Tref question in any image.** The tREFI front end on Fire Range is the AMD Overclocking (AOD) menu, not AMD CBS.
- **The Dragon Range AOD modules in MS-A2 DRG 1.03 are byte-identical to DRFXI 1.15** (`AodSmm` `d7d1a13f…`, `AodDxe` `2d0552fc…`).

## Conclusion

The "newer AGESA" difference behind editable tREFI on Fire Range is the **AOD front end**: an AOD question plus an `AodSmm` APCB producer for token `0x419FF338`. It was present already in FireRangePI 1.0.0.0 on MS-A2.

The token ID is the **same** one the Dragon Range ABL (32.3 → 4C.11.90.20) has always read. On Dragon Range, only the producer side is missing.

MS-A2 offers no within-Fire-Range "before/after" pair: every FRG image examined has Tref.

Still unknown: whether the Dragon Range ABL applies a supplied `0x419FF338` value to the effective `DramTiming12[Tref]`, and how the Fire Range ABLs (51.15 / 64.24) differ in that path.

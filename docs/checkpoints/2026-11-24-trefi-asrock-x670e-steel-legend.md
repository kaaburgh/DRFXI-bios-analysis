# tREFI before/after on desktop AM5: ASRock X670E Steel Legend 1.11.x → 1.21

Date: 2026-11-24

Context: [`2026-11-24-trefi-static-narrowing.md`](2026-11-24-trefi-static-narrowing.md), [`2026-11-24-trefi-firerange-msa2.md`](2026-11-24-trefi-firerange-msa2.md) and [`2026-11-24-trefi-abl-path.md`](2026-11-24-trefi-abl-path.md). Goal: a desktop "before/after" pair showing when AMD's own CBS gained tREFI, and how that relates to the Dragon Range CBS layout.

## Artifacts

The user supplied four packages from the ASRock BIOS page. Each zip SHA-256 matches the value printed on the ASRock page (screenshot supplied by the user). Hashes, AGESA strings and ABL versions are in [`../../data/reference-firmware-hashes.csv`](../../data/reference-firmware-hashes.csv). The images are not committed.

| Version | Date | ASRock description | AGESA (binary) | ABL |
|---|---|---|---|---|
| 1.11 | 2022-10-25 | Optimize system settings; enhance iGPU performance | ComboAM5PI 1.0.0.3 | 28.22.90.13 |
| 1.11.AS01 [Beta] | 2022-11-01 | Enhance graphics card performance | ComboAM5PI 1.0.0.3 | 28.22.90.13 |
| 1.11.AS03 [Beta] | 2022-11-04 | Enhance S3 mode | ComboAM5PI 1.0.0.3 | 28.22.90.13 |
| 1.21 | 2023-04-27 | Update AGESA ComboAM5 1.0.0.6; improve memory compatibility; optimize for 7000X3D | ComboAM5PI 1.0.0.6 | 2C.16.90.12 |

A forum user reported that tRef/tRefi first appeared in 1.20.AS01 [Beta] (2023-04-20). That build is not on the ASRock page and was not analysed.

## Results (`scripts/trefi_chain_audit.py`, `scripts/abl_tref_path.py`, IFR parse, x86 disassembly)

| Layer | 1.11 / 1.11.AS01 / 1.11.AS03 | 1.21 |
|---|---|---|
| AMD CBS IFR (`CbsSetupDxeRPL`) | no tREFI; timing block `0x116`–`0x162`, then `0x164` drive strengths | **`Trefi`**, numeric UINT16, `AmdSetupRPL` offset **`0x2E1`** (appended at the end of the variable, shown in the form between Twr and Trfc1), min 0, max `0xFFFF`, default `0xFFFF`, help "Specifies the Refresh Recovery Delay Time (tREFI)." No separate `Trefi Ctrl` |
| `CbsSetupDxeRPL` token producer | none | `if [0x116] (Active Memory Timing Settings) == enabled: write word token 0x419FF338 = AmdSetupRPL[0x2E1]`, placed right after the Twr write |
| `BctBaseSmmRPL` | none | same producer, same offsets |
| `AodSmm` | none | `if AOD buffer [+0x1B8] != 0: write token 0x419FF338` (also in its token table). There is no AOD IFR question (`AodDxe` has no Tref string) |
| ASRock `Setup` (OC Tweaker) | tRFC1/tRFC2/tRFCSb only | adds **"Refresh Interval (tREFI)"**, ASRock `Setup` varstore offset `0x178`, 0–0xFFFF, default 0 |
| ABL reads `0x419FF338` and programs `DramTiming12[15:0]` | **yes** (28.22.90.13: Override → `+0x218`, TimingPtr `+0x1AC`, field `+0x6C`, Override directly before Program UMC Timings) | yes (2C.16.90.12, same layout) |

## Interpretation

- **Confirmed:** in the Raphael desktop line, AMD's own CBS gained the tREFI question and its APCB producer between ComboAM5PI 1.0.0.3 (late 2022) and 1.0.0.6 (April 2023). In this pair it arrives together with an AOD-side producer and the vendor's own menu item.
- **Confirmed:** the ABL consumer was already present in ComboAM5 1.0.0.3 (ABL 28.22.90.13) with the same structure layout Dragon Range uses. So the ABL side predates the menu in both desktop and Dragon Range lines.
- **Confirmed:** the pre-1.0.0.6 desktop CBS layout (`0x116`–`0x162` timing block, `0x164` drive strengths, no `0x2E1` Trefi) is the same layout DRFXI 1.04–1.17 and MS-A2 DRG still use. DragonRangePI-FL1 up to 1.0.0.3h never took over the 1.0.0.6-era Trefi CBS addition.
- **Three ways the producer appears in this corpus:**
  1. desktop ComboAM5 1.0.0.6 — AMD CBS `AmdSetupRPL[0x2E1]` (plus SMM mirror and AodSmm);
  2. FireRangePI — AMD Overclocking (AOD) `Tref Ctrl`/`Tref` at the AOD variable `0x20F`/`0x210`, while Fire Range CBS has no Trefi;
  3. DragonRangePI — none.

  All three use the same token `0x419FF338`.

## Open side question

In ASRock 1.21 the CBS producer writes `AmdSetupRPL[0x2E1]` with no `Ctrl` gate whenever Active Memory Timing Settings is enabled, and the IFR default is `0xFFFF`. ABL 2C.16 has no `0xFFFF` filter in the Tref override. Two things were not checked: whether the CBS APCB word-token setter (reached through a protocol pointer) treats `0xFFFF` as "skip", and whether enabling Active Memory Timing Settings without touching Trefi applies tREFI = 65535.

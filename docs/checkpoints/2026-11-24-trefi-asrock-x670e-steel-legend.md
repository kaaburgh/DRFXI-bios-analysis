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

## `0xFFFF` handling in the CBS → APCB setter (ASRock 1.21)

In ASRock 1.21 the CBS producer writes `AmdSetupRPL[0x2E1]` with no `Ctrl` gate whenever Active Memory Timing Settings is enabled, and the IFR default is `0xFFFF`. The setter path was disassembled as follows.

Module hashes (decompressed PE, SHA-256 prefix): `CbsSetupDxeRPL` `b8725db405933e96`, `AmdApcbDxeV3` `12070b9a44de2756`, `AmdApcbSmmV3` `bb290cdcf4e7209e`.

1. **Caller.** In `CbsSetupDxeRPL`, the token-writing function at `0x4D58` takes `(AmdSetupRPL*, APCB protocol*)`. It caches protocol slots `+0x88` (8-bit set), `+0x98` (16-bit set) and `+0xA8` (32-bit set).
   - It first calls `+0x60`, then `+0xC0` with `dl=3`.
   - Trefi: `cmp [rbx+0x116],1; jne skip; movzx r9d, word [rbx+0x2E1]; mov r8d,0x419FF338; mov dl,3; call rbp`. There is no value test.
2. **Protocol.** `AmdApcbDxeV3` installs its protocol at `0x9E00` (Revision 3). Slot `+0x98` is `0x12D0` (Set16), and slot `+0xC0` is `0x191C`.
3. **Set16 `0x12D0`** either forwards `{purpose, token, value}` unchanged through a located protocol (SMM path) or calls `0x3CC0(purpose)` and then `0x4E18(token, value)`. It has no value check.
4. **`0x4E18`** checks only the priority level (2..5), gets the APCB buffer (`0x3D54`) and calls `0x6638(apcb, size, prioMask = 1<<(prio−1), 0xFFFF, token, value)`. The `0xFFFF` there is the **board-mask argument**, not a value sentinel.
5. **`0x6638`** (generic WORD-token set):
   - checks the `APCB` signature;
   - finds group `0x3000` (TOKN), type 2, by priority mask (`[entry+0xB]`) and board mask (`[entry+0xE] & 0xFFFF`, or equal to `0xFFFF`);
   - binary-searches the token;
   - **updates** an existing value (`mov word [rcx+4], ax`) or **inserts** a new `{token, value}` pair, then recomputes the checksum (`0x5E6C`).

   The value is never compared with anything.
6. **SMM variant.** `AmdApcbSmmV3`'s equivalent routine (`0x6984`) compares only priority masks and the `APCB` signature. Neither module contains any `cmp …, 0xFFFF`.
7. **Slot `+0xC0` → `0x5380`** recreates empty TOKN type entries (bool, byte, word, dword) for the selected priority through `0x7180`. In practice CBS clears its own token lists before rewriting them on each save. This is an inference from the call pattern.

**Result:** the CBS → APCB setter stores `0xFFFF` like any other value. In ASRock 1.21 with stock AMD CBS:
- if Active Memory Timing Settings is **disabled**, no Tref token is written, so the ABL default (3.9 µs / 1.95 µs) applies;
- if it is **enabled** and `Trefi` is left at its default, token `0x419FF338 = 0xFFFF` is written. ABL 2C.16 applies tokens in Override Timing without filtering, so `DramTiming12[15:0]` would become 65535.

This conclusion is static. It assumes the ABL core APCB token-get service (core table `+0xD8`) does not itself treat `0xFFFF` as absent; that service was not disassembled. ASRock's own "Refresh Interval (tREFI)" (default 0) feeds `AodSmm`, which writes the token only when the value is nonzero.

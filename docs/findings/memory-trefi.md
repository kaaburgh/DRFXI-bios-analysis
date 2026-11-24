# DDR5 tREFI (Tref) editability

Last updated: 2026-11-24

Scope: why DDR5 tREFI cannot be edited on DRFXI 1.15 / 1.17, checked layer by layer from the setup question down to the PSP AGESA boot loader (ABL). Static analysis only: no hardware, no flashing, no variable writes.

Dated snapshot: [`../checkpoints/2026-11-24-trefi-static-narrowing.md`](../checkpoints/2026-11-24-trefi-static-narrowing.md). Excerpts: [`../../evidence/memory/trefi-chain-excerpts.txt`](../../evidence/memory/trefi-chain-excerpts.txt). Token table: [`../../data/trefi-token-map.csv`](../../data/trefi-token-map.csv). Reproduction: [`../../scripts/trefi_chain_audit.py`](../../scripts/trefi_chain_audit.py).

## Short answer

- **Confirmed:** stock 1.15 and 1.17 have **no tREFI setup question** and **no UEFI code that writes a tREFI value** anywhere. The 1.17 clean HII unlock and AMIBCP-style access changes cannot expose tREFI: there is nothing hidden to unhide.
- **Confirmed:** the ABL in the same images **does read a tREFI override**. Its "Override Timing" routine requests APCB token **`0x419FF338`** (16-bit) and, when present, logs `Override Tref: 0x%x` and stores the value in the per-P-state timing structure, the same way it handles Tcl, Trfc1 and the other manual timings.
- **Confirmed:** this has been true since 1.04 (DragonRangePI-FL1 1.0.0.3a, ABL 32.3.90.20). It is not a 1.15/1.17 regression.
- **Narrowed cause:** the gap is in the platform-side **CBS/AOD front end** (IFR question plus APCB token producer), not in the ABL consumer.
- **Unknown:** whether a `0x419FF338` token, if one were present in the APCB, ends up as the effective `UMC::DramTiming12` Tref value. The ABL path after the override store was not traced to the register write.

## Firmware corpus

| BIOS | AGESA PI string | ABL version | ABL overlay holding "Override Timing" (decompressed SHA-256) |
|---|---|---|---|
| 1.04 | DragonRangePI-FL1 1.0.0.3a | 32.3.90.20 | `c4820bdff16ba4d731b939f13a9d64e8be0e184393fc82b4da11cf41c53ba586` |
| 1.07 | DragonRangePI-FL1 1.0.0.3d | 35.23.90.20 | `be90ebf29fdb88bb024bc73da868c154da3b51b41f47dcb4655b9c7c637c478e` |
| 1.12 / community 795iX3D | DragonRangePI-FL1 1.0.0.3d | 35.23.90.20 | same as 1.07 |
| 1.15 | DragonRangePI-FL1 1.0.0.3h | 4C.11.90.20 | `f4ec135a998b81ef7547e6b303fec72dd219b786442aad85c48ee6eaf4330c1c` |
| 1.17 | DragonRangePI-FL1 1.0.0.3h | 4C.11.90.20 | same as 1.15 |

All 20 ABL `$PS1` sub-images (flash `0x24AB00`–`0x2B6600`) are byte-identical between 1.15 and 1.17 after zlib decompression. None is encrypted.

## Layer by layer

### 1. HII / IFR: no question exists

`CbsSetupDxeRPL` has 574 IFR questions in both 1.15 and 1.17. The manual timing block in VarStore `0x5000` (`AmdSetupRPL`) is:

| Offset | Question |
|---|---|
| `0x116` | Active Memory Timing Settings |
| `0x117` | Memory Target Speed (word) |
| `0x119` … `0x162` | 25 `Ctrl` / value pairs: Tcl, Trcd, Trp, Tras, Trc, Twr, Trfc1, Trfc2, TrfcSb, Trtp, TrrdL, TrrdS, Tfaw, TwtrL, TwtrS, TrdrdScL, TrdrdSc, TrdrdSd, TrdrdDd, TwrwrScL, TwrwrSc, TwrwrSd, TwrwrDd, Twrrd, Trdwr |
| `0x164` | Processor CK drive strengths (next, unrelated block) |

There is no reserved slot for tREFI in the variable layout. No IFR prompt contains `refresh`/`refi`, so there is also no refresh-rate, fine-granularity-refresh or temperature-refresh question.

A case-insensitive ASCII and UTF-16LE search of every decompressed module body (362 named modules in 1.15, 366 in 1.17) finds no `trefi` or `refresh interval` string. The same search does find the neighbouring `Trfc1`, `Trfc2` and `TrfcSb` prompts in `CbsSetupDxeRPL` and `AodDxe`, which shows the search works.

### 2. CBS / AOD token producers: tREFI is never written

`CbsSetupDxeRPL` x86 code at RVA `0x4789`–`0x4BC5` writes 26 APCB word tokens. It writes Memory Target Speed and every timing whose `Ctrl` is set, and only when Active Memory Timing Settings is enabled. The token table is identical in 1.15 and 1.17, and the same token IDs appear in `BctBaseSmmRPL` and `AodSmm`.

`AodSmm`'s `AodMemTiming*Ddr` name list holds the same 25 timings with no Trefi entry. `AodDxe` has no Trefi prompt.

Token `0x419FF338` appears in **no** UEFI module of 1.04, 1.07, 1.12, 1.15, 1.17 or the community 795iX3D image. The positive control (Tcl token `0xFC195E5C`) appears in `CbsSetupDxeRPL` and `BctBaseSmmRPL` in all of them, and in `AodSmm` from 1.07 on.

### 3. APCB contents in flash

- Main APCB (`0x51D400`, mirrored at `0x8E5400`): its word-token list holds 11 platform tokens, none of them timing tokens.
- Small APCB instances (`0x522000`, `0x525000`): nearly empty token lists, apparently where CBS-written tokens go. Instance 0 is empty for every type. Instance 1 holds one byte token and two dword tokens.
- Token `0x419FF338` does not occur anywhere in the raw image.

The default manual-timing tokens (Tcl and the rest) are also absent from the static APCB. CBS therefore inserts tokens when the user saves manual timings, and **nothing in the APCB format itself prevents a Tref token** (inference).

### 4. ABL consumer: present

Overlay at flash `0x289940` (1.15/1.17), Thumb-2 code:

- `0x9D8C`: the "Override Timing" routine. It loops over P-states and channels and calls 19 getters. The getter for each timing checks that the token size is 2 and calls the ABL APCB token service (core table offset `+0xD8`) with a fixed token ID.
- `0x2D30`: the Tref getter. It requests token `0x419FF338`. The caller at `0xA0E6` stores the returned 16-bit value at timing-structure offset `+0x218` (stride `0x164` per P-state) and prints `Override Tref: 0x%x`.
- The 4 ABL-only override tokens (no UEFI producer) are Tref `0x419FF338`, Tcksrx `0x4F641FDE`, Tcksre `0xE9868CF1` and Tpd `0x7A4972A9`.
- All 26 CBS-written tokens are consumed by the ABL: 15 in this routine, the 10 turnaround tokens in overlay `0x29EBF0`, and Memory Target Speed in overlay `0x2787F0`.
- Side observation: Tcwl is not a user token. The override path sets `Tcwl = Tcl − 2`.

The routine runs only if a gate returns nonzero: `[ctx+0x20]`, checked by the function at `0x4508`. That gate's source was not established. It is plausibly the user-timing mode, which CBS always writes together with the timings (inference).

## Relation to the "new AGESA" claim

[brick2928/AMD-Mobile-overclocking-capabilities](https://github.com/brick2928/AMD-Mobile-overclocking-capabilities) lists tREFI as "No" for all Dragon Range parts and "Yes, with newer AGESA" for Fire Range (9955HX3D/9955HX/9850HX). Its only cited evidence is one Discord screenshot of a 9955HX3D system. It gives no AGESA version and no mechanism.

DRFXI evidence agrees that stock Dragon Range firmware gives the user no way to change tREFI. It does **not** support the reading that Dragon Range ABL lacks tREFI support: the ABL has read token `0x419FF338` since PI 1.0.0.3a. The most economical explanation is that the newer (Fire Range / ComboAM5-derived) AGESA added the **generated CBS/AOD layer** for tREFI: an IFR question, an `AmdSetup` field, a token write in CbsSetupDxe/BctBaseSmm and an AOD entry. Whether it also changed ABL behavior is unknown until a Fire Range image is compared.

## Open questions

1. Does a `0x419FF338` token in the APCB actually become the effective `UMC::DramTiming12[Tref]`? The ABL code observed around `DramTiming12` (refresh enable and P-state save/restore; a `0xC00FFFFF` mask) does not recompute the Tref field, but the main timing-programming path was not traced.
2. What feeds the Override Timing gate `[ctx+0x20]`?
3. Does a Fire Range BIOS with editable tREFI use the same token ID?

## Next bounded steps

1. **Fire Range comparison (static, highest value).** Run `scripts/trefi_chain_audit.py` on a FireRangeFL1 BIOS in which tREFI is reported editable. Record:
   - whether a `Trefi` IFR prompt exists, in which module, and at which VarOffset;
   - which UEFI modules write `0x419FF338`, or which other token sits next to the Trfc/TrfcSb token writes;
   - the ABL version, and whether "Override Tref" is still present.

   If the Fire Range producer writes `0x419FF338`, the Dragon Range ABL already accepts the same token and the gap is purely front-end.
2. **Hardware, read-only.** An SPI readback after saving manual timings in setup would confirm which tokens CBS inserts into the small APCB instances. Do not change firmware for this step.
3. Any experiment that **writes** a Tref token (APCB edit, CBS patch, runtime APCB service call) modifies boot-critical configuration. It needs its own safety and recovery analysis first. The ABL contains "Memory error occurs with default APCB" and "Clear CMOS and load default APCB" recovery paths, but their behavior on this board is unverified.

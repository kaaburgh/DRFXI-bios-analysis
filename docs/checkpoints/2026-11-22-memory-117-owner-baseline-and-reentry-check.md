# Checkpoint 2026-11-22 — DRFXI 1.17 DDR5: owner baseline, re-entry sheet and before/after comparison

Scope: static and offline work that is useful **before** the owner saves a read-only baseline on stock 1.15. No flashing, no variable writes, no runtime experiments. Earlier checkpoints of the same day are not modified.

Labels: **CONFIRMED** (byte/IFR fact), **STRONG EVIDENCE**, **INFERENCE**, **UNKNOWN**.

## 1. Re-entry path is unchanged in 1.17

| Component | 1.15 → 1.17 | Label |
|---|---|---|
| `AmdVariableProtection` (gate for runtime writes of `AmdSetupRPL` / `AodSetupRpl` / `AMD_PBS_SETUP`) | byte-identical | CONFIRMED |
| `CbsSetupDxeRPL`, `AodDxe`, `AodSmm`, `AmdApcbDxeV3`, `AmdApcbSmmV3` | PCD-token renumbering only | CONFIRMED (04) |
| CBS (574) and AOD (118) question tables, ranges, defaults | identical | CONFIRMED (06) |

Whatever path the owner used on 1.15 to reach the hidden CBS/AOD questions through HII (form browser → `RouteConfig` → CBS sync → APCB flush) meets the same code on 1.17. A modified 1.15 image is the exception: its visibility edits live in `AMITSESetupData`/`Setup`, which differ between releases, so it does not carry over (a 1.17 equivalent exists only as the hardware-untested patcher in `findings/clean-hii-unlock.md`). **STRONG EVIDENCE** (static; no hardware run).

## 2. What the menus can and cannot set

`evidence/memory-117/18-…` §2, machine-readable in `setup-questions.json`:

- 25 timing Ctrl/value pairs in CBS and the same 25 in AOD (Tcl, Trcd, Trp, Tras, Trc, Twr, Trfc1/2/Sb, Trtp, TrrdL/S, Tfaw, TwtrL/S, the eight read/write turnarounds, Twrrd, Trdwr), identical ranges; AOD enforces step 2 for Tcl and step 6 for Twr. **CONFIRMED**
- No question in either menu for tCWL, tREFI, tCKE, tSTAG, tMOD, Gear Down, Cmd2T or Nitro: these are AGESA-derived on both builds and cannot be "lost" by an update. **CONFIRMED** (absence in IFR). CBS `BankSwapMode` exists; its relation to ZenTimings BGS/BGS Alt is **UNKNOWN**.
- FCLK 2000 MHz is selectable in both menus (CBS code 48, AOD value 2000). UCLK DIV1 MODE, SoC voltage, DIMM VDD/VDDQ and VPP exist only in AMD Overclocking. **CONFIRMED**

## 3. Telling manual from Auto in a ZenTimings reading (no dump needed)

Auto values at DDR5-6000 for an SPD carrying the JEDEC DDR5-5600B 16 Gb x8 parameters (tAA = tRCD = tRP = 16 ns, tRAS 32 ns, tRC 48 ns, tWR 30 ns, tRFC1/2/sb 295/160/130 ns, tRTP max(7.5 ns, 12 nCK), tRRD_L max(5 ns, 8 nCK), tRRD_S 8 nCK, tFAW 32 nCK, tWTR_L max(10 ns, 16 nCK), tWTR_S max(2.5 ns, 4 nCK)), JEDEC rounding (0.974 guard), CL rounded to even:

| tCL | tRCD | tRP | tRAS | tRC | tWR | tRFC1 | tRFC2 | tRFCsb | tRTP | tRRD_L | tRRD_S | tFAW | tWTR_L | tWTR_S |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 48 | 48 | 48 | 96 | 144 | 90 | 885 | 480 | 390 | 23 | 15 | 8 | 32 | 30 | 8 |

A reading that matches a column was most likely left on Auto; one that differs must have been set. **INFERENCE** (the module's real SPD may deviate from the JEDEC bin; the dump-based sheet in §4 is authoritative).

## 4. Tooling: `memory_state_report.py`

New:

- **Re-entry sheet**: every CBS and AOD question whose stored value differs from its default, with Ctrl/value pairs printed only when the Ctrl is Manual and values gated off by an Auto control suppressed. AmdSetupRPL defaults are the shipped StdDefaults; AodSetupRpl defaults are IFR defaults (the variable is not in StdDefaults).
- **`--compare B.bin`**: lists every difference in the effective memory configuration (override-APCB tokens per instance/priority, non-token overrides, CBS and AOD sheets) between two dumps and exits 0 only when there is none. Build IDs and APOB NV state are informational.
- **`--aodsetup`** alongside `--amdsetup`: efivarfs exports alone produce the sheet without an SPI image (APCB state stays unknown).
- APCB headers are verified before decoding; a dump that is not 32 MiB or lacks headers at the fixed offsets is reported, not misparsed.

Validation (`18-…` §3–5): on a synthetic copy of the community dump with only the stored variables edited, the report lists exactly the edited settings and flags every one as `DIVERGES` (setup would push, APCB lacks the token) — the signature of a variable edit that never went through a Setup save. Self-comparison returns no difference; comparison with the official 1.17 image (= state after a full-image flash) lists the whole configuration as reverted plus the variables as absent. **CONFIRMED** on these inputs.

## 5. Privacy of an owner dump

The live NVRAM store of a configured board contains, besides the setup variables, Secure Boot keys and databases, boot entries, the TPM EK public key (`OfflineUniqueIDEKPub`), Windows VSM key-protector variables and an unlock ID (variable names seen in the community dump); the PSP area holds fTPM NV data. Recommended: run `memory_state_report.py` locally and share only its text output; dumps are never committed.

## 6. Owner procedure (read-only, in order of value)

1. On 1.15: save the ROM image (AFU `/O`, read-only) and/or export `AmdSetupRPL` and `AodSetupRpl` from efivarfs; run the report and keep its re-entry sheet.
2. Check the sheet for `DIVERGES` (settings stored but never pushed to APCB) and for which menu (CBS vs AOD) actually carries the settings.
3. After an eventual update: re-enter exactly the sheet through the same HII path, save once, let training complete, save a new image and run `--compare` against the 1.15 image. Zero differences means the configuration is reproduced; residual instability would then point at training margin, not at a lost setting.
4. Optional, hardware and owner's choice: measure training margin on 1.15 by repeating fresh trainings (for example with Memory Context Restore temporarily Disabled, every cold boot trains from scratch) and running a memory test after each; the training code is identical in 1.17, so this predicts the post-update behaviour. **INFERENCE** (that MCR Disabled forces full training each boot is AGESA's documented behaviour, not traced in ABL).

## Open

AFU `/O` output layout on this board (expected full 32 MiB; the tool warns otherwise), ABL internals (unchanged list), the owner's actual method and settings.

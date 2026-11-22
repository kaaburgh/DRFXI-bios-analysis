# Checkpoint 2026-11-22 — DRFXI 1.17 DDR5: owner's 1.15 readback, AMD Overclocking path

Scope: first real readback from the owner's BD790i X3D on stock 1.15 (AFUWINx64 `/O`, run locally; the image is not committed). Earlier checkpoints are not modified; this one corrects one inference from `2026-11-22-memory-117-regression-config-lifecycle.md`.

## 1. Where the owner's configuration lives — CONFIRMED

- CBS (`AmdSetupRPL`): Active Memory Timing Settings = Auto, Memory Context Restore = Auto, no CBS DRAM token in the APCB; generation token in sync (no pending resync).
- AMD Overclocking (`AodSetupRpl`): Active Memory Timing Settings Enabled, 6000 MT/s, 13 timings Manual (Tcl 36, Trcd 40, Trp 40, Tras 64, Trc 104, Twr 48, Trfc1 480, Trtp 16, TrrdL 12, TrrdS 8, Tfaw 32, TwtrL 24, TwtrS 7), FCLK 2000 MHz, UCLK = MEMCLK, VDDIO Ctrl Manual with DIMM VDD / DIMM VDDQ / APU VDDIO 1200 mV, Enable Platform PMIC Control = Disable.
- Override APCB: those settings as 21 purpose-2 tokens; APOB NV populated.
- Both Setup links ("AMD CBS", "AMD Overclocking") sit in the same form under the same `GrayOutIf` in 1.15 and 1.17 (Setup IFR walk); AMITSE access for these two links was not compared.

## 2. AodSetupRpl → APCB map — CONFIRMED on real data

`scripts/fwtools/aod_apcb_map.py` extracts every purpose-2 write from `AodSmm` (63 writes, identical in 1.15/1.17 apart from code addresses; `evidence/memory-117/19-…`, `aod-apcb-map.json`). Applied to the owner's AMD Overclocking settings it predicts all 21 stored tokens exactly (`20-…`). Notable entries: FCLK is converted from MHz to the CBS option code; DIMM VDD/VDDQ are written with two TRUE flags only when VDDIO Ctrl is Manual/Separate; "Enable Platform PMIC Control" has its own token; APU VDDIO has no token (extended-CMOS hand-off).

**Correction:** purpose-2 (AOD) tokens are stored in override instance 0 with priority mask **0x02**, not 0x10. The earlier inference came from the community dump's GNBG entry, which is unrelated. CBS (purpose 3) uses instance 1 / 0x04. With fiano's level order, AOD would outrank CBS where both set a token (**INFERENCE**: ABL not readable).

## 3. Tooling fix

The owner's first report flagged every AOD token as `DIVERGES`: the CBS expectation was compared against all override slots. `memory_state_report.py` and the generated `scripts/win/drfxi-mem.ps1` now check CBS against inst 1 / 0x04 and AMD Overclocking against inst 0 / 0x02 using the AOD map. `Combo CBS` (AmdSetupRPL 0x20) is marked as an internal selector in the sheet (**INFERENCE**).

## 4. Consequences for the 1.17 update

- The full-image flash removes `AodSetupRpl` and every purpose-2 token: the 22 AMD Overclocking entries above are what has to be re-entered, through the same menu; no CBS entry is involved except the owner's non-memory `CPPC Dynamic Preferred Cores = Driver` and `iGPU Configuration = Auto`.
- The APU VDDIO value in extended CMOS 0xA0/0xA1 survives the flash; whether ABL applies it while VDDIO Ctrl is back on Auto remains **UNKNOWN**. Re-entering VDDIO Ctrl Manual makes the question moot.
- Open: ZenTimings showed MEM VDD/VDDQ 1.10 V on this setup while 1.20 V is requested with platform PMIC control disabled. Whether processor firmware actually reprograms the SODIMM PMICs (or they refuse out-of-range values) is **UNKNOWN**; read-only check: HWiNFO DIMM PMIC sensors. If 1.20 V is effective it is part of the stability and must be re-entered; if not, the configuration runs at 1.10 V and the margin estimate in the earlier reply stands.

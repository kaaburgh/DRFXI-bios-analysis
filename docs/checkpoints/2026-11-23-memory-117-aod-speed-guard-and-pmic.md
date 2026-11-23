# Checkpoint 2026-11-23 — AOD speed-guard correction, first hardware run of the origin column, DIMM PMIC readout

Scope: results of the owner's run of the ZenTimings fork build `142.1+e7cf7a3` (PR kaaburgh/ZenTimings#1) on the BD790i X3D with stock DRFXI 1.15, and a correction to the AodSmm map. Earlier checkpoints are not modified.

Labels: **CONFIRMED**, **STRONG EVIDENCE**, **INFERENCE**, **UNKNOWN**.

## 1. Correction: Memory Target Speed guard polarity — CONFIRMED

`aod_apcb_map.py` recorded every `cmp BYTE PTR [rbx+OFF],r13b` as "write when [OFF] == 1" without looking at the following branch. One guard is inverted:

```
5573: cmp BYTE PTR [rbx+0x3c],r13b ; jne 0x58ed   -> requires [0x3C] == 1
557D: cmp BYTE PTR [rbx+0x3a],r13b ; je  0x5595   -> requires [0x3A] != 1
5583: movzx r9d,WORD PTR [rbx+0x3d] ; mov r8d,0xd06dbafb ; mov dl,2 ; call rsi
```

Memory Target Speed (token `0xD06DBAFB`) is written when *Active Memory Timing Settings* is Enabled **and AodSetupRpl[0x3A] != 1**. With `[0x3A] == 1` AodSmm instead writes `0xE753A04C` = TRUE and `0x244E47D0` = `[0x3B]` (unnamed IFR questions; a memory-profile selector is the likely meaning — **INFERENCE**). The AodSmm defaults builder sets `[0x3A]` to 0xFF (`4E98: mov WORD PTR [rbx+0x3a],0xff`).

Consequences:

- `aod_apcb_map.py` now takes the direction from `jne`/`je` and also records `cmp …,0xff` guards; guard format is `[offset, "eq"|"ne", [values]]`. Regenerated `aod-apcb-map.json` / evidence 19 differ only in this guard and in one non-DRAM write (`0xE033C709`, now `const 1` when `[0x187] != 0xFF`).
- Evidence 20 is revised: the first version set `[0x3A] = 1`, which "matched" only because the map had the same polarity error. With the driver default 0xFF the corrected map again predicts all 21 stored tokens; a counter-check shows that `[0x3A] = 1` drops the speed token.
- `memory_state_report.py` and the generated `scripts/win/drfxi-mem.ps1` evaluate the new guard format.
- The ZenTimings PR copied the wrong polarity (`aod[0x3A] == 1` for the speed origin and the speed plausibility check), which is exactly why the hardware run showed `Speed`/`MCLK` as Auto (section 2). Reported on the PR.

## 2. First hardware run of the origin column — owner's DRFXI 1.15

From the owner's screenshot and debug report:

- `AmdSetupRPL` and `AodSetupRpl` are readable from Windows through `GetFirmwareEnvironmentVariableEx`; layout `drfxi-dragonrange-v1` matched, plausibility passed. **CONFIRMED** (was TO VERIFY).
- Origins as predicted from the SPI readback: 13 timings, FCLK, UCLK and the three voltage rows `AOD`; turnarounds, tRFC2, tRFCsb, ODT/RTT/drive strengths, PowerDown, VPP, VDD Misc `Auto`; AGESA-only rows `·`; BGS `?`; CPU VDDIO without a reading and without a false `≠`.
- Only deviation: Speed and MCLK shown as Auto — the guard error of section 1.
- The same build's debug report fails in "BIOS: Memory Controller Config" (null reference); later fork commits address it and have not been run yet.

## 3. DIMM voltages: the saved 1.20 V is not applied — CONFIRMED

The debug report reads the PMIC on each SODIMM (HMCG78AGBSA095N, PMIC5100 by MPS, SPD5118 hub):

| Register / ADC | Value |
|---|---|
| PMIC mode | Secure |
| High Voltage Mode | Disabled |
| VDD set-point / SWA ADC | 1100 mV / 1095 mV |
| VDDQ set-point / SWB ADC | 1100 mV / 1095 mV |
| VPP set-point / SWC ADC | 1800 mV / 1785 mV |

AMD Overclocking holds DIMM VDD = VDDQ = 1200 mV with VDDIO Ctrl Manual and Enable Platform PMIC Control = Disable, and the APCB carries the corresponding tokens, yet the PMIC set-points are the JEDEC 1100 mV. The configuration therefore runs at **1.10 V**. Why the request is not applied — ABL not programming the PMICs on this platform, or the PMIC in Secure mode refusing the write — is **UNKNOWN** (ABL is not readable; PMIC write-protection behaviour was not tested).

Consequences for the 1.17 question: the DIMM-voltage entries do not contribute to the current stability, so forgetting them after an update would not change the running state; re-entering them is harmless. The stability margin estimate for tRFC 160 ns at stock VDD/VDDQ from the earlier analysis applies as is. APU VDDIO (memory-controller side) has no reading on this board, so whether its 1200 mV request is applied stays **UNKNOWN**.

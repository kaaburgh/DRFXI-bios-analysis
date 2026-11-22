# DDR5 tuning regression after DRFXI 1.15 → 1.17

Last updated: 2026-11-22 (afternoon: AFU coverage + consumers, corrections)

Living summary. Details, evidence references and the hypothesis table are in `../checkpoints/2026-11-22-memory-117-regression-config-lifecycle.md`, corrected and extended by `../checkpoints/2026-11-22-memory-117-afu-coverage-and-dram-consumers.md` (and the earlier `2026-11-14-memory-117-regression-static-narrowing.md`). Evidence: `../../evidence/memory-117/`.

Trigger: one BD790i owner reported that after 1.17 the previous manual DDR5 timings produced memory errors/BSODs, Auto values looked much looser (tRFC ~968, tWR 96) and some earlier values were no longer reachable. Single-system report; applicability to BD790i X3D is not assumed.

## What does not differ (CONFIRMED)

- AMD part of the image: 18 bytes (APCB `UniqueAPCBInstance` + checksums); ABL0, PMU firmware, microcode, SMU firmware and all APCB payloads identical.
- Memory PEI path identical; memory-related DXE/SMM modules differ only by PCD-token renumbering (verified per byte).
- CBS (`AmdSetupRPL`, 574 questions) and AOD (`AodSetupRpl`, 118 questions) IFR, ranges and StdDefaults identical; the CBS→APCB token map (89 tokens) and the CBS fingerprint routine identical.
- `STABILITY_BOOST` (PCD 0x496) results in the same zero byte at `+0x4DF` of the SMU configuration structure as 1.15.
- Every other 1.15→1.17 delta is classified and none is on the memory path; a 1.16 memory change cannot persist into 1.17 unseen.

## How memory configuration actually flows (both versions)

```text
Setup UI ──Save──> AmdSetupRPL (NVRAM) ──CbsSetupDxeRPL sync──> APCB override tokens (purpose 3) ──flush──> SPI
                                   │                                                       │
                     AMD Overclocking (AodSetupRpl) ──AodSmm──> same token IDs, purpose 2   └─> discard memory context
                                                                                                (ext. CMOS 0x0D bit)
next boot: ABL reads APCB (+ platform defaults, priority 0x20) ─> train or restore (MCR) ─> APOB / APOB NV
```

- The sync purges all purpose-3 tokens and re-adds only non-Auto values. Timing tokens require `Active Memory Timing Settings = Enabled` **and** the timing's `Ctrl = Manual`. Auto means "no token": ABL derives the value from SPD/JEDEC.
- Every boot `CbsSetupDxeRPL` (a) resets CBS to code defaults if ABL reports APCB recovery or the generation token is `'RECV'`, (b) loads `AmdSetupRPL`; a missing variable, or one with a foreign header signature (StdDefaults have a zero header), is rebuilt from **code defaults** (= StdDefaults values, generation `0x4B9D5809`), (c) resyncs only if `[0x08]` ≠ APCB token `0xB331378E`. Out-of-band edits of the variable are not pushed by this path, and the SMM duplicate sync in `BctBaseSmmRPL` is never called.
- Any APCB flush discards the saved memory context → full training on the next boot.
- Memory Context Restore: Setup "Auto" → token not pushed → platform default `0xFEDB01F8 = TRUE`. MCR is effectively on.

## Mechanism that fits the report

The shipped command `/p /b /n /k /r /l /RLC:E` rewrites **the whole 32 MiB**: SmiFlash classifies the eleven AMD/PSP areas as non-critical blocks, so `/K` rewrites the APCB (image copy: no timing tokens) and APOB NV (blank), `/N` rewrites NVRAM (only StdDefaults), with no firmware-side setup preservation and no `/SP`. The first 1.17 boot therefore trains from scratch with Auto (SPD-derived) timings — tWR 96 / tRFC 968 = 30 ns / ~302 ns at DDR5-6400 — and MCR (platform default TRUE) keeps that training. The owner's first Setup save with re-entered values flushes the APCB, discards the context and trains again; anything not re-entered (AOD voltages, UCLK mode, Power Down, ODT/drive strengths, secondary timings, the master gate, the other menu) stays at default. None of this requires a 1.17 change. 1.17 adds one more retrain trigger: `OemDxe` flushes the APCB when the dGPU state changes. CMOS-resident AOD VDDIO hand-off (ext. CMOS 0xA0/0xA1) survives the flash; its effect is unknown.

Status: SPI coverage **STRONG EVIDENCE** (firmware classification confirmed, AFU flag semantics from its own help text); settings/training reset mechanism **STRONG EVIDENCE**; causation of the BD790i observation **INFERENCE** pending hardware data. A visible proxy: the update should also reset fTPM state (PSP NV data is in the rewritten range).

## Real-data validation (community 795iX3D readback, 1.12-based)

`evidence/memory-117/17-…`: on a board configured and saved through Setup, `AmdSetupRPL` carries signature `0xFC4053AA` and generation `0x4B9D5809` equal to the override-APCB token (no pending resync), the live NVRAM store sits in the backup NV area `0x1BC0000`, APOB NV is populated (ABL recorded APCB instance 0x60, recovery flag 0), and a runtime APCB write raised the override APCB's `UniqueAPCBInstance` from 0x2732 to 0x2733. `memory_state_report.py` now scans both NV areas.

## BD790i X3D

Same image, same APCB, same code: the reset/retrain behaviour and MCR default apply identically. Nothing predicts that a complete, re-entered DDR5-6000 configuration behaves differently on 1.17; it must be re-entered in full and re-validated on fresh training.

## Next (read-only)

Baseline on 1.15: efivarfs exports of `AmdSetupRPL` (`3a997502-647a-4c82-998e-52ef9486a247`), `AodSetupRpl` (`5ed15dc0-edef-4161-9151-6014c4cc630c`), `AMD_PBS_SETUP` (`a339d746-f678-49b3-9fc7-54ce0f9df226`), a saved SPI image, running timings and WHEA counts → `scripts/fwtools/memory_state_report.py`. Decisive comparison: Auto timings at the same target speed on 1.15 and 1.17.

Open: AFU-side behaviour beyond its help text (not disassembled), ABL internals (MCR, discard bit, CMOS VDDIO hand-off, AOD-vs-CBS priority, APCB-recovery conditions), the reporter's complete settings.

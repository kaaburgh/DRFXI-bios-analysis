# DDR5 tuning regression after DRFXI 1.15 → 1.17

Last updated: 2026-11-22

Living summary. Details, evidence references and the hypothesis table are in `../checkpoints/2026-11-22-memory-117-regression-config-lifecycle.md` (and the earlier `2026-11-14-memory-117-regression-static-narrowing.md`). Evidence: `../../evidence/memory-117/`.

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
- Boot-time resync: if `AmdSetupRPL[0x08]` ≠ APCB token `0xB331378E`, the sync runs automatically. StdDefaults have `[0x08]=0`, so a reset NVRAM always triggers it. Out-of-band edits of the variable (outside Setup) are not pushed by this path.
- Any APCB flush discards the saved memory context → full training on the next boot.
- Memory Context Restore: Setup "Auto" → token not pushed → platform default `0xFEDB01F8 = TRUE`. MCR is effectively on.

## Mechanism that fits the report

The shipped flash command (`/p /b /n /k /r /l /RLC:E`, no `/SP`, no firmware-side setup preservation) resets NVRAM. The first boot then rebuilds the APCB from defaults, discards the memory context and trains from scratch; MCR keeps that new training. Afterwards Auto values are SPD-derived (tWR 96 / tRFC 968 = 30 ns / ~302 ns at DDR5-6400), and re-entered "old" timings run on a different training result and without any setting that was not re-entered (AOD voltages, UCLK mode, Power Down, ODT/drive strengths, secondary timings, master gate, the other menu). None of this requires a 1.17 change. 1.17 adds one more retrain trigger: `OemDxe` flushes the APCB when the dGPU state changes.

Status: mechanism **CONFIRMED** in code; that it caused the BD790i observation is **INFERENCE** pending hardware data.

## BD790i X3D

Same image, same APCB, same code: the reset/retrain behaviour and MCR default apply identically. Nothing predicts that a complete, re-entered DDR5-6000 configuration behaves differently on 1.17; it must be re-entered in full and re-validated on fresh training.

## Next (read-only)

Baseline on 1.15: efivarfs exports of `AmdSetupRPL` (`3a997502-647a-4c82-998e-52ef9486a247`), `AodSetupRpl` (`5ed15dc0-edef-4161-9151-6014c4cc630c`), `AMD_PBS_SETUP` (`a339d746-f678-49b3-9fc7-54ce0f9df226`), a saved SPI image, running timings and WHEA counts → `scripts/fwtools/memory_state_report.py`. Decisive comparison: Auto timings at the same target speed on 1.15 and 1.17.

Open: AFU's exact SPI coverage (survival of AOD purpose-2 tokens / APOB NV), ABL internals (MCR, discard bit, AOD-vs-CBS priority), the reporter's complete settings.

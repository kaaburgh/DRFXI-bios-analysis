# DDR5 DIMM VDD/VDDQ: the module PMIC decides

**Question (2026-11-25).** On a stock DRFXI 1.15 BD790i X3D, DIMM VDD/VDDQ were set to 1.2 V in the AMD Overclocking (AOD) menu, but HWiNFO's DIMM PMIC readings stay at 1.1 V. Is this a firmware block or a module lock?

**Answer (static).** The firmware does try to apply the value. The module's PMIC refuses it. There is no software path past that refusal.

## Firmware side (DRFXI 1.15)

**AOD producer.** `AodDxe`/`AodSmm` write these APCB tokens at priority 2 (see `../checkpoints/2026-11-24-trefi-apcb-service-feasibility.md` §8):

| Token | Meaning |
|---|---|
| `0x66CAD59B` | DIMM VDD, mV |
| `0x814A6C32` | DIMM VDDQ, mV |
| `0x288F8A28` | Enable Platform PMIC Control |

AOD help text for the last one: "When Enable Platform PMIC Control is enabled, the DDR PMIC voltages are not adjusted by processor FW, and may be adjusted directly by EC or other platform based mechanism." The AOD range for VDD/VDDQ is 800–1430 mV in 10 mV steps.

**ABL consumer.** Overlay `0x2787F0`, "PMIC Overrides", file offsets:

1. `0x1D0C` reads bool token `0x288F8A28`. If it is 1 (`0x4DEE`), ABL logs "PMIC voltages are adjusted by EC or other platform machanism" and skips the routine.
2. Otherwise, for each populated DIMM, ABL reads PMIC register `0x2F` (`0x4E66`). It writes it back with bit 2 set (`orr r2, r0, #4`, `0x4E86`/`0x4E90`), which requests Programmable Mode, then reads it again (`0x4E94`).
3. **If bit 2 reads back as 1**, ABL logs "PMIC is in Programmable Mode". It optionally applies a customer R2B[5:3] value, then programs the voltages: VDD starts at the default `0x44C` = 1100 mV, is replaced by the token value when present, and is logged as "PMIC Set VDD = %dmV". VDDQ and VPP follow the same pattern.
4. **If bit 2 reads back as 0** (`bge 0x4F44`, literal `0x2B788` → string at `0xB688`), ABL logs "Channel %d, Dimm %d PMIC is in Secure Mode. Default settings can not be overridden." and moves on to the next DIMM without writing any voltage.

## Board readback

The board owner's APCB extract (§9 of the checkpoint) holds the following in the active override `0x522000`:

| Token | Value |
|---|---|
| DIMM VDD `0x66CAD59B` | 1200 |
| DIMM VDDQ `0x814A6C32` | 1200 |
| Enable Platform PMIC Control `0x288F8A28` | 0 (processor FW programs the PMIC) |
| `0x6CD36DBE`, `0x72958E2C` | 1 |

The firmware therefore requests 1.2 V. HWiNFO reads the PMIC's own telemetry, and that stays at 1.1 V. This matches step 4: the module's PMIC ignores the Programmable Mode request, i.e. it is in Secure Mode.

## Consequences

- **No firmware or OS workaround.** ABL already performs the only unlock step a host can perform (set R2F[2] and verify). A runtime SMBus/I3C write from the OS would send the same request and get the same refusal.
- **Where the lock lives.** Whether a PMIC accepts Programmable Mode is fixed by the module/PMIC vendor's configuration, not by the BIOS or by SPD contents. No public, safe procedure to change it is known.
- **The only route is hardware.** Modules whose PMIC accepts Programmable Mode, typically modules sold with XMP/EXPO profiles above 1.1 V. With such modules, the 1.2 V tokens already stored would be applied at the next boot.
- **CPU-side VDDIO.** The AOD VDDIO control ("Manual" synchronises APU VDDIO to DIMM VDD, "Separate" sets it independently) concerns the processor's memory-IO rail, which is a different rail from the DIMM PMIC outputs. It was not analysed here.

Not verified on hardware: the ABL debug log, which would print `PMIC 0x2F = …` and the Secure/Programmable line per DIMM, was not captured.

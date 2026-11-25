# Static feasibility: writing the Tref token via the firmware's own APCB service (DRFXI 1.15)

Date: 2026-11-24

Question: on DRFXI, APCB token `0x419FF338` is read by the ABL but no stock producer writes it. Could the firmware's own APCB write service be used to inject it, and what are the gates, persistence and recovery? Static analysis only; no hardware, no flashing, no injector written.

Baseline is **DRFXI 1.15** (the reporter's board runs 1.15; ZenTimings shows `AGESA DragonRangePI-FL1 1.0.0.3h`, DDR5-6000, tREFI 11677 at MCLK 3000, which is exactly the ABL default 3.9 µs ÷ tCK). Modules (decompressed PE, SHA-256 prefix): `AmdApcbDxeV3` `7d42c7eefdb02ce2`, `AmdApcbSmmV3` `9dd2f6fc7be93f9f`, `CbsSetupDxeRPL` `0aafafee9e5f51d7`, `AodSmm` `d7d1a13f5bb7ef04`. Reproduce the disassembly with `scripts/lib/x86mod.py`.

## 1. The write service exists and CBS uses it

`AmdApcbDxeV3` installs a protocol (Revision 3) whose function table sits at module offset `0xA160` (`03 00…` revision, then 26 entry pointers). Relevant slots:

| Slot | RVA | Meaning |
|---|---|---|
| +0x88 | `0x10E0` | SetToken8 |
| +0x98 | `0x12D0` | **SetToken16** (used for Tref) |
| +0xA8 | `0x14C0` | SetToken32 |
| +0xC0 | `0x191C` | recreate empty token lists |
| +0xD8 | `0x2108` | writeback / lock helper |

`CbsSetupDxeRPL` and `BctBaseSmmRPL` reach exactly this table to write the manual-timing tokens, so the same `SetToken16(purpose, token, value)` could carry `0x419FF338`.

## 2. Access control is present but NOT armed on DRFXI

Both modules contain an "Apcb Tokens Register Permission" whitelist with `[Apcb Tokens Access]… Uid 0x%x is Access Denied` logging. It is inert here:

- **SMM `SetToken16` (`0x2274`)** enforces only when `PermEnabled (byte 0xE069) == 1` **and** `SmmLocked (byte 0xE068) == 1`; otherwise it jumps straight to the write. Across the whole SMM module the only store to either flag, or to the whitelist pointer `0xE060` / count `0xE06C`, is `mov byte [0xE069], 0` at driver init. Nothing sets them to 1 and nothing populates the whitelist.
- **`RegisterPermission` (`0x40C4`)** bails immediately unless `PermEnabled != 0` and a whitelist buffer already exists at `0xE060`. Since `PermEnabled` is only ever cleared, registration can never run. The feature is dead code on this build (gated off, consistent with a disabled PCD).
- The whitelist check `0x1AC4` matches a 5-byte record `{u32 token, u8 attr}` and requires `attr-1 ≤ 2` and `attr & requested`. Moot while disabled.

So the SMM `SetToken16` accepts any token id, including `0x419FF338`. The active DRFXI protection is the separate `AmdVariableProtection.efi` (which locks the UEFI *variables* `AmdSetupRPL`/`AMD_PBS_SETUP`/`AodSetupRpl`), not this APCB-token permission layer.

## 3. DXE-local vs SMM routing flips at Ready-To-Boot

`AmdApcbDxeV3` `SetToken16` (`0x12D0`) branches on byte `0xCFA8`:

- `0xCFA8 == 0` → **local** write (`0x137E`: `0x3D30` then `0x4E94`), directly into the in-RAM APCB, no access check at all (identical to the ASRock local path).
- `0xCFA8 != 0` → build SMM command `0xA1CB000A` and forward to the SMM handler (which, per §2, also doesn't enforce).

`ApcbRTBDxeCallBack` (`0x22DC`) sets `0xCFA8 = 1`. That callback is a Ready-To-Boot handler, which fires before any boot option — including a UEFI Shell launched from the boot menu. So a Shell-time caller would hit the SMM-forwarding path, while firmware-internal callers during DXE/BDS hit the local path. Both accept the write.

## 4. Persistence needs an explicit SPI write-back

A `SetToken16` updates only the RAM APCB copy and recomputes its checksum (`0x6638` → `0x5E6C`); it does not touch SPI. Flushing is a separate action: SMM command `0xA1CBD301` → `AmdPspWriteBackApcbShadowCopy` (`0x4F6C`). That routine **exits without writing if `APCB.RecoveryFlag` is set**, and is further gated by flags `0xE138`/`0xE139`. CBS triggers the write-back after it finishes writing tokens (on Save & Exit). An external injector would have to trigger the write-back itself; without it the token is lost at reset.

## 5. Survival to the next boot

The ABL only **reads** tokens — the memory overlays call the get-token service (table `+0xD8`) 23×, and no token-set service is called. ABL does not rewrite the APCB, so an injected token is not erased by ABL. CBS rewrites *its own* priority's token list on each settings save; an injected token at the same priority would be purged on the next CBS Save. Whether a value written to a priority CBS never clears would survive a CBS save was not fully resolved (slot `+0xC0` recreates empty lists per priority; which priorities CBS clears is the open part).

## 6. Automatic recovery is training-failure-based — the key risk

The ABL overclock-failure recovery (overlay `0x289940`, routine at `0x1900`) keeps a persistent counter:

- reads `APCB_TOKEN_UID_MEM_OVERCLOCK_FAIL_CNT` (token `0xE5325C7B`) as the threshold;
- increments a saved fail count on each failed attempt;
- when the count reaches the threshold: prints `Clear CMOS and load default APCB`, clears CMOS (SVC sequence writing `0x5555`), and reloads the **default** APCB — which would wipe an injected token.

But this fires only on a **memory-training/boot failure**. An over-aggressive tREFI usually trains and boots cleanly and then causes instability or data corruption under load, especially warm. In that case the counter never increments, recovery never fires, and there is **no automatic rollback** — the failure surfaces in the OS. This is the dominant risk and it is structural, not incidental.

## 7. Follow-up: what is actually armed for recovery (DRFXI 1.15)

- **OC-failure threshold is configured.** Token `0xE5325C7B` (`APCB_TOKEN_UID_MEM_OVERCLOCK_FAIL_CNT`) is present in the main APCB (`0x51D400`, mirror `0x8E5400`): byte token, priority mask `0x20`, value **1**. So the §6 "Clear CMOS and load default APCB" path is configured with threshold 1. The extra gate checked before it (`[ctx+0x28]->[0x10] == 1`) was not identified. No DXE/SMM module writes this token; the CBS menu has no matching question.
- **APCB integrity handling in the ABL core** (overlay `0x24ADA0`, ~`0x884`–`0x8F8`):
  - if an APCB entry fails validation and the loader is not already in recovery and the failing entry is not the backup type `0x68`, it logs "Recoverable APCB Checksum Error" (postcode `0xE329`), sets a recovery flag and takes an alternate load path. By the structure this is most likely the backup `APCB_COPY` (`0x68`); that is an inference.
  - if it is already in recovery, or the failing entry is the backup itself, it logs "Fatal APCB Checksum Error" (postcode `0xE32A`) and stops (`svc #0`, code `0x10`). This happens in the PSP before x86 runs: no POST, no UEFI, so no software recovery is possible.
- `AmdPspWriteBackApcbShadowCopy` refuses to write while `APCB.RecoveryFlag` is set (§4).

## 8. Follow-up: real board readback (BD790i X3D, stock DRFXI 1.15) and purge semantics

The board owner ran an APCB/NVRAM parser on a full readback of a stock DRFXI 1.15 BD790i X3D with manual timings set in the stock AMD Overclocking (AOD) menu. Structural facts, cross-checked against the official image:

| Copy | State on the board | Contents |
|---|---|---|
| Main APCB `0x51D400` (`0x68` inst 0, defaults, priority mask `0x20` = level 6) | **factory**: payload SHA-256 prefix `7a1bfc4ac026cb94` equals official 1.15 | platform defaults incl. `MEM_OVERCLOCK_FAIL_CNT`=1 |
| Active override APCB `0x522000` (`0x60`) | **rewritten**: size `0x410` (factory `0x128`), 32-bit instance field at `+0x0C` `0x00B55A83` (factory `0x00006A06`) | AOD timing/voltage tokens at **priority mask `0x02` (level 2)**, instance 0; CBS sync-generation token `0xB331378E` at mask `0x04` (level 3), instance 1; a GNB type `0x1705/0x1002` override at mask `0x10` (level 5) |
| Override backup `0x525000` (`0x68` inst 8) | **factory** (`0x6A06`, size `0x128`, factory tokens) | — |
| B-side mirrors `0x8E5400/0x8EA000/0x8ED000` | not reported | — |

So the firmware's own write-back updates only the active override copy at `0x522000`. The main APCB and the override backup keep their factory content, so a good fallback copy exists for the "Recoverable APCB Checksum Error" path in §7. No Tref token is present, which matches the observed tREFI 11677 (= default 3.9 µs at MCLK 3000).

**How AOD writes** (`AodSmm` `0x533C`, DRFXI 1.15):

1. It acquires the APCB mutex (`+0x60`).
2. It calls **`+0xD0` "APCB purge tokens"** with priority 2 and an explicit list of **59 AOD-owned token IDs** built on the stack. That list has the timings, PHY/ODT/drive, voltages, UCLK/FCLK and PMIC IDs. **`0x419FF338` is not in it.**
3. It writes the current AOD values at priority 2 (`dl=2`).
4. It flushes with `+0x08` ("Write back APCB to SPI") and releases the mutex with `+0x68`.

Six AOD token IDs the parser left unnamed map as follows: `0xF0947E37` = UCLK DIV1 mode `[0x96]`; `0x814A6C32` = DIMM VDDQ `[0x195]` and `0x66CAD59B` = DIMM VDD `[0x193]`, both written only when VDDIO Ctrl `[0x192]` is 1 or 2; `0x6CD36DBE` and `0x72958E2C` = two boolean flags set to 1 under the same VDDIO-control condition; `0x288F8A28` = Enable Platform PMIC Control `[0x1A9]`.

**How CBS writes:** it clears **all** of its own priority-3 token lists (`+0xC0` with `dl=3`) and rewrites them only when Active Memory Timing Settings is enabled. On this board it is Auto, so CBS pushes no timing tokens. Its sync token matches the setup variable, so no resync runs at boot.

**`+0xD0` semantics** (DXE `0x1834` → core `0x5170`): only priorities 2..5 are allowed ("APCB writes not allowed at the current priority" otherwise). The routine sorts the passed IDs and deletes exactly those tokens at the selected priority.

**Consequences for a Tref token** (inference from the above):

- Written as a WORD token at priority 2 in the active override APCB, it sits next to the AOD tokens that ABL demonstrably applies. Priority 2 also outranks CBS (3), consistent with the community observation that AOD overrides CBS.
- It would **survive** AOD saves (AOD purges only its 59-ID list), CBS saves (level 3 only) and, by the same logic, "Load Optimized Defaults".
- That stickiness cuts both ways. A bad value is **not** removed by loading defaults in setup. It has to be overwritten or deleted with the same tool, or removed by an APCB fallback to the backup or default copy.
- Whether the "Clear CMOS and load default APCB" / recovery path permanently restores `0x522000` from the backup, or only boots once with defaults: see §10 (restores; traced statically).

This resolves the §5 purge question for AOD and CBS.

## 9. Follow-up: B-side copies, image integrity, and board hardware (2026-11-25)

The board owner ran `scripts/extract_apcb_regions.py` on the same stock 1.15 readback (image SHA-256 prefix `9a732a2d9d271f2e`; per-block hashes only, no NVRAM content shared).

| Copy | vs official 1.15 |
|---|---|
| A main `0x51D400` (`0x68` inst 0) | identical |
| **A active override `0x522000` (`0x60`)** | **differs** (AOD tokens, §8) |
| A override backup `0x525000` (`0x68` inst 8) | identical |
| B main `0x8E5400` | identical |
| **B active override `0x8EA000`** | **identical, i.e. factory** |
| B override backup `0x8ED000` | identical |

- All PSP/BIOS directory tables and the EFS header are identical.
- Only 11 of 512 blocks (64 KiB each) differ from the official image, and all of them are runtime-data regions:
  - `0xC0000–0xEFFFF`: PSP NV data / PSP NVRAM (fTPM);
  - `0x120000–0x13FFFF`: `APOB_NV_COPY` at `0x125000`;
  - `0x520000`: the active override APCB;
  - `0x1BA0000` (erased in the official image) and `0x1BC0000–0x1BFFFFF`: NVRAM / ROM-Armor NV stores.
- The firmware itself is stock and unmodified.

Consequences:

- The firmware's own write-back touches **only the A-side active override copy**. Both A-side defaults and the A backup are factory, and so is the **entire B side** (a second PSP L2/BIOS L2 directory set at `0x565000` / `0x8E5000`).
- A corrupted A-side override would therefore leave several factory fallbacks: the A backup (used by the "Recoverable" path in §7) and, if the PSP A/B recovery engages, the whole B side. Whether the PSP actually falls back to B on an APCB failure on this board was not verified.
- If the board ever boots from the B side, the AOD timings would silently stop applying, because B holds factory APCB. That is a visible sign of a recovery boot.

Board hardware, from public product photos and the official manual (`M09.04.DRFXI002`, DRFXI V2.0 2023-12-19):

- **Reset Hole** on the rear I/O (manual item 13): with power removed, hold for 10 s to restore BIOS factory defaults, i.e. a CMOS clear. Its effect on the APCB override copy is analysed in §10.
- **CR2032 RTC battery** on a cable, on the back of the board.
- Unpopulated **2×10 footprint labelled `JTG1`** on the back, most likely a debug (JTAG/HDT) header and not an SPI header.
- **SPI flash location is not confirmed.** The strongest front-side candidate is an 8-lead package (~6×9 mm including leads, consistent with a 256 Mbit SOIC-8/WSON-8). It sits between the PCIe x16 slot and the CE/RoHS print, above the upper SO-DIMM slot, directly left of a small FPC connector. The back side shows no package of a suitable size; the larger parts there are a 64-pin QFP (`U3401`), QFNs near the rear I/O, and power MOSFETs. Markings are unreadable at the available resolution, so part number and voltage remain unknown.

## 10. Follow-up: what a CMOS clear does to the active override APCB (2026-11-25)

Static trace in DRFXI 1.15 (ABL core overlay `0x24ADA0`, `AmdPspDxeV2Rpl`, `ApobRplDxe`, `AmdAgesaParameterGroupPei`, `AmdCpmOemInitPeim`, `FchYuntaiPei`). The question: does the Reset Hole (§9, a CMOS clear) drop or ignore the active override copy at `0x522000`, where the AOD tokens and any injected Tref token would live?

**CMOS markers.** ABL keeps a two-byte marker in the upper RTC bank: `CMOS[6..7]`, accessed through IO `0x72/0x73`, which the PSP reaches as `0xFC000072/73` via `svc #0x26/#0x27`. `0xA55A` or `0x5555` means "valid"; anything else, including the state after an RTC/CMOS clear, means "invalid". Writers found:

| Writer | Value | When |
|---|---|---|
| ABL `0xCEC` | `5A A5` | only on a pre-silicon environment (`0x5854(3,0)`) |
| ABL `0xB5C` | `5A A5` | active override is identical to its backup (see step 2) |
| ABL OC-fail `0x289940:0x1900` | `00 00` | "Clear CMOS and load default APCB" (§6/§7) |
| `AmdPspDxeV2Rpl` `0xE4C` | `5A A5` | after a successful APCB restore, before the reset |
| `AmdPspDxeV2Rpl` `0xE4C` | `55 55` | `PcdAmdPspApcbRecoveryEnable` is FALSE ("ignore recovery") |

**Step 1: ABL reads the markers before it loads the APCB** (core `0x3E7A`). `ctx[0x11E] = CmosCheck()` (`0xCEC`, returns 1 for invalid markers).

**Step 2: if the markers are invalid**, and the boot is not an s0i3 resume, ABL compares the active override (`0x60`) with its backup (`0x68`, instance 8) through `0xB5C`. That routine logs "SizeOfApcb is identical" / "Apcb content is identical" and skips the CBS sync token `0xB331378E`.

- If the copies are identical, it writes `5A A5` and clears the flag. A board that never saved AOD/CBS settings just continues.
- If they differ, as on the reporter's board (§8: AOD tokens in `0x522000`), `ctx[0x11E]` stays 1.

The gate is the boot mode from `svc #0x1C` (stored at `[sp+0x14]`). The ABL dispatcher in the same function (`0x3F84`–`0x4010`) branches on it:

| Value | Real silicon | Pre-silicon |
|---|---|---|
| 2 | "S3 Resume" | "S3 Resume on Emulation" |
| 1 | "s0i3 Resume" | "s0i3 Resume on Emulation" |
| other | "Cold or Warm Boot" | "Cold or Warm Boot on Emulation" |

So only on an s0i3 resume is the compare skipped with the flag left at 1. A Reset Hole press removes power, so the next boot is a cold boot and the compare runs.

**Step 3: with the flag set, ABL ignores the active override for this boot.** `0x494(1)` zeroes field `+0xC` of every type-`0x60` entry in the 20-entry BIOS-directory cache (`0x1EDB4`). The APCB entry lookup (`0x6EE`) also redirects a request for type `0x60` instance N to type `0x68` instance N+8.

Memory training therefore runs on the factory override backup. The same flag and path are used by "Recoverable APCB Checksum Error" (postcode `0xE329`, §7). How the flag reaches the APOB is traced byte by byte below ("ABL flag → APOB").

**Step 4: DXE restores the active copy in SPI.** `AmdPspDxeV2Rpl` registers `0xE4C` as an EndOfDxe callback.

1. It reads `PcdAmdPspApcbRecoveryEnable` (dynamic PCD token `0x304`, PEI DB default `0x01` = TRUE).
2. If the PCD is FALSE, it writes `55 55` and exits.
3. If the PCD is TRUE, it asks `ApobRplDxe` for `ApobApcbRecoveryFlag`: APOB group 1, type `0x10`, instance 0, byte `+0x65`. Neighbours in the same entry are `ApcbInstance` at `+0x30` and `DimmCfgUpdatedFlag` at `+0x64`.
4. If the flag is set, it walks the table at `0x7788`:
   - `0x68`/8 → `0x60`/0 (mandatory);
   - `0x68`/9 → `0x60`/1 (optional).
5. For each entry it reads the backup from SPI, writes a new `UniqueApcbInstance` at `+0x0C`, recomputes the checksum at `+0x10`, and writes the result over the active copy in SPI.
6. It logs "Recover Succeed, set CMOS flag, reset system", writes `5A A5`, and resets.

The missing-backup cases are fatal ("Required Backup Apcb ... Not Detected").

**The PCD stays TRUE on retail hardware.** Only two modules write token `0x304`, both with `SetBool(0x304, 0)`:

- `AmdAgesaParameterGroupPei` (`0x2FD`);
- `AmdCpmOemInitPeim` (`0x3F3`).

Both do so only when the low nibble of PSP register `SMN 0x03810A84` is non-zero. In the same register, `FchYuntaiPei` uses bit 9 as "SkipAllUSBControllerAccess" and bit 10 as "SkipAllUSBPhyAccess". `AmdSocFl1RplPei` decodes the low nibble as a platform class (0 → class 0, 1 → 1, otherwise 2+).

Both writers are therefore pre-silicon/emulation switches. On a production board the nibble is 0, the PCD keeps its TRUE default, and the restore handler is armed. No DXE module sets the PCD; the only other `0x304` references, in `AmdCpmDisplayFeatureSmm`, are not PCD calls.

**ABL flag → APOB `ApobApcbRecoveryFlag`, byte by byte.** Overlay addresses below are file offsets. The ABL dispatcher loads each overlay at `0x20000` and enters it at `0x20100` (file offset 0, an ARM wrapper that `blx`-es to the Thumb entry in its literal).

1. **ctx.** In core `0x24ADA0`, fn `0x3CCC` uses `r4 = 0x3A000` as the ABL context and publishes it in the global `0x1E76C` (`0x3D24`). It fills the service table: `+0x50` = `0x1AD61`, `+0x68` = `0x19911` (debug print), `+0x7C` = `0x195CD` (heap allocate), `+0x84` = `0x19885` (heap locate), `+0xD4` = `0x1855D` (APCB bool token get). It writes `ctx+0x11E` at `0x3E80`/`0x3E92` (steps 1–2), before any overlay runs.
2. **Dispatch.** The same function calls each overlay with `r0 = r4 = ctx` (`0x43C0`: `ldr r1,[sp,#0x64]; mov r0,r4; blx r1`, and again at `0x4544`, where `[sp+0x64] = 0x20000 + 0x100`). Both overlays below save that `r0` in their own global as their first action:
   - `0x298D10`: entry literal `0x27209` → file `0x7108`, `str.w r4,[sl]` with `sl = 0x2A7F0`;
   - `0x260950`: entry literal `0x2A195` → file `0xA094`, `str r4,[r5]` with `r5 = 0x2E328`.
3. **Export to heap** (`0x298D10`, "ABL General Environmental Initialization").
   - `0x71A6`–`0x71C8` allocates heap block `0xA03A`, size `0x60`, through `ctx+0x7C`. The descriptor is `{size, id, flag, out}` at `sp+0x360`, so the block pointer comes back at `sp+0x36C`.
   - `0x71EE` loads `r7 = [sp+0x36C]`. `r7` is not written again before `0x728C`.
   - `0x727E`–`0x7288` stores `ctx+0x120` → `[r7+0x58]` (word) and `ctx+0x11E` → `[r7+0x5C]` (byte).
   - Across all 20 ABL overlays of the image (Thumb disassembly) this is the only `strb` to `#0x5C`.
4. **APOB entry build** (`0x260950`, "ABL - General APOB Creation").
   - `0xA148`–`0xA15A` locates heap `0xA03A` through `ctx+0x84` into `r4` and calls `0x354(r4)`. In `0x354`, `r4` stays the heap pointer (`mov r4,r0` at `0x35C`; every later use is `[r4,#0x3C]` = APOB base or `[r4,#0x58/#0x5C]`). The `r4`/`r7` "writes" at `0x74A`–`0x88E` and `0xC90`–`0xDBA` are the overlay's string table (`"\nCreate APOB\n"`, `"\tAdd PMU SMB\n"`, …), not code.
   - At "Add ApobApcbBootInfo" (`0xE4E`), the entry is built on the stack at `sp+0x220`:

| Stack | Entry offset | Value | Source |
|---|---|---|---|
| `sp+0x220` | `+0x00` | 1 | GroupID (`0xEE0`/`0xEE4`) |
| `sp+0x224` | `+0x04` | `0x10` | DataTypeID (`0xEE6`/`0xEE8`) |
| `sp+0x228` | `+0x08` | 0 | InstanceID (`0xEEA`/`0xEF0`) |
| `sp+0x22C` | `+0x0C` | `0x78` | size (`0xEE2`/`0xEF0`) |
| `sp+0x250` | **`+0x30`** | `[r4+0x58]` = `ctx+0x120` | `0xE58`/`0xE5A` → DXE `ApcbInstance` |
| `sp+0x284` | `+0x64` | `r7` | `0xE66` → DXE `DimmCfgUpdatedFlag` |
| `sp+0x285` | **`+0x65`** | `[r4+0x5C]` = `ctx+0x11E` | `0xE7C`/`0xE84` → DXE `ApobApcbRecoveryFlag` |
| `sp+0x286` / `+0x287` | `+0x66` / `+0x67` | APCB bool tokens `0xCBC2C0DD` / `0x22F4299F` | via `ctx+0xD4` |

5. **Copy to the APOB in DRAM.** `0xEF8` calls `0xD068(src = sp+0x220, dst = 0x1430, size = 0x78, base = [r4+0x3C])`.
   - For size > `0x30`, `svc #0xA3` signs bytes `+0x30…+0x77` into `+0x10…+0x2F` ("Sign & Copy APOB Entry to DRAM").
   - It then tail-calls `0xCFE0`. Between `svc #7`/`#8` that routine copies all `0x78` bytes unchanged (8-byte words, then tail bytes) to the APOB DRAM base (global `0x2E960`) + `0x1430`.
   - The header is therefore 0x30 bytes (ID, type, instance, size and a 32-byte signature), and the first data byte is `+0x30`.
6. **DXE read.** `ApobRplDxe` `0x2438` walks the APOB entries from `ApobAddr`, matching `[+0x00] == GroupID` and `[+0x04] == DataTypeID`; `0x2648` then matches `[+0x08] == InstanceID`.
   - `0x15C8` returns byte `+0x65` ("Fail to get ApobApcbRecoveryFlag" on error).
   - `0x162C` returns byte `+0x30` as `ApcbInstance`.
   - `0x16A8` returns `+0x64` as `DimmCfgUpdatedFlag`.
   - The `+0x30` match with ABL's `ctx+0x120` corroborates the layout independently of the flag.

So `ApobApcbRecoveryFlag` is exactly `ctx+0x11E`, the CMOS/compare result of steps 1–2. The handler in step 4 acts on precisely the condition under which ABL booted from the backup.

Caveat: if "Recoverable APCB Checksum Error" sets `ctx+0x11E` only after the `0x298D10` export, the heap copy would be stale. That matters only for the checksum path; the CMOS path sets the flag before the first overlay call.

**Result for the reporter's board** (stock 1.15, AOD timings saved, factory override backup per §9). Statically, a Reset Hole press does the following:

1. **First boot:** ABL sees invalid markers and a differing override, and trains on the factory backup. AOD timings, and any injected Tref token, are **not applied**, even if the stored values would not train.
2. **Same boot, EndOfDxe:** the active override `0x522000` is rewritten in SPI from the factory backup. This erases all AOD tokens and any Tref token. The markers are set to `5A A5` and the system resets once by itself.
3. **Later boots:** markers are valid and the override equals factory. To restore the timings, re-enter them in AOD.

Step 1 does not depend on the bad configuration being bootable. The rest has been traced statically, but nothing was run on hardware.

**Consequences for a Tref experiment.**

- The Reset Hole is a **software-free rollback of any APCB-override change**, including a bad Tref token. It needs no programmer, as long as the override backup (`0x525000`) is intact, which it is factory on this board, and the board reaches EndOfDxe on the factory copy.
- It is also a **destructive** reset of the user's AOD timings, so they must be written down before use.
- It does not cover failures outside the APCB override (a damaged firmware image or backup copy). The training-failure-only limitation of §6 still applies to automatic recovery, but not to this manual path.

## Conclusion

Mechanically, nothing in DRFXI 1.15 blocks writing token `0x419FF338` through the firmware's own `AmdApcbDxeV3` `SetToken16`: the register-permission whitelist is never armed, and the pre-/post-ReadyToBoot paths both accept the write. The ABL then applies it the way `docs/checkpoints/2026-11-24-trefi-abl-path.md` traced.

The blockers are practical and safety-related, not permission-related:

1. **Reachability** — using the DXE protocol and, crucially, triggering `AmdPspWriteBackApcbShadowCopy` from outside the firmware's own save flow is non-trivial and unverified; the SMM route additionally needs the AMD PSP SMM runtime buffer. No injector was written or tested.
2. **CBS purge** — an injected token may be cleared the next time CBS saves settings at the same priority (partially open).
3. **No safe auto-rollback for bad tREFI** — the ABL safety net only catches training failures, not the warm-instability that a too-high tREFI produces. A **manual** rollback does exist (§10): a CMOS clear makes ABL ignore a modified override copy and DXE rewrite it from the factory backup. It also wipes the AOD settings.

Any actual attempt would modify boot-critical configuration and must be preceded by a hardware-level recovery plan (external SPI programmer / confirmed flashback), a conservative first value (e.g. ~2× the ~11677 default, not 65535), and a read-only baseline (ZenTimings) — none of which is in scope here. No flashing or injection is part of this project.

## Open items

- ~~Which priority avoids the Save-time purge (§5)~~: resolved in §8 — priority 2 survives AOD and CBS saves.
- ~~Whether the recovery path permanently restores the active override APCB from its backup (§8)~~: §10. Statically, a CMOS clear with a modified override leads to ABL booting from the backup and DXE rewriting `0x522000` from it, and the ABL flag → APOB `ApobApcbRecoveryFlag` link is traced byte by byte. Hardware confirmation would be: after a Reset Hole press, an extra automatic reset, AOD timings back to Auto, and `0x522000` equal to the official image.
- ~~The `svc #0x1C` gate in front of the CMOS compare~~: it is the boot mode; the compare is skipped only on s0i3 resume (§10, step 2).
- State of the B-side APCB mirrors after firmware write-backs (§8).
- Whether the ABL get-token service treats `0xFFFF` as "absent" (relevant only to the ASRock default-value side, not to a deliberate injection).
- `0xE138`/`0xE139` write-back gating conditions.

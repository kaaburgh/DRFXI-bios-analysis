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
- Whether the "Clear CMOS and load default APCB" / recovery path permanently restores `0x522000` from the backup, or only boots once with defaults, was not established.

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

- **Reset Hole** on the rear I/O (manual item 13): with power removed, hold for 10 s to restore BIOS factory defaults, i.e. a CMOS clear. It is not established whether this also clears the APCB override copy.
- **CR2032 RTC battery** on a cable, on the back of the board.
- Unpopulated **2×10 footprint labelled `JTG1`** on the back, most likely a debug (JTAG/HDT) header and not an SPI header.
- **SPI flash location is not confirmed.** The strongest front-side candidate is an 8-lead package (~6×9 mm including leads, consistent with a 256 Mbit SOIC-8/WSON-8). It sits between the PCIe x16 slot and the CE/RoHS print, above the upper SO-DIMM slot, directly left of a small FPC connector. The back side shows no package of a suitable size; the larger parts there are a 64-pin QFP (`U3401`), QFNs near the rear I/O, and power MOSFETs. Markings are unreadable at the available resolution, so part number and voltage remain unknown.

## Conclusion

Mechanically, nothing in DRFXI 1.15 blocks writing token `0x419FF338` through the firmware's own `AmdApcbDxeV3` `SetToken16`: the register-permission whitelist is never armed, and the pre-/post-ReadyToBoot paths both accept the write. The ABL then applies it the way `docs/checkpoints/2026-11-24-trefi-abl-path.md` traced.

The blockers are practical and safety-related, not permission-related:

1. **Reachability** — using the DXE protocol and, crucially, triggering `AmdPspWriteBackApcbShadowCopy` from outside the firmware's own save flow is non-trivial and unverified; the SMM route additionally needs the AMD PSP SMM runtime buffer. No injector was written or tested.
2. **CBS purge** — an injected token may be cleared the next time CBS saves settings at the same priority (partially open).
3. **No safe auto-rollback for bad tREFI** — the ABL safety net only catches training failures, not the warm-instability that a too-high tREFI produces.

Any actual attempt would modify boot-critical configuration and must be preceded by a hardware-level recovery plan (external SPI programmer / confirmed flashback), a conservative first value (e.g. ~2× the ~11677 default, not 65535), and a read-only baseline (ZenTimings) — none of which is in scope here. No flashing or injection is part of this project.

## Open items

- ~~Which priority avoids the Save-time purge (§5)~~: resolved in §8 — priority 2 survives AOD and CBS saves.
- Whether the recovery path permanently restores the active override APCB from its backup (§8).
- State of the B-side APCB mirrors after firmware write-backs (§8).
- Whether the ABL get-token service treats `0xFFFF` as "absent" (relevant only to the ASRock default-value side, not to a deliberate injection).
- `0xE138`/`0xE139` write-back gating conditions.

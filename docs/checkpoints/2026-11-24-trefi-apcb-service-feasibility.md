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

## Conclusion

Mechanically, nothing in DRFXI 1.15 blocks writing token `0x419FF338` through the firmware's own `AmdApcbDxeV3` `SetToken16`: the register-permission whitelist is never armed, and the pre-/post-ReadyToBoot paths both accept the write. The ABL then applies it the way `docs/checkpoints/2026-11-24-trefi-abl-path.md` traced.

The blockers are practical and safety-related, not permission-related:

1. **Reachability** — using the DXE protocol and, crucially, triggering `AmdPspWriteBackApcbShadowCopy` from outside the firmware's own save flow is non-trivial and unverified; the SMM route additionally needs the AMD PSP SMM runtime buffer. No injector was written or tested.
2. **CBS purge** — an injected token may be cleared the next time CBS saves settings at the same priority (partially open).
3. **No safe auto-rollback for bad tREFI** — the ABL safety net only catches training failures, not the warm-instability that a too-high tREFI produces.

Any actual attempt would modify boot-critical configuration and must be preceded by a hardware-level recovery plan (external SPI programmer / confirmed flashback), a conservative first value (e.g. ~2× the ~11677 default, not 65535), and a read-only baseline (ZenTimings) — none of which is in scope here. No flashing or injection is part of this project.

## Open items

- Which CBS priority the injected token should use to avoid the Save-time purge (§5).
- Whether the ABL get-token service treats `0xFFFF` as "absent" (relevant only to the ASRock default-value side, not to a deliberate injection).
- `0xE138`/`0xE139` write-back gating conditions.

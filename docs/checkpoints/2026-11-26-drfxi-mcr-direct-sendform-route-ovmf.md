# DRFXI 1.15: direct MCR navigation and original RouteConfig execution in OVMF

2026-11-26. Follow-up to [runtime checkpoint](2026-11-26-drfxi-115-mcr-hii-runtime.md) and [OVMF HiiProbe checkpoint](2026-11-26-drfxi-hii-probe-ovmf.md). Scope: autonomous offline experiments, no physical-board operations, no protection opening or real AMD variable/flash writes.

## Inputs and reproduction boundaries

Re-extracted exact stock DRFXI 1.15 from the acquisition ZIP, official-1.15-aliyun 7z, outer LZMA FFS and CBS PE32. SHA256: firmware 3afaba6d916b3897d1d98bd5913008b38e89b6c51b2c6963c7109793541d8d88; CbsSetupDxeRPL PE (171808 bytes, FFS 2848A12F-3F86-47C7-81D8-D3FD47B205B2) 0aafafee9e5f51d72b978a8268499c6aacbc9e3a612d22e3b4943c0021212084; package list at PE+0x8760, size 0x21789, hash 58d1d2dfaf5920edcf0e77225b62307b80edc28c739a77a398cda6300489f92a. Forms CRC32 7897C39A. QEMU 10.0.13 / OVMF 2025.02-8+deb13u1, TCG, disposable FAT and VARS per run, no network. Bundle archive SHA256 037b64ab4e77e5779dc5d6cfdafa4a09babab0a39cfd10bb14d3d6e3eddc9d9c. No private AFU or owner CBS payload used. Synthetic buffers initialized with stock defaults, with artificial timing override for selected tests.

A separate owner observation was committed during this work: [755c485](https://github.com/kaaburgh/DRFXI-bios-analysis/commit/755c4859ad6c93c4fc49140bd77236f074821830). Physical BD790i HiiProbe showed unique owner and ConfigAccess, form mask F, refs7, MCR1, stock length and CRC, unchanged gate and CBS at endpoints. This is actual hardware evidence of runtime publication, not actual SendForm/RouteConfig execution. Photo truncated initial status lines. No new hardware action taken in this session.

## 1. Direct FormBrowser2.SendForm, stock package, synthetic ExtractConfig

Registered the unmodified HII package list on a new OVMF handle with exact CBS vendor device path and synthetic ConfigAccess. Real HII Database, routing and SetupBrowser. Synthetic CBS selector 0x43 or 0xFF; MCR FF. Requested FormSet C03209ED-5F4B-4631-BD03-8ED627CD9DAF explicitly.

- root43: SendForm(7000) shows CPU/NBIO/FCH/SMU Common Options; no UMC. Reproduces physical observation.
- rootff: SendForm(7000) additionally shows DF, UMC and SOC Miscellaneous Control; Combo CBS control visible. No change to real selector.
- direct: SendForm(701B) with selector 43 shows DDR Memory Features and Memory Context Restore <Auto>, all stock options Auto/Enabled/Disabled. No IFR or HII patch. Esc returns EFI_SUCCESS, Action 0, one ExtractConfig, zero RouteConfig, zero callback, unchanged synthetic MCR FF.
- save: select Enabled, F10, Y, Esc. Exactly one RouteConfig with 18753 UTF-16 characters and 574 OFFSET ranges, ConfigToBlock output size 0x2D7; only changed byte 0x263 FF->1. 21 callbacks, action request 1 (RESET). This fixture commits only to synthetic RAM.
- discard: select Enabled, Esc, N. No RouteConfig, Action0, MCR FF.

This is a positive direct-navigation test, not just an API inference. Ancestor Ref suppression is not inherited by the terminal form. Runtime physical publication and emulated browser behavior together strongly support the approach. The actual zedk/AMI browser on BD790i has not yet been invoked with an explicit FormId; physical compatibility and side effects not proven.

## 2. Execute exact position-independent stock routines with mock APCB

Used the reviewed bytes, not a reimplementation. Linked into an EFI test app as .text slices; original DXE entry point never executed. All calls in sync routine are indirect calls to local mock APCB vtable, no real APCB/RT or flash access.

| Routine | PE/RVA range (exclusive end) | SHA256 |
|---|---|---|
| defaults | 3E58..45C3 | 94553d7761d003d8ce34891656b8dd70b1e15c870b626e98fe3eb7fdf6786147 |
| CBS->APCB | 45C4..5131 | 12181b63b220acde636295e511c83f3a632fde17722db54e346c7f12b7b414e5 |
| fingerprint | 5134..5EDF | 71c6b2564a5d111852ba9b05e31763c3d1d70cba3ddc693972c27d2fc0418d1f |

Stock defaults produce FF MCR, correct size/version words. Synthetic selector43 and timing override (offset 116/119 flags, 11A..11B data) used in all tests; no actual owner timings. Auto: five token setter calls including existing fingerprint, zero MCR calls. Disabled and Enabled: six calls, exactly one added Boolean MCR setter (token FEDB01F8, priority argument3, values 0/1); all other typed token records identical, all CBS input bytes unchanged by transfer. Acquire +60, clear priority +C0, Boolean +78, byte +88, word +98, dword +A8, writeback +08, release +68. Names denote recovered roles, not ABI source names. Three computed synthetic fingerprints distinct; transfer sends stored CBS+8, not freshly computed fingerprint.

Fault injection into original sync: acquire failure returns EFI_DEVICE_ERROR and no token/flush/release call. Injected clear failure, MCR setter failure, writeback failure or release failure are ignored: original sync returns EFI_SUCCESS, proceeds through calls. No real storage state modeled by these failures. This directly confirms incomplete error propagation.

## 3. Execute exact stock RouteConfig and startup code

In OVMF only, copied verified PE to temporary EfiLoaderCode memory (file offsets equal RVAs in reviewed image, one DIR64 relocation at 7108), patched only *private copied* image globals 7F70/7F78 to mock BS/RT tables, used real OVMF ConfigToBlock via local routing vtable. No global UEFI table or live firmware code modified. No driver entry. Fake private ConfigAccess context reproduces relative pointer fields This-20 (CBS buffer) and This-8 (routing). Mock SetVariable checks exact name/GUID/attributes7/size6D5 and writes local saved array. Mock GetVariable counted separately. APCB locate and methods mocked. Exact code at RVA B58, 3C3C, 3E58, 5134, 45C4 and original header helpers.

Single-field synthetic ConfigResp (MCR Disabled):
- fresh cached CBS: EFI_SUCCESS, one full 1749-byte SetVariable (mock), zero GetVariable, one APCB locate, six token calls including MCR0, one writeback, one release; only offset263 changed; saved fingerprint unchanged.
- stale cached CBS with one unrelated synthetic timing byte differing from saved variable at offset11A: EFI_SUCCESS; both 11A and 263 changed in saved payload. The original RouteConfig does not reload storage before merging the incoming response. Never assume a one-field ConfigResp is an isolated one-byte persistent update.
- invalid GUID: EFI_NOT_FOUND, no variable/APCB calls.
- mock SetVariable EFI_WRITE_PROTECTED: error propagated, no APCB calls.
- missing APCB, failed acquire, failed MCR setter, failed writeback: outer RouteConfig EFI_SUCCESS after successful mock SetVariable. Earlier static inference confirmed by machine-code execution.

Startup check: after normal synthetic route, recomputed fingerprint differs from saved CBS+8, but the stored APCB fingerprint equals saved CBS+8. Calling original 3C3C skips sync and leaves buffer unchanged (0 token calls). Perturbing only mock APCB fingerprint triggers six token calls, one writeback and replaces CBS+8 with freshly computed hash. Thus matching *stored* values do not prove recomputed hash or repair of lost token writes. Do not use this experiment to infer exact persistence failure states of real APCB implementation.

## 4. Integrated end-to-end browser + original RouteConfig

Registered stock package and exact vendor path, synthetic ExtractConfig loads full mock saved CBS into private driver cache; actual OVMF routing dispatches browser response to a wrapper that invokes original RouteConfig machine code. 21 callbacks all SUBMITTED (action5), none for MCR Q9B; original C60 callback invoked only on its reviewed immediate-success SUBMITTED branch, all other actions would be rejected. Two cases: no error, and simulated APCB Writeback returns EFI_DEVICE_ERROR. Selected Disabled from Auto via real Browser; F10/Y/Esc. Both produce exactly same visible success, one Extract, one Route, one mock SetVariable, zero GetVariable in Route, one MCR setter 0, one Writeback attempt, Action1, only saved byte263 changed, fingerprint unchanged. Both explicitly reach INTEGRATED FIXTURE PASS; real APCB persistence not measured. Failure hidden from browser despite normal UI path. Initial integrated tests completed all core assertions but failed cleanup (combined UninstallMultipleProtocolInterfaces -> EFI_INVALID_PARAMETER). Fixed by removing ConfigAccess and DevicePath separately after verifying the exact interface pointers; reran both cases, successful Remove, both Uninstall calls, FreePages, PASS. This is a fixture issue, not a BD790i firmware defect.

## 5. Automatic suite and reproduction

9 cases PASS, split into 3 groups because a single long terminal invocation was interrupted by execution limits. Group browse: root43, rootff, direct, save, discard. Group code: sync, route. Group integrated: integrated0, integrated4. Source-only evidence ZIP delivered in chat: drfxi-mcr-ovmf-research.zip (49463 bytes, SHA256 31bd6790e60d24a6149b3501d8f49515c43c7d47e2b5cf11330829215457692c). Contains source, per-case serial logs, three OVMF screenshots and result JSONs, not stock PE, firmware, generated EFI, VARS, or private user settings. Archive source blobs (git hashes): sendform_fixture.c 52d0248b4c534353fbcd4952cab08f5baededf57; sync_fixture.c e283c8600c677fd2a4c24d43d60bac858376fb12; sync_code.S 21a3929cf435d93541a8094caaf21d1b19d3d9c6; route_fixture.c c3badf0c060cc23d73413d2590ace4df4422d737; route_code.S 30df023a6454996cfb0a70ff88e330370cd34724; integrated_fixture.c 58694de44b8dacbaeb0ba549a4c2657e2bb160ac; run_ovmf_research.py 025140df7190000360c6fb61a4aaa3cef163ba7d; extract_stock.py 147d9329c2f2d3a6a4a45469f25cbb629575df50. HiiProbe source existing be083cd3d6d4b2717b8d86914ad2da6c54040334.

Build/test commands: Python3 extract_stock.py ACQUISITION_ZIP OUTPUT_PE, then python3 run_ovmf_research.py --pe OUTPUT_PE --qemu UNPACKED_BUNDLE --group browse|code|integrated --out NEW_DIR. libarchive, clang, lld-link, QEMU bundle required. Source verifies exact PE and extracted packages/slices with hashes; all EFI artifacts VM-only and built in temporary dir.

## 6. Decision and remaining blockers

No RAM patch or global suppression change needed to expose MCR, on the observed browser architecture. Do not alter Combo CBS, AMITSE or AMD Variable Protection. Direct SendForm loads config via global routing even with no edits: one ExtractConfig confirmed. Physical AmdVariableProtection hooks that function and may remove runtime gate during late Shell. Thus direct SendForm is not strictly read-only on actual board even when user presses Esc. OVMF tests do not emulate that hook, the actual CBS ExtractConfig (selector/PCD computation), actual APCB implementation, SPI persistence, or memory training. No hardware-capable write/launcher EFI provided or executed. No evidence that a late Shell write is safe while runtime protection stays active. Need separate owner approval before intentionally invoking the normal configuration window or saving. A passive read-only viewer can avoid the hook but cannot perform a real setup edit. Next priorities: independently recover actual APCB priority/board/instance resolution and verify what read-only evidence is available for effective MCR; design a separately approved controlled direct-open (no Save) with gate and full CBS checks, ideally with controlled reboot recovery. Do not infer policy change from EFI_SUCCESS, stored fingerprint equality, or virtual mock storage.

# DRFXI 1.15 -> 1.17: DDR5 tuning regression, read-only static narrowing

Date: 2026-11-14

Scope: investigate the September 2026 report of a BD790i user whose previously stable tuned DDR5 settings became unstable after upgrading to DRFXI 1.17. No hardware access or flashing. This report concerns a BD790i owner; applicability to BD790i X3D must not be assumed.

## Baseline and provenance

Official, locally unpacked `DRFXI.BIN` images, SHA-256:
- 1.15: `3afaba6d916b3897d1d98bd5913008b38e89b6c51b2c6963c7109793541d8d88`
- 1.17: `99f3bab5ea491202bf365c23e6416f9d1e8a649ad00f90c1f3e21f1a61e35c51`

Additional officially acquired 1.04/1.07/1.12 binaries were checked for APCB ID precedent. UEFIExtract NE A75 was used for decompressed PE/TE leaf inspection. No board runtime measurements exist.

User report: https://www.reddit.com/r/MINISFORUM/comments/1wg7tb0/bd790i_bios_117_update_broke_memory_timings_dont/ (2026-09-14): after upgrade, the prior manual profile failed; the reporter observed much looser automatic timings (including ~tRFC 968), later retuned with tighter limits than before. This is an anecdotal single-system result, not an established firmware-wide regression. Reports about the non-X3D BD790i are not automatically proved for X3D.

## 1. AMD/PSP region diff and APCB

**Direct binary evidence:** the first 0x1000000 (16 MiB) of the 1.15 and 1.17 images differs in *exactly 18 bytes* across six APCB headers; no other bytes change there. The six structural APCB bases are:

- primary: `0x51D400`, `0x522000`, `0x525000`
- mirrored: `0x8E5400`, `0x8EA000`, `0x8ED000`

Each header has `UniqueApcbID` at base + `0x0C` and checksum at base + `0x10`. Values change in both mirrors:
- main APCB `UniqueApcbID: 0x000069FF -> 0x00004E98`, checksum `0x0E -> 0x90`;
- secondary small APCB blocks `0x00006A06 -> 0x00004E9F`, checksum `0x0C -> 0x8F`.

All other bytes, including APCB payload/configuration records in that 16 MiB region, are unchanged.

**New negative control:** earlier official images also rotate APCB IDs:

| BIOS | Main APCB ID | Small APCB ID |
|---|---:|---:|
| 1.04 | 0x09CC | 0x09CF |
| 1.07 | 0x5BBC | 0x5BC3 |
| 1.12 | 0x272F | 0x2732 |
| 1.15 | 0x69FF | 0x6A06 |
| 1.17 | 0x4E98 | 0x4E9F |

Critically, 1.07 -> 1.12 changed IDs while the *APCB payload hashes remained identical*. Therefore ID rotation is not unique to 1.17 and is not sufficient evidence for a regression. The narrower question is whether an ID change affects an update-time retention/fallback/cache decision; **not proven**.

The APCB v3 header layout/ID role is described in https://ptswarm.com/blog/slowburn-looking-through-amd-platform-configuration-blobs-infrastructure/.

## 2. Memory-relevant executable code

Compared extracted PE/TE bodies, not compressed-container bytes.

**Byte-identical 1.15 -> 1.17 PEI/related images:**
- `AmdMemFl1Pei`
- `AmdSocFl1RplPei`
- `AmdAgesaParameterGroupPei`
- `AmdMemRestorePei`
- `AmdMemoryHobInfoPeimRpl`
- `AodPei`
- `PcdPeim` PE body
- `AmdMemRestoreDxe`
- `AmdVariableProtection`

**Only PCD-token immediate renumbering, with otherwise identical bodies:**
- `AmdApcbDxeV3`: 11 bytes (e.g. `0x48D -> 0x490`), same executable code/branch structure;
- `AmdApcbSmmV3`: 11 bytes;
- `AodDxe`: 11 bytes;
- `AodSmm`: 5 bytes;
- `CbsSetupDxeRPL`: 5 bytes;
- `AmdMemRestoreDxeV2`: 3 bytes;
- `AmdPbsSetupDxe`: 9 bytes.

These are decoded at immediate operands of `Get8/Get16/Get32` PCD calls; no changes to their algorithms were found in this normalized comparison. Prior project HII/IFR investigation independently establishes unchanged `CbsSetupDxeRPL` memory controls.

**Consequence:** there is no evidence in these images of changed DDR timing selection/training algorithms, but their unchanged code can still produce different runtime values when inputs or saved state differ.

## 3. Genuine new SmuV13Dxe consumer: STABILITY_BOOST

`SmuV13Dxe` is *not* merely a PCD-renumbering-only module. Code-level diff between 1.15 (PE image 48096 bytes) and 1.17 (48128 bytes) finds newly inserted instructions at ~`0x27E4` and a new diagnostic line at ~`0x4F23` (PE virtual addresses).

1.17 newly:
- calls the PCD protocol getter for token `0x496` (instruction `mov ecx,0x496; call [rax+0x08]`);
- stores returned byte to `[rbx+0x4DF]` of the configuration structure;
- prints `STABILITY_BOOST = %d` from that field, followed by the existing `Sending this to the SMU...` diagnostic.

This is a real executable behavior addition rather than only layout churn. It occurs in DXE, after initial DDR training; there is **no proof** that it changes UMC timings, training parameters or effective VDD/VSOC.

The UEFI `PcdDxe` raw PCD database grows 2824 -> 2840 bytes and `LocalTokenCount` 357 -> 361; `PcdPeim` raw database remains 5704 bytes, with `LocalTokenCount=966`. Under the EDK2 global-token-to-DXE-local mapping, `0x496 - 966 = 208`, so DXE local index 207 holds `0x01000C70`: UINT8 DATA type, offset `0xC70`. This is beyond the initialized DXE DB length `0xB18` but within DB+uninitialized area (`0xB18+0x1C8 = 0xCE0`), hence initialized to zero unless changed elsewhere. No static non-SMU `mov ecx,0x496` consumer was established in the scanned modules, but a computed/dynamic setter has not been exhaustively excluded.

PCD structural/source reference: https://github.com/tianocore/edk2/blob/master/MdeModulePkg/Include/Guid/PcdDataBaseSignatureGuid.h.

**Priority for memory regression:** low pending a discovered nonzero runtime value or connection to memory voltage/power.

## 4. New OemDxe writes the same AMD setup variable

Already identified in `docs/findings/graphics-autodetect.md`; additionally checked in the 1.17 executable:

- `GetVariable(AmdSetupRPL)` with buffer size `0x6D5`; failure checked before updating it;
- conditionally changes only byte at offset `0x44` (iGPU Configuration) in the obtained buffer;
- `SetVariable` with attributes `0x7` and the `0x6D5` buffer, then reset on transition.

The newly introduced path performs a full-variable write but the static code does **not** blindly recreate the rest of the AMD setup payload. A loss of unrelated timing fields is therefore not established by this function. Possible interaction with `AmdVariableProtection` or update-time variable state remains an unverified low-priority branch.

## 5. Defaults and flashing package

The decompressed `NVRAM external defaults / StdDefaults / AmdSetupRPL` entry is *byte-identical*, length 1749, SHA-256:

`e4c97468779e948fc9df86fe43a613bbc4ece4b32b0c9f85a5fc86d16fbacc51`.

Most other stock external default entries (including ROM_CMN and AMITSESetup) match as well. The aggregate StdDefaults store and GUID-store structure differ due to other additions; those differences are not direct evidence of changed AMD memory defaults.

The 1.15 and 1.17 official packages contain **byte-identical**:
- `AFUWINx64.EXE`, `AfuEfix64.efi`, `amigendrv64.sys`;
- `WinFlash.bat` and `EfiFlash.nsh`.

Both use the identical command flags:

`/p /b /n /k /r /l /RLC:E /reboot`

The AMI AFU guide describes `/N` as programming NVRAM and `/RLC:E` as selecting the Entire BIOS region option for ROM-layout-change handling. This does **not** establish whether all settings were erased or preserved: actual preservation is platform and AFU-flow dependent. Do not infer that `/SP` absence alone means nothing was preserved.

Source for documented option meanings: https://www.scribd.com/document/831336124/AMI-Aptio-5-x-AFU-User-Guide-PUB .

Separately, firmware-side `ReFlash`, `FlashDriver` and `FlashDriverSmm` changed materially (see `docs/findings/flash-eip-and-tcg.md`). Their relationship to the unchanged external AFU workflow is **not proven**; do not assume those internal modules were invoked by AFU.

## Updated hypothesis ordering (NOT root-cause proof)

1. **Flash-time NVRAM/configuration migration or selection, plus state persisted from previous firmware**. A viable explanation of different effective Auto values with identical static defaults. High information gain if a concrete flash/variable path can be isolated; not confirmed.
2. **APOB / saved training / Memory Context Restore lifecycle**. Runtime state can affect behavior without binary changes. A direct firmware-specific causal path has not been demonstrated.
3. **Hidden dynamic PCD inputs or DXE dispatch/initialization order**. The PCD roster grew and new DXE code exists, but most memory-relevant binaries are identical; investigate only a concrete variable/consumer.
4. **New `SmuV13Dxe` STABILITY_BOOST handling**. Real delta, likely zero by default, post-training; presently low probability for the large Auto-timing shift.
5. **New `OemDxe` graphics-variable write**. Real 1.17 action against the shared `AmdSetupRPL` variable; only offset `0x44` is deliberately mutated, so a memory-timing side effect is unproven.
6. **Changed underlying DDR training algorithm or embedded PMU firmware**. The matching first 16 MiB and matching main memory PEI modules argue strongly against this in the *available static images*. Do not claim impossible without runtime measurements.

## Limits / next bounded paths

- The Reddit case is only one affected system, and may not generalize to BD790i X3D.
- Missing 1.16 prevents release-by-release attribution of 1.15 -> 1.17 deltas.
- Neither a firmware dump of the affected machine nor runtime timings / NVRAM variables / training logs are available.
- A complete causal proof is impossible from two factory distribution binaries alone.
- If continuing without hardware, prioritize a narrowly scoped audit of AFU `/N` preservation and explicit config rehydration, with strong public-source or instruction-level anchors. Avoid a generic diff of thousands of firmware modules.
- No flashing, patching, or writing of AMD setup variables is part of this investigation.

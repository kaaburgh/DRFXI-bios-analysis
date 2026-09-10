# TCC / SMU power-limit investigation

Last updated: 2026-09-10

Relevant 1.15 changelog items:

```text
Set TCC to 100
Update SMU for power limit
```

Scope of this finding is intentionally limited to thermal/power configuration and SMU firmware. S3, BDS/LAN and TCG changes are outside scope.

## Summary

The strongest positive result is that 1.15 contains a **materially different AMD SMU function-firmware image** in the PSP directory. By contrast, the obvious host-side setup/default/APCB paths do not contain a corresponding TCC/PPT default change.

Current attribution:

- `Update SMU for power limit`: **high confidence match** to replacement of `PSP_SMU_FN_FIRMWARE~0x108`; exact internal SMU routine/table responsible for the power-limit behavior is not yet localized.
- `Set TCC to 100`: **still unresolved**. HII/default NVRAM, APCB and the obvious host-side SMU/AGESA wrappers have been substantially narrowed or excluded. The early PEI PCD database is the strongest remaining static-config candidate.

## HII and default setup data: negative result

`CbsSetupDxeRPL` is semantically unchanged between 1.12 and 1.15.

The `AmdSetupRPL` VarStore remains:

```text
GUID: 3A997502-647A-4C82-998E-52EF9486A247
Size: 0x6D5
```

Relevant offsets remain stable, including:

```text
0x064  Sustained Power Limit control
0x065  TDP
0x069  PPT Control
~0x06A Thermal Control
0x06B  TjMax
0x1B4  PPT
0x29A  STT_MIN_POWER_LIMIT
0x2B8  APU-only sPPT
0x2BC  Sustained PowerLimit
0x2C0  Fast PPT
0x2C4  Slow PPT
0x2D4  second PPT Control
```

The externally stored default `AmdSetupRPL/body.bin` is **byte-identical** between 1.12 and 1.15:

```text
SHA-256 e4c97468779e948fc9df86fe43a613bbc4ece4b32b0c9f85a5fc86d16fbacc51
```

Relevant defaults are unchanged and remain Auto/zero (`TjMax = 0`, PPT/TDP limits = 0; the second PPT control remains `0xFF`).

Therefore `Set TCC to 100` is **not** implemented by changing the visible CBS `TjMax` default or the persisted/default `AmdSetupRPL` variable.

Important terminology boundary: the changelog word `TCC` should not be silently equated with the user-facing CBS `TjMax` question. They may converge on related SMU thermal behavior, but the setup default itself did not change.

## APCB: strong negative result

Six matching APCB v3 blocks were compared, including the main/mirrored blocks at:

```text
0x51D400
0x522000
0x525000
0x8E5400
0x8EA000
0x8ED000
```

The main APCB retains the same group layout (`PSPG`, `MEMG`, `GNBG`, `FCHG`, `TOKN`). Non-token payloads are byte-identical.

The main token area contains 162 records. Only **one semantic token value** changes:

```text
UID:   0x7A4FA9ED
Type:  uint32
1.12:  0xF0000000
1.15:  0xE0000000
```

The same transition is visible elsewhere as a platform-wide PCI ECAM-base migration and is not a plausible TCC/power-limit setting. The two smaller APCB token blocks do not contain changed semantic token values.

No APCB change was found that explains either target changelog item.

## Positive result: actual SMU firmware was replaced

The AMD PSP level-2 directory contains a composite type `0x00000108` entry identified by PSPTool nomenclature as:

```text
PSP_SMU_FN_FIRMWARE~0x108
```

The entry starts at the same ROM location, `0x1C9600`, in both images, but the signed/compressed container and its decompressed payload are different.

### 1.12

```text
container size: 137,840 bytes (0x21A70)
container SHA-256:
8b12cce4d120b06698250ba587f185b452d513a8c99c31fb4885cb0ad90d897c

header bytes @0x60..0x63:
00 68 54 00

PSPTool HeaderFile-style decoded version field:
0.54.68.0
```

### 1.15

```text
container size: 138,304 bytes (0x21C40)
container SHA-256:
f2b07c1f912bda4d18b2dd126606f4c155c57e6d40e00ee9d626b4d1e2b4d129

header bytes @0x60..0x63:
32 6C 54 00

PSPTool HeaderFile-style decoded version field:
0.54.6C.32
```

The container has `$PS1` at offset `0x10`. Its payload beginning at `0x100` decompresses as zlib to exactly 262,144 bytes in both versions.

Decompressed images:

```text
1.12 SHA-256:
1a00faf2f497846bd0415c544510f212ea12d4f0753a7b19da24c098b25c8f6b

1.15 SHA-256:
fd45717e18d448bd0a72779b317123e24e90bf2d1b57b528033bdc9f93bc72ef

Differing bytes: 169,544 / 262,144 = 64.6759%
Identical 4 KiB blocks: 8 / 64
```

The version bytes are also repeated at the beginning of the decompressed payload.

This is a real SMU firmware replacement, not signature/header churn around an unchanged image.

### Changelog attribution

This is currently the strongest direct binary match for:

```text
Update SMU for power limit
```

It establishes that the SMU function firmware really changed in 1.15. It does **not** yet identify which internal SMU routine/table motivated the phrase `for power limit`.

## Host-side SMU wrappers: no new pathway

`SmuV13Dxe` contains the same thermal/power-related pathways in both releases, including:

```text
BIOSSMC_MSG_SetTjMax
BIOSSMC_MSG_SetPPTLimit
BIOSSMC_MSG_SetSlowPPTLimit
BIOSSMC_MSG_SetSustainedPowerLimit
BIOSSMC_MSG_SetSlowPPTLimitApuOnly
STT_MIN_POWER_LIMIT
```

The module retains the same size. Only 163 raw bytes differ and the dominant pattern is PCD-token renumbering plus the unrelated platform-wide ECAM-base change.

A literal search for decimal 100 (`0x64`) does not reveal a newly introduced command/value; observed `0x64` operands are unchanged structure displacements.

`SmuV13Pei` has the same overall result after TE/relocation normalization.

Therefore 1.12 already had the host-side SetTjMax/PPT message mechanisms; 1.15 did not simply add a new message path here.

## AGESA/config host initializers

`AmdAgesaParameterGroupPei` was converted from TE to PE for comparison.

- `.data`: 5,616 bytes and byte-identical between 1.12 and 1.15.
- `.text`: grows by only 18 bytes, primarily a small structure-layout/initialization extension plus the platform-wide ECAM-base change.
- no new immediate decimal `100` was localized.

`CpuSetAgesaPcd` changes only weakly (21 raw bytes in 11 small regions, dominated by address/PCD shifts) and likewise does not introduce an obvious TCC=100 assignment.

## Remaining PCD candidate

The early PEI `PcdPeim` carries a RAW PCD database that changes structurally:

```text
1.12
size:   5,696
SHA256: 8d68393cb1388c3c936a24116883c0f8991f22696fc5e6d06980e096fd97668c

1.15
size:   5,704
SHA256: e4847fe7ead968ced7c2842bd2e20934c3220765d53a606b35bca85ce94a8435
```

A naive diff is noisy because token/index layout changed between builds. This database still needs a format-aware EDK II PCD decode so scalar values can be compared independent of token renumbering.

This is currently the strongest remaining static-config candidate for `Set TCC to 100`.

## Confidence / hypotheses

**Confirmed:**

- AmdSetupRPL HII/default data is unchanged.
- APCB has no relevant thermal/power semantic change.
- host-side SmuV13Dxe/Pei already contain SetTjMax/PPT pathways in 1.12 and do not gain an obvious new power algorithm in 1.15.
- AmdAgesaParameterGroupPei static data is unchanged and no TCC=100 assignment was localized there.
- `PSP_SMU_FN_FIRMWARE~0x108` is materially replaced; its embedded version field changes from `0.54.68.0` to `0.54.6C.32` and 64.68% of the decompressed 256 KiB payload differs.

**High-confidence hypothesis:** `Update SMU for power limit` refers primarily to this SMU firmware replacement.

**Unresolved:** `Set TCC to 100`. Strongest candidates are a changed platform PCD/default consumed by an existing pathway, an internal AGESA/SMU config value, or a default/behavior inside the updated SMU firmware itself.

## Next bounded step

Decode only the early PEI `PcdPeim` RAW database using the EDK II PCD database format and produce a semantic token/value diff for 1.12→1.15.

The goal is to normalize token renumbering and decide whether a changed scalar value maps to decimal 100 / thermal/TCC semantics. If the PCD database is negative, the next separate branch should identify the architecture/tables of the decompressed `PSP_SMU_FN_FIRMWARE~0x108` payload and perform a semantic SMU-firmware diff.

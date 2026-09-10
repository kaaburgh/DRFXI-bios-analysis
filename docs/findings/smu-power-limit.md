# TCC / SMU power-limit investigation

Last updated: 2026-09-10

Relevant 1.15 changelog items:

```text
Set TCC to 100
Update SMU for power limit
```

Scope is intentionally limited to thermal/power configuration and SMU firmware. S3, BDS/LAN and TCG changes are outside scope.

## Summary

Both target changelog items now have strong binary-level anchors:

- `Set TCC to 100`: **high-confidence value-level localization** in the early PEI `PcdPeim` database. Exactly one pre-existing scalar Dynamic PCD changes, from `91` to `100`.
- `Update SMU for power limit`: **high-confidence match** to replacement of `PSP_SMU_FN_FIRMWARE~0x108`; the exact internal SMU routine/table responsible for the power-limit behavior is not yet localized.

The TCC finding explains why no corresponding change appeared in the user-facing CBS `TjMax` default: the vendor changed a separate platform Dynamic PCD.

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

The externally stored default `AmdSetupRPL/body.bin` is byte-identical between 1.12 and 1.15:

```text
SHA-256 e4c97468779e948fc9df86fe43a613bbc4ece4b32b0c9f85a5fc86d16fbacc51
```

Relevant defaults remain Auto/zero (`TjMax = 0`, PPT/TDP limits = 0; second PPT control `0xFF`). Therefore `Set TCC to 100` is not implemented by changing the visible CBS `TjMax` default.

## APCB: strong negative result

Six matching APCB v3 blocks were compared at:

```text
0x51D400
0x522000
0x525000
0x8E5400
0x8EA000
0x8ED000
```

The main APCB retains the same `PSPG`, `MEMG`, `GNBG`, `FCHG`, `TOKN` layout. Non-token payloads are byte-identical.

Among 162 main token records, only one semantic value changes:

```text
UID:   0x7A4FA9ED
Type:  uint32
1.12:  0xF0000000
1.15:  0xE0000000
```

This is the platform-wide PCI ECAM-base migration seen elsewhere and is unrelated to TCC/power-limit configuration. The two smaller APCB token blocks contain no changed semantic values.

## `PcdPeim`: TCC value localized

The early PEI `PcdPeim` carries an external EDK II BuildVersion-7 PCD database.

```text
1.12
size:   5696
SHA256: 8d68393cb1388c3c936a24116883c0f8991f22696fc5e6d06980e096fd97668c
LocalTokenCount: 963

1.15
size:   5704
SHA256: e4847fe7ead968ced7c2842bd2e20934c3220765d53a606b35bca85ce94a8435
LocalTokenCount: 966
```

Both have `ExTokenCount = 40`, `GuidTableCount = 5` and `PcdNameTableOffset = 0`.

### Token-renumbering normalization

Only the BOOLEAN DATA-token count changes: +3. Counts of UINT8, UINT16, UINT32, UINT64 and STRING tokens remain unchanged.

All 40 DynamicEx semantic keys `(TokenSpaceGuid, ExTokenNumber)` are identical in both databases and every one of their local token numbers shifts by exactly `+3`. This independently demonstrates that three ordinary Dynamic tokens were inserted before the DynamicEx tail.

A value-aware sequence alignment excluding local token numbers and physical offsets gives:

```text
equal existing token records: 962
inserted records:               3
deleted records:                0
same-category scalar changes:   1
```

The three new entries are ordinary BOOLEAN DATA PCDs: one initialized to 1 and two zero-initialized in the UnInit database area.

### The only changed pre-existing scalar

```text
1.12 local token: 209
1.15 local token: 212

descriptor in both images:
0x0400009C

PCD type:    DATA
datum type:  UINT32
data offset: 0x9C

raw bytes:
1.12: 5B 00 00 00 -> 91
1.15: 64 00 00 00 -> 100
```

The descriptor occurs exactly once in each database and the physical value offset remains `0x9C`; the local-token-number change is explained by the three inserted tokens.

**Assessment: high confidence that this Dynamic UINT32 PCD is the static change described by `Set TCC to 100`.** There is no other aligned scalar default change to 100.

The remaining limitation is symbolic naming: `PcdNameTableOffset == 0`, so the source-level PCD CName is not present in the RAW database. The next step is to trace consumers of local token 209/212.

Evidence: `evidence/pcd/tcc-default-change.txt`  
Machine-readable diff: `data/pcd-db-1.12-to-1.15-diff.json`  
Checkpoint: `docs/checkpoints/2026-09-10-pcd-tcc.md`

### Interpretation boundary for HX3D

The value-level result proves that a platform PCD changed from 91 to 100. It does not by itself prove that every supported processor will run with a 100°C effective junction limit. CPU/SMU-specific policy may clamp the platform input, particularly for HX3D parts.

## Positive result: actual SMU firmware was replaced

The AMD PSP level-2 directory contains composite type `0x00000108`, identified by PSPTool nomenclature as:

```text
PSP_SMU_FN_FIRMWARE~0x108
```

It starts at the same ROM location (`0x1C9600`) in both images, but the signed/compressed container and decompressed firmware are materially different.

### 1.12

```text
container size: 137,840 bytes
container SHA-256:
8b12cce4d120b06698250ba587f185b452d513a8c99c31fb4885cb0ad90d897c

header version: 0.54.68.0

decompressed payload SHA-256:
1a00faf2f497846bd0415c544510f212ea12d4f0753a7b19da24c098b25c8f6b
```

### 1.15

```text
container size: 138,304 bytes
container SHA-256:
f2b07c1f912bda4d18b2dd126606f4c155c57e6d40e00ee9d626b4d1e2b4d129

header version: 0.54.6C.32

decompressed payload SHA-256:
fd45717e18d448bd0a72779b317123e24e90bf2d1b57b528033bdc9f93bc72ef
```

Both decompress to 262,144 bytes. `169,544 / 262,144 = 64.6759%` of bytes differ; only 8/64 4-KiB blocks are identical. This is a real SMU firmware replacement rather than signature/header churn.

**High-confidence attribution:** this is the strongest direct binary match for `Update SMU for power limit`. What remains unknown is which internal SMU routine/table motivated the vendor's `for power limit` wording.

## Host-side SMU wrappers: no new pathway

`SmuV13Dxe` already contains in 1.12:

```text
BIOSSMC_MSG_SetTjMax
BIOSSMC_MSG_SetPPTLimit
BIOSSMC_MSG_SetSlowPPTLimit
BIOSSMC_MSG_SetSustainedPowerLimit
BIOSSMC_MSG_SetSlowPPTLimitApuOnly
STT_MIN_POWER_LIMIT
```

Only 163 raw bytes differ in 1.15, dominated by PCD-token renumbering and the unrelated ECAM-base change. No new immediate `100` assignment was localized. `SmuV13Pei` gives the same general result after TE/relocation normalization.

Thus 1.12 already had the host-side TjMax/PPT message mechanisms; 1.15 did not simply add a new message API.

## AGESA/config host initializers

`AmdAgesaParameterGroupPei` `.data` is byte-identical (5,616 bytes). Its `.text` grows by only 18 bytes, largely structure-layout initialization plus the ECAM-base transition. No new immediate decimal `100` was found.

`CpuSetAgesaPcd` changes only weakly (21 raw bytes in 11 small regions, dominated by address/PCD churn) and also does not expose the TCC assignment directly.

## Confidence / remaining questions

**Confirmed:**

- CBS/AmdSetupRPL defaults do not implement the change.
- APCB does not implement the change.
- `PcdPeim` contains exactly one changed pre-existing scalar default: Dynamic DATA/UINT32 descriptor `0x0400009C`, value `91 → 100`.
- token renumbering is normalized by three inserted Dynamic BOOLEAN tokens and a uniform +3 shift of all 40 DynamicEx local token numbers.
- actual `PSP_SMU_FN_FIRMWARE~0x108` is materially replaced in 1.15.

**High-confidence attribution:**

- `Set TCC to 100` → PcdPeim Dynamic UINT32 `91 → 100`.
- `Update SMU for power limit` → replacement of `PSP_SMU_FN_FIRMWARE~0x108`.

**Still open:**

- symbolic CName of the TCC PCD;
- which module/function consumes local token 209/212 and whether it feeds `SetTjMax` or another thermal path;
- exact internal SMU firmware changes responsible for power-limit behavior.

## Next bounded step

Trace **only** the consumer of this one PCD: local token 209 in 1.12 / 212 in 1.15. Normalize the +3 token-number shift, identify the calling module/function, and determine the value's destination. This is smaller and higher-value than immediately reverse-engineering the complete 256-KiB SMU image.

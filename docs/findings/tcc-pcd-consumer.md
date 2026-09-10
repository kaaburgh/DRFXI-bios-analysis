# TCC PCD consumer path

Last updated: 2026-09-10

Scope: consumer trace for the one Dynamic UINT32 PCD previously isolated in `PcdPeim`:

```text
DRFXI 1.12: local token 209 (0xD1)
DRFXI 1.15: local token 212 (0xD4)
descriptor: 0x0400009C
static default: 91 -> 100
```

## Result

The consumer path closes the missing link between the PCD value change and the 1.15 changelog item `Set TCC to 100`.

The target PCD has one logical PEI writer in `AodPei` and two direct DXE `Get32` reads in `SmuV13Dxe`.

### Direct consumer #1: SMU SetTjMax

`SmuV13Dxe` resolves native EDK II `PcdProtocolGuid` (`11B34006-D85B-4D0A-A290-D5A571310EF7`). On x86-64, `Get32` is the function pointer at `+0x18`.

At the same RVA `0x1B99` in both releases:

```asm
; 1.12
mov  ecx,0xd1
call qword ptr [rax+0x18]   ; PcdProtocol->Get32(209)
...
mov  r8d,eax                ; argument = PCD value
lea  edx,[r9+0x3f]          ; message ID 0x3F
call 0x3ce4                 ; SMU request path

; 1.15: identical semantics, token becomes 0xD4 / 212
```

The same path references firmware diagnostic text:

```text
BIOSSMC_MSG_SetTjMax %x
```

Thus the value chain is:

```text
PcdPeim UINT32 default
91 -> 100
    ↓
PcdProtocol->Get32(209 / 212)
    ↓
SMU request argument
message ID 0x3F
    ↓
BIOSSMC_MSG_SetTjMax
```

### Direct consumer #2: PPTable/default-infrastructure TjMax

The second direct read is at RVA `0x2D1D` in both releases:

```asm
call <get PCD protocol>
mov  ecx,0xd1 / 0xd4
call qword ptr [rax+0x18]
mov  dword ptr [rbx+0x10],eax
```

The surrounding routine populates a defaults/PPTable structure. Another diagnostic routine prints the fields as:

```text
DEFAULT INFRASTRUCTURE LIMITS
  TDP = 0x%x
  PPT = 0x%x
  TDC = 0x%x
  EDC = 0x%x
  TjMax = 0x%x
```

Structure offset `+0x10` maps to `TjMax`. This independently confirms the semantic identity of the target PCD.

## PEI override from AOD

`AodPei` can overwrite the same PCD before DXE.

The IA32 code is semantically identical between releases apart from the expected `0xD1 -> 0xD4` token renumbering:

```asm
cmp   byte ptr [edi+0xb1],0x1
jne   skip
movzx esi,byte ptr [edi+0xb2]
call  <get PCD PPI>
push  esi
push  0xd1 / 0xd4
call  dword ptr [eax+0x44]    ; PcdPpi->Set32(token, esi)
```

AOD IFR identifies the fields:

```text
VarOffset 0xB1: Platform Thermal Throttle Ctrl
  Help: Allows the user to decrease the maximum allowed processor temperature (celsius).
  Manual = 1, Auto = 0 (default)

VarOffset 0xB2: Platform Thermal Throttle Limit
  Help: Allows the user to decrease the maximum allowed processor temperature (celsius).
```

Therefore:

```text
if Platform Thermal Throttle Ctrl == Manual:
    target TjMax PCD = Platform Thermal Throttle Limit
```

The static PCD value `100` is therefore the Auto/platform default; AOD can replace it with a user-requested lower limit before the DXE consumer runs.

## Direct-access inventory

An instruction-pattern scan across all extracted executable PE/TE bodies found, for the version-normalized literal target token:

- DXE native PCD `Get32`: exactly two sites, both `SmuV13Dxe`;
- PEI native PCD `Get32`: no direct target-token site;
- PEI native PCD `Set32`: one logical site in `AodPei` (duplicated in byte-identical firmware-volume copies).

A `0xD1` immediate in `CpuMpPei` was verified as an interrupt/exception-vector stub, not PCD access.

This inventory is exhaustive for the direct literal-token calling forms observed in the firmware. A computed token number or additional abstraction could theoretically evade this pattern scan; no evidence for such a path was found.

## Module identities

`SmuV13Dxe` FFS GUID:

```text
5C60F367-A505-419A-859E-2A4FF6CA6FE5
```

PE SHA-256:

```text
1.12 1a2fd7004920d84f55f45f9a3c0ba00d3de36b2e123915db8dbcbe7044f51b43
1.15 850202358265ab7a3fd4a43c32b59a4f3a393ca5a7a57765f34f888c675d5739
```

## Confidence

**Confirmed:** the target PCD is consumed as `TjMax` through two independent `SmuV13Dxe` paths, and AOD can override it from explicit thermal-throttle controls.

**Very high-confidence changelog attribution:** the static default `91 -> 100` is the firmware change described by `Set TCC to 100`.

**Not proven:** that every CPU using DRFXI ultimately accepts 100°C as its effective silicon temperature limit. SMU/silicon-specific policy may clamp or reinterpret the requested value.

The exact source-level PCD CName remains unavailable because the release PCD database has no name table.

## Status

The static consumer-trace branch is complete for the changelog question. Further work is optional: recover the source-level PCD name from matching debug/source metadata, or verify the effective limit dynamically on hardware.

# Checkpoint — TCC PCD consumer trace

Date: 2026-09-10

Scope: only the consumer path of the `PcdPeim` Dynamic UINT32 PCD whose static default changes `91 -> 100` between DRFXI 1.12 and 1.15.

## Target

```text
1.12 local token 209 (0xD1)
1.15 local token 212 (0xD4)
descriptor 0x0400009C
DATA / UINT32
static default 91 -> 100
```

## Consumer inventory

A direct instruction-pattern scan over extracted PE/TE executable bodies, normalized for token `0xD1 -> 0xD4`, found:

```text
DXE PcdProtocol->Get32: 2 sites, both SmuV13Dxe
PEI PcdPpi->Get32:      no direct target site
PEI PcdPpi->Set32:      1 logical site, AodPei
```

The `AodPei` code exists in byte-identical copies in separate firmware volumes. A broad `0xD1` hit in `CpuMpPei` was checked and is only an interrupt-vector stub.

## SmuV13Dxe read #1

At RVA `0x1B99`:

```asm
; 1.12
mov  ecx,0xd1
call qword ptr [rax+0x18]    ; native PCD Get32
...
mov  r8d,eax                 ; PCD value as SMU argument
lea  edx,[r9+0x3f]           ; message ID 0x3F
call 0x3ce4

; 1.15: same sequence, token 0xD4
```

The code path references diagnostic string:

```text
BIOSSMC_MSG_SetTjMax %x
```

Thus the target PCD is directly fed to the BIOS→SMU SetTjMax path.

## SmuV13Dxe read #2

At RVA `0x2D1D`:

```asm
mov  ecx,0xd1 / 0xd4
call qword ptr [rax+0x18]
mov  dword ptr [rbx+0x10],eax
```

The containing defaults/PPTable structure is dumped elsewhere as:

```text
DEFAULT INFRASTRUCTURE LIMITS
  TDP
  PPT
  TDC
  EDC
  TjMax
```

and offset `+0x10` maps to `TjMax`. This independently confirms the PCD semantic role.

## AodPei writer

The PEI code checks AOD setup offset `0xB1`, reads byte `0xB2`, then calls native PCD PPI `Set32` on target token `0xD1`/`0xD4`.

AOD IFR identifies these exactly:

```text
0xB1 Platform Thermal Throttle Ctrl
     Manual = 1, Auto = 0 (default)

0xB2 Platform Thermal Throttle Limit
```

Both carry help text saying the control allows the user to decrease maximum allowed processor temperature in Celsius.

Therefore:

```text
if Platform Thermal Throttle Ctrl == Manual:
    target TjMax PCD = Platform Thermal Throttle Limit
```

## Conclusion

**Confirmed:** the PCD with static default `91 -> 100` is a TjMax-path configuration value. One consumer sends it directly with `BIOSSMC_MSG_SetTjMax`; another stores it in the PPTable/default-infrastructure `TjMax` field. AOD can override it with an explicit user thermal-throttle limit.

**Very high-confidence attribution:** this closes the code path for the 1.15 changelog item `Set TCC to 100`:

```text
PcdPeim default 91 -> 100
    ↓
SmuV13Dxe PcdGet32
    ↓
BIOSSMC_MSG_SetTjMax
```

**Not proven:** that all CPUs supported by the common DRFXI image ultimately use 100°C as the effective silicon limit. Downstream SMU/silicon policy can still clamp or reinterpret the request.

The source-level PCD CName remains unavailable because the release PCD database omits the PCD name table.

# AMD Variable Protection runtime gate / UEFI Shell path

Date: 2026-09-11

## Scope

Bounded static pass (20–25 minutes) answering only:

1. whether `AmdVariableProtection.efi` directly reads the `AmdPbsSetup` option at offset `0x91`;
2. when variable protection policy is registered;
3. what actually activates/deactivates the protection;
4. whether a late UEFI Shell `SetVariable()` can be expected to modify protected AMD setup variables;
5. whether the firmware itself exposes a no-flash path that temporarily removes the protection.

Generic NVRAM/SMM reverse engineering and broad PBS analysis were out of scope.

## Target module

Stock DRFXI 1.17:

- FFS: `AmdVariableProtection`
- FFS GUID: `0F411BE5-B10C-4DDA-B28C-868FC24789F8`
- PE32 size: 10,752 bytes
- PE32 SHA-256: `b3ae42f5abab17e56d5efc3ecc3019054e336e93cb335d50d681d846b9c9624b`
- subsystem: EFI runtime driver

The DXE dependency expression requires Variable Write Architecture + PCD + one of the two supported policy backends:

- `EDKII_VARIABLE_POLICY_PROTOCOL` (`81D1675C-86F6-48DF-BD95-9A6E4F0925C3`), or
- `EDKII_VAR_CHECK_PROTOCOL` (`AF23B340-97B4-4685-8D4F-A3F28169B21D`).

Public EDK II headers independently identify those GUIDs and the VariablePolicy API semantics.

## Major correction: offset `0x91` is not read by `AmdVariableProtection.efi`

**CONFIRMED.**

The protection driver does **not** read `AMD_PBS_SETUP` / `AmdPbsSetup` offset `0x91`.

The protected-variable table contains names such as:

- `AMD_PBS_SETUP`
- `AmdSetupRPL`
- `AodSetupRpl`

but these are protection targets. There is no direct load of PBS offset `0x91` in this driver.

The actual runtime lock-state variable is a separate authenticated UEFI variable:

- name: `AmdVariableProtection`
- GUID: `408F573D-65EE-49ED-8BC5-5A32BBEAE745`
- state used by policy: byte value `1`

This corrects the earlier working assumption that the Setup option itself was directly consumed by the protection driver.

## Policy registration timing

**CONFIRMED.**

Protection policy is registered during normal DXE execution of `AmdVariableProtection.efi`, not deferred until ReadyToBoot.

The initialization path first consults a PCD Boolean (`PcdProtocol->GetBool()` with token number `6`). If it is false, the feature returns without installing protection. The source-level PCD CName was not recovered in this bounded pass.

If enabled, the driver registers protection for its variable list using one of two backends.

### VariablePolicy backend

The driver builds `VARIABLE_POLICY_TYPE_LOCK_ON_VAR_STATE` entries. The lock-state policy points at:

- namespace `408F573D-65EE-49ED-8BC5-5A32BBEAE745`;
- variable name `AmdVariableProtection`;
- required byte value `1`.

It then calls `EDKII_VARIABLE_POLICY_PROTOCOL.RegisterVariablePolicy()`.

This matches public EDK II semantics: a lock-on-variable-state policy becomes active when the state variable exists and its one-byte value matches the configured value.

### VarCheck fallback

If VariablePolicy is unavailable, the driver registers a VarCheck SetVariable handler. The callback matches incoming name/GUID against the protected-variable table, reads the `AmdVariableProtection` gate variable, and returns `EFI_WRITE_PROTECTED` when the gate byte is `1`.

Thus both backends implement the same effective runtime gate.

## Authenticated gate management

**CONFIRMED.**

The driver contains embedded authenticated create/delete payloads for `AmdVariableProtection` and uses Runtime Services `SetVariable()` with attributes `0x26` (Boot Service + Runtime + time-based authenticated write access).

Two operations are visible statically:

- desired state `0`: authenticated deletion/removal of the gate variable;
- desired state `1`: authenticated creation/restoration with byte value `1`.

A plain unauthenticated Shell write to this gate variable therefore cannot be assumed to work.

## HII Config Routing hook

**CONFIRMED.**

The driver registers a notification for `EFI_HII_CONFIG_ROUTING_PROTOCOL` GUID:

`587E72D7-CC50-4F79-8209-CA291FC1A10F`.

When the protocol appears, it replaces the protocol's first function pointer and preserves the original pointer. Public EDK II `HiiConfigRouting.h` establishes that the first method is `ExtractConfig()`.

The wrapper performs:

```text
if AmdVariableProtection gate exists:
    authenticated-delete gate
call original HiiConfigRouting->ExtractConfig(...)
```

The gate removal occurs before the original function call and is not conditioned on that call succeeding.

This strongly indicates that AMD intentionally opens a configuration window around the normal HII configuration workflow so protected AMD setup variables can be manipulated by firmware Setup code.

## ReadyToBoot behavior

**CONFIRMED.**

A ReadyToBoot callback checks whether `AmdVariableProtection` exists. If it does not, the callback uses the embedded authenticated create payload to recreate the gate with value `1`.

Therefore the intended lifecycle is approximately:

```text
DXE: register policy
        |
        v
AmdVariableProtection == 1 -> protected variables locked
        |
HII ExtractConfig invoked
        |
        v
authenticated delete gate -> policies remain registered but lock-on-state inactive
        |
normal Setup configuration activity
        |
ReadyToBoot
        |
        v
authenticated recreate gate == 1 -> protected variables locked again
```

## Consequence for UEFI Shell

### Plain `SetVariable()` after entering a normal UEFI Shell

**STRONG STATIC EVIDENCE: expected to fail while the gate exists with value `1`.**

For `AMD_PBS_SETUP`, `AmdSetupRPL`, `AodSetupRpl`, and other entries in the protected list, a direct write should hit either VariablePolicy lock-on-state or the VarCheck callback and return `EFI_WRITE_PROTECTED`.

This is a stronger conclusion than the earlier generic concern that protection “might” block Shell writes.

### Potential no-flash route

**STRONG STATIC EVIDENCE, NOT RUNTIME-PROVEN.**

An EFI diagnostic application could locate `EFI_HII_CONFIG_ROUTING_PROTOCOL` and invoke the already-hooked `ExtractConfig()` method. The static code predicts that doing so removes the authenticated gate before forwarding to the original routing implementation. While the gate is absent, VariablePolicy lock-on-state should be inactive; the VarCheck fallback likewise permits writes when the gate is absent/not equal to `1`.

A safe first runtime experiment should remain read-only/diagnostic:

1. inspect whether `AmdVariableProtection` exists before the HII call;
2. invoke a valid HII `ExtractConfig()` request through the installed protocol;
3. inspect whether the gate disappears afterwards;
4. query registered VariablePolicy information / protection state if available;
5. do **not** write a tuning variable in the first probe.

Only after that evidence should a controlled single-setting write be considered.

## What happened to the visible PBS option at offset `0x91`?

`AmdPbsSetupDxe` IFR confirms:

```text
AMD Variable Protection
QuestionId: 0x1D
VarStoreId: 0x1
VarOffset: 0x91
Disabled = 0
Enabled  = 1 (default)
QuestionFlags: 0x14
```

The PE initializes byte `0x91` to `1` in its default PBS structure and reads/serializes that field in normal setup handling.

However, the module does **not** contain the `AmdVariableProtection` gate GUID. Its HII Config Access callback has no dedicated branch for QuestionId `0x1D`; the explicit callback switch handles unrelated high QuestionIds (`0x7D4...`). No direct `offset 0x91 -> PCD token 6` bridge was localized in this bounded pass.

A full-image byte search found the gate GUID/name only in `AmdVariableProtection` and `GenerateTimeBaseVariable` (plus their enclosing volume/container copies), not in `AmdPbsSetupDxe`.

Therefore the exact mechanism by which the visible PBS option affects the feature remains **NOT PROVEN**. Plausible possibilities include a PEI/setup synchronization path or a PCD/state handoff elsewhere, but further tracing would exceed this pass's scope.

## Public-source correlation

Current AMD platform DSCs in `tianocore/edk2-platforms` include `AmdCpmPkg/Features/AmdVariableProtection/AmdVariableProtection.inf`; emulation BIOS configurations explicitly disable that feature through an always-false DEPEX override. This supports treating the binary as a standard AMD feature family rather than MINISFORUM-local code.

## Confidence summary

- **CONFIRMED:** driver does not directly read PBS offset `0x91`.
- **CONFIRMED:** actual runtime lock gate is authenticated variable `AmdVariableProtection` / GUID `408F573D-65EE-49ED-8BC5-5A32BBEAE745`, active at value `1`.
- **CONFIRMED:** policies are registered during DXE execution.
- **CONFIRMED:** VariablePolicy backend uses lock-on-variable-state; VarCheck fallback returns `EFI_WRITE_PROTECTED` under the same gate condition.
- **CONFIRMED:** HII Config Routing `ExtractConfig()` is hooked to remove the gate using an embedded authenticated delete payload.
- **CONFIRMED:** ReadyToBoot restores the gate using an authenticated create payload.
- **STRONG EVIDENCE:** a normal late UEFI Shell direct write to protected variables is blocked while gate=1.
- **STRONG EVIDENCE / NOT RUNTIME-PROVEN:** calling the hooked HII `ExtractConfig()` can intentionally open the same temporary unlocked window used by firmware Setup.
- **NOT PROVEN:** exact bridge from the visible PBS option at offset `0x91` to PCD token 6 / gate lifecycle.

## Stop condition

The requested bounded pass is complete. Further static work on `AmdPbsSetupDxe`/PEI to resolve `0x91` attribution would be a separate investigation. The highest-information next step for the no-flash hypothesis is a small **read-only UEFI probe** that observes the gate before and after HII `ExtractConfig()` on real hardware.

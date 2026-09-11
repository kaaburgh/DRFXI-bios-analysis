# AMD Variable Protection

Last updated: 2026-09-11

Scope: runtime behavior of `AmdVariableProtection.efi` in stock DRFXI 1.17 and implications for changing hidden AMD setup variables without flashing.

## Confirmed implementation

`AmdVariableProtection.efi` is FFS `0F411BE5-B10C-4DDA-B28C-868FC24789F8`. Its PE32 is a small EFI runtime driver. DXE dispatch requires Variable Write Architecture + PCD + either EDKII VariablePolicy or EDKII VarCheck.

The driver protects variables including `AMD_PBS_SETUP`, `AmdSetupRPL`, and `AodSetupRpl`, but it does **not** directly read `AmdPbsSetup` offset `0x91`.

The actual runtime gate is a separate authenticated variable:

- name: `AmdVariableProtection`
- GUID: `408F573D-65EE-49ED-8BC5-5A32BBEAE745`
- active lock-state value: `1`

This corrects the older provisional GUID spelling and the earlier assumption that PBS offset `0x91` was directly consumed by the protection driver.

## Backends

With `EDKII_VARIABLE_POLICY_PROTOCOL`, the driver registers `VARIABLE_POLICY_TYPE_LOCK_ON_VAR_STATE` policies pointing to `AmdVariableProtection == 1`.

With EDKII VarCheck, it installs a SetVariable check handler that matches protected variable name/GUID pairs and returns `EFI_WRITE_PROTECTED` when the same gate variable is present with byte value `1`.

Policy registration occurs during normal DXE execution. It is not delayed until ReadyToBoot.

A PCD Boolean gates installation (`PcdProtocol->GetBool()` token `6`), but the source CName of that token is not yet recovered.

## Authenticated gate lifecycle

The driver embeds authenticated create/delete payloads for `AmdVariableProtection` and uses Runtime Services `SetVariable()` with time-based authenticated-write attributes.

It also hooks `EFI_HII_CONFIG_ROUTING_PROTOCOL->ExtractConfig()`:

```text
if AmdVariableProtection gate exists:
    authenticated-delete gate
call original ExtractConfig(...)
```

A ReadyToBoot callback performs the inverse: if the gate is absent, it uses the embedded authenticated create payload to recreate it with value `1`.

This strongly indicates an intentional configuration window:

```text
normal DXE / gate=1
    -> protected AMD variables locked
HII ExtractConfig
    -> gate removed
    -> lock-on-state inactive
firmware Setup configuration work
ReadyToBoot
    -> gate recreated as 1
    -> protected variables locked again
```

## Implication for UEFI Shell

A plain late Shell `SetVariable()` against `AMD_PBS_SETUP`, `AmdSetupRPL`, or `AodSetupRpl` is expected to receive `EFI_WRITE_PROTECTED` while gate=1.

However there is a strong no-flash hypothesis: an EFI application can call the already-hooked HII Config Routing `ExtractConfig()` path and observe whether the gate disappears. Static code predicts that this happens before forwarding to the original `ExtractConfig()` implementation.

This is **not runtime-proven** on BD790i. The correct first experiment is a read-only EFI probe that records gate existence/state before and after a valid `ExtractConfig()` call; it should not write tuning variables in the first run.

## PBS option `AMD Variable Protection`

`AmdPbsSetupDxe` IFR contains:

- QuestionId `0x1D`
- VarStoreId `0x1`
- VarOffset `0x91`
- Disabled `0`, Enabled `1` (default)
- QuestionFlags `0x14`

The module initializes the PBS structure byte at offset `0x91` to `1` and handles it as part of the normal setup structure. But its explicit HII Config Access callback has no special branch for QuestionId `0x1D`, and `AmdPbsSetupDxe` does not contain the authenticated gate GUID.

A full-image search finds that gate GUID/name only in `AmdVariableProtection` and its companion `GenerateTimeBaseVariable` payload generator (plus enclosing container copies).

Therefore the exact bridge from the visible PBS option at `0x91` to the PCD token/gate lifecycle is still **NOT PROVEN**. Resolving that bridge is a separate follow-up, not required to test the HII-ExtractConfig no-flash hypothesis.

See checkpoint `docs/checkpoints/2026-09-11-amd-variable-protection-shell-path.md`.

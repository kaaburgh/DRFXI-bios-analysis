# AMD Variable Protection

Last updated: 2026-09-12

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

Static inspection also shows that gate creation is **not ReadyToBoot-only**. During the driver's normal DXE initialization, after the protection backend is located/registered, it calls the same gate-state helper with desired state `1`. Therefore a fresh boot should recreate the gate during DXE even if a previous late-Shell probe deleted it after ReadyToBoot.

This strongly indicates an intentional configuration window:

```text
DXE init -> gate created/restored as 1
    -> protected AMD variables locked
HII ExtractConfig
    -> gate removed
    -> lock-on-state inactive
firmware Setup configuration work
ReadyToBoot
    -> gate recreated as 1 when absent
```

## Read-only runtime probe

A minimal standalone X64 UEFI application now exists under:

`tools/amd-variable-protection-probe/`

It records the gate state, locates HII Config Routing, prints the installed `ExtractConfig` pointer, invokes that pointer, records the gate again, and exits. It contains no setup-variable writes, no `RouteConfig()`, no manual authenticated gate mutation, no policy-disable path, no reset call, and no filesystem writes.

### Exact ExtractConfig trigger

The probe passes `Request == NULL` with valid `Progress` and `Results` pointers.

This is intentional. Upstream EDK II `HiiConfigRoutingExtractConfig()` explicitly returns `EFI_INVALID_PARAMETER` for NULL `Request` before allocating results, parsing a request, locating a target HII driver, or calling any driver's Config Access `ExtractConfig()`.

The DRFXI 1.17 AMD wrapper checks/removes the gate **before** forwarding the original four arguments to the saved original function pointer and does not inspect `Request` itself. Thus the NULL request still traverses the interesting AMD hook while minimizing original-router side effects.

Reference probe SHA-256:

`8991966a546960265287ab1e4804658d4e879680ce47c50f29350d0ab4016431`

Static validation confirms PE32+ / X64 / EFI Application, a non-empty relocation directory, no imports, and absence of forbidden service invocations in the source/reference binary checks.

The runtime behavior is still **NOT PROVEN** on actual BD790i hardware. The current expected observation is:

```text
before: gate exists, value 01
ExtractConfig: EFI_INVALID_PARAMETER
after: gate is EFI_NOT_FOUND
```

A gate that remains present is also a valid negative result and must not trigger any bypass attempt.

## Implication for UEFI Shell

A plain late Shell `SetVariable()` against `AMD_PBS_SETUP`, `AmdSetupRPL`, or `AodSetupRpl` is expected to receive `EFI_WRITE_PROTECTED` while gate=1.

A normal Shell launched as a boot option usually starts after ReadyToBoot has already been signaled. If the probe then causes the AMD hook to delete the gate, protection may remain open for the rest of that Shell session. The first hardware procedure therefore requires no variable writes and an immediate reboot/power-cycle after recording the result.

On the next warm/cold boot, the fresh DXE execution should recreate the gate before ReadyToBoot, provided the feature remains enabled and the driver/backend loads normally. This recovery is strong static evidence, not yet hardware-confirmed.

## PBS option `AMD Variable Protection`

`AmdPbsSetupDxe` IFR contains:

- QuestionId `0x1D`
- VarStoreId `0x1`
- VarOffset `0x91`
- Disabled `0`, Enabled `1` (default)
- QuestionFlags `0x14`

The module initializes the PBS structure byte at offset `0x91` to `1` and handles it as part of the normal setup structure. But its explicit HII Config Access callback has no special branch for QuestionId `0x1D`, and `AmdPbsSetupDxe` does not contain the authenticated gate GUID.

A full-image search finds that gate GUID/name only in `AmdVariableProtection` and its companion `GenerateTimeBaseVariable` payload generator (plus enclosing container copies).

Therefore the exact bridge from the visible PBS option at `0x91` to the PCD token/gate lifecycle is still **NOT PROVEN**. Resolving that bridge is a separate follow-up, not required for the first runtime gate experiment.

See checkpoints:

- `docs/checkpoints/2026-09-11-amd-variable-protection-shell-path.md`
- `docs/checkpoints/2026-09-12-amd-variable-protection-runtime-probe.md`

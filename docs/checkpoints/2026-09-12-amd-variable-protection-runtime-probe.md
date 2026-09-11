# AMD Variable Protection runtime probe

Date: 2026-09-12

## Scope

Bounded follow-up to `2026-09-11-amd-variable-protection-shell-path.md`.

Goal: produce and statically validate a minimal read-only X64 UEFI application that can be run from UEFI Shell on stock DRFXI 1.17 to observe the `AmdVariableProtection` gate before and after invoking the installed/hooked `EFI_HII_CONFIG_ROUTING_PROTOCOL->ExtractConfig()`.

No protected AMD setup variable is written. No editor, RouteConfig path, manual authenticated gate mutation, policy disable, flash, reset, or filesystem logging was added.

## Recovered starting facts

Stock DRFXI 1.17 `AmdVariableProtection.efi`:

- FFS GUID `0F411BE5-B10C-4DDA-B28C-868FC24789F8`;
- gate variable `AmdVariableProtection` / `408F573D-65EE-49ED-8BC5-5A32BBEAE745`;
- active state byte `1`;
- protects AMD setup variables through VariablePolicy `LOCK_ON_VAR_STATE` or equivalent VarCheck logic;
- hooks the first method of HII Config Routing, i.e. `ExtractConfig()`;
- wrapper removes the gate before forwarding to original `ExtractConfig()`;
- ReadyToBoot recreates the gate when absent.

## Exact trigger chosen

The probe calls the installed protocol as:

```c
CHAR16 *progress = (CHAR16 *)(UINTN)0x1111111111111111ULL;
CHAR16 *results = NULL;
status = routing->ExtractConfig(routing, NULL, &progress, &results);
```

### Why `Request == NULL`

Upstream EDK II `HiiConfigRoutingExtractConfig()` explicitly treats `Request == NULL` as `EFI_INVALID_PARAMETER`: after validating `This`, `Progress`, and `Results`, it sets `*Progress = NULL` and returns before allocating result storage, parsing routing syntax, locating a driver, or invoking an HII Config Access callback.

DRFXI 1.17 AMD wrapper disassembly shows the opposite ordering at RVA approximately `0x12F4`:

1. save all four incoming arguments;
2. call gate-existence helper (`0x1674`);
3. if gate exists, call gate-state helper with ECX=`0` (`0x16B8`), which is the authenticated delete path;
4. restore all four original arguments;
5. tail-call the saved original `ExtractConfig()` pointer at global `0x3110`.

The wrapper does not validate `Request` before the gate operation.

Therefore the NULL request is intentionally not a successful ConfigRequest. It is a defined original-router error path selected specifically because it still traverses the AMD wrapper while preventing the original EDK II router from reaching any real HII driver.

Expected original-router return is `EFI_INVALID_PARAMETER`; success is not required for the experiment.

## Probe implementation

Added under:

`tools/amd-variable-protection-probe/`

Files:

- `AmdVariableProtectionProbe.c`
- `build.sh`
- `validate.sh`
- `README.md`

Phases:

1. gate `GetVariable()` baseline;
2. HII Config Routing `LocateProtocol()` and print protocol/ExtractConfig addresses;
3. invoke installed `ExtractConfig()` with NULL request;
4. repeat gate `GetVariable()` immediately.

Gate reads report status, existence, attributes, size, and complete value when <=64 KiB.

The first version intentionally omits passive reads of `AmdSetupRPL`, `AodSetupRpl`, and `AMD_PBS_SETUP`: those reads are not needed to answer the first lifecycle question and would add namespace assumptions and code to the smallest hardware experiment.

## Build

Reference toolchain:

- clang 17.0.0
- lld-link 17.0.0

No EDK II or GNU-EFI library dependency is required. The minimal ABI declarations have compile-time offset assertions for every System Table / Runtime Services / Boot Services member used.

The linker uses `/timestamp:0`; two consecutive local rebuilds were byte-identical.

Reference SHA-256:

`8991966a546960265287ab1e4804658d4e879680ce47c50f29350d0ab4016431`

## Static validation

Reference binary:

- PE32+;
- x86-64;
- subsystem `0x0A` EFI Application;
- non-empty PE base-relocation directory with a DIR64 relocation;
- zero import directory;
- no source invocation of `SetVariable()`, `RouteConfig()`, or `ResetSystem()`;
- generated disassembly contains no indirect call at the forbidden table offsets checked by the validator (`0x58`, `0x68`, `0x10`);
- produced image contains no forbidden API names in binary strings;
- no filesystem protocol or logging implementation exists.

`validate.sh` result on the reference build: PASS.

## Gate recovery after running from Shell

### ReadyToBoot timing

Upstream EDK II `EfiBootManagerBoot()` signals ReadyToBoot immediately before starting a normal boot option. Thus a Shell launched as a boot option normally starts after ReadyToBoot, so the AMD ReadyToBoot restoration callback may already have fired before the probe is run.

If the probe then deletes the gate through the AMD hook, do not rely on the same callback running again during that Shell session.

### Next-boot recreation

Static DRFXI 1.17 analysis shows gate creation is not ReadyToBoot-only. In the DXE initialization path, after locating/registering the VariablePolicy or VarCheck backend, the driver calls its gate-state helper with desired state `1`. ReadyToBoot provides another create-if-absent restoration point later.

Therefore a fresh warm or cold boot should rerun DXE and recreate the gate even if the authenticated deletion persisted from the prior Shell session, provided the feature remains enabled and the driver/backend load normally.

This is strong static evidence but still needs hardware confirmation.

## First hardware-test policy

After the first run:

- capture all output;
- do not write any BIOS/setup variables in that boot session;
- reboot or power-cycle immediately;
- on a subsequent Shell boot, verify that Phase 1 sees the gate restored before any later write-capable experiment is considered;
- remember that running this v1 probe a second time will itself trigger deletion again after Phase 1, so reboot once more after that recovery-verification run.

## Expected result

Primary hypothesis:

```text
before ExtractConfig:
  gate exists, value 01

ExtractConfig:
  EFI_INVALID_PARAMETER

after ExtractConfig:
  EFI_NOT_FOUND
```

A gate that remains present is a valid negative result. The probe performs no fallback bypass and no write test.

## Status

**READY FOR FIRST READ-ONLY HARDWARE TEST**, subject to the usual risk of executing an unsigned custom UEFI application.

No write-capable editor should be implemented until the runtime gate lifecycle and reboot recovery are observed on hardware.

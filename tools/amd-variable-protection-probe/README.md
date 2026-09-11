# AmdVariableProtectionProbe

Minimal standalone X64 UEFI application for the first hardware experiment on the DRFXI 1.17 `AmdVariableProtection` lifecycle.

The application itself is read-only with respect to firmware variables. It calls only `GetVariable()` for the gate, `LocateProtocol()` for HII Config Routing, console output, and pool allocation/free. It never calls `SetVariable()`, `RouteConfig()`, `ResetSystem()`, any filesystem write API, or any BIOS-setting mutation path.

The only state change expected during the experiment is the one performed internally by the stock DRFXI 1.17 `AmdVariableProtection.efi` hook when its installed `EFI_HII_CONFIG_ROUTING_PROTOCOL->ExtractConfig()` wrapper is invoked.

## Target

Gate variable:

- name: `AmdVariableProtection`
- GUID: `408F573D-65EE-49ED-8BC5-5A32BBEAE745`
- expected active value: `01`

HII Config Routing protocol:

- GUID: `587E72D7-CC50-4F79-8209-CA291FC1A10F`

## Exact ExtractConfig probe call

The probe calls:

```c
CHAR16 *progress = (CHAR16 *)(UINTN)0x1111111111111111ULL;
CHAR16 *results = NULL;
status = routing->ExtractConfig(routing, NULL, &progress, &results);
```

`Request == NULL` is intentional.

Upstream EDK II `HiiConfigRoutingExtractConfig()` first validates `This`, `Progress`, and `Results`, then explicitly handles `Request == NULL` by setting `*Progress = NULL` and returning `EFI_INVALID_PARAMETER`. It does so before allocating the result buffer, parsing a ConfigRequest, locating a target driver, or calling a driver's `EFI_HII_CONFIG_ACCESS_PROTOCOL->ExtractConfig()`.

The DRFXI 1.17 AMD wrapper has the opposite ordering: it preserves all four incoming arguments, checks whether the `AmdVariableProtection` gate exists, calls its authenticated gate-state helper with desired state `0` when it exists, restores the original four arguments, then tail-calls the saved original `ExtractConfig()` pointer. The wrapper does not inspect or validate `Request` before the gate operation.

Therefore `NULL` is a deliberately defined error-path input to the original router, but it still traverses the interesting AMD wrapper first. This is safer than constructing a routing request that could reach a real HII Config Access driver.

Expected original-router return status is `EFI_INVALID_PARAMETER`. The return code is observational; the gate state before/after is the actual experiment.

## What the application reads

Phase 1 reads the gate with `GetVariable()` and prints:

- EFI status;
- existence;
- attributes;
- size;
- complete value in hex when <= 64 KiB.

Phase 2 uses `LocateProtocol()` and prints:

- locate status;
- protocol instance address;
- installed `ExtractConfig` function pointer.

Phase 3 invokes the installed `ExtractConfig` pointer with the `NULL` request above. If an unexpected non-NULL Results buffer is returned, it is freed.

Phase 4 repeats the gate read immediately.

No protected AMD setup variable is read or written in v1; keeping this first probe gate-only reduces both code size and the number of namespace assumptions involved in the hardware experiment.

## Expected observation

The main hypothesis is:

```text
before ExtractConfig:
  AmdVariableProtection exists
  value hex: 01

after ExtractConfig:
  initial GetVariable: ... EFI_NOT_FOUND
  exists: no
```

A remaining gate is also a valid result. The probe does not attempt to bypass or retry the protection.

The `ExtractConfig` call itself is expected to report `EFI_INVALID_PARAMETER` because the request is intentionally NULL.

## Lifecycle / recovery after running from UEFI Shell

When Shell is launched as a normal boot option, ReadyToBoot is normally signaled by the boot manager immediately before that boot option is started. Thus the AMD ReadyToBoot callback will usually already have run before this probe executes.

If the probe causes the hook to delete the gate after that point, do not assume the ReadyToBoot callback will run again during the same Shell session. Treat protection as potentially open for the remainder of that boot session and perform no setup-variable writes.

Static DRFXI 1.17 analysis also shows that gate creation is not ReadyToBoot-only. During the next DXE startup, after the variable-protection backend is located/registered, `AmdVariableProtection.efi` invokes its gate-state helper with desired state `1`. ReadyToBoot is an additional restoration point later in the boot.

Therefore, with the feature enabled and the driver loading normally, both warm and cold reboot enter a fresh DXE execution and should recreate the gate even if the authenticated deletion persisted in NVRAM from the previous Shell session. This remains a static prediction until verified on hardware.

For the first hardware test, reboot or power-cycle immediately after recording the post-trigger result. On the next Shell boot, run the probe again and confirm that Phase 1 sees the gate restored before considering any later experiment.

## Build

Dependencies used for the reference build:

- clang 17.0.0
- lld-link 17.0.0
- GNU binutils (`objdump`, `strings`) for validation

No EDK II or GNU-EFI headers/libraries are required. The source contains only the minimal ABI structures used by the application, with compile-time offset assertions for the referenced System Table, Runtime Services, and Boot Services fields.

Build:

```sh
cd tools/amd-variable-protection-probe
./build.sh
```

Reference binary SHA-256:

```text
8991966a546960265287ab1e4804658d4e879680ce47c50f29350d0ab4016431
```

`/timestamp:0` is used so repeated builds with the tested clang/lld versions are byte-for-byte reproducible. Two consecutive local reference builds produced the same hash.

## Static validation

Run:

```sh
./validate.sh
```

The reference build passes checks for:

- PE32+;
- x86-64;
- EFI Application subsystem (`0x0A`);
- non-empty PE base-relocation directory;
- no dynamic import table;
- no source invocation of `SetVariable`, `RouteConfig`, or `ResetSystem`;
- no indirect call using the corresponding forbidden service-table offsets in the generated reference disassembly;
- no embedded forbidden API names in binary strings.

The reference binary has one deliberately forced ordinary DIR64 relocation so it remains normally relocatable even though most clang-generated accesses are RIP-relative.

## First hardware test

1. Copy `AmdVariableProtectionProbe.efi` to a FAT32 USB stick or ESP, for example as `\AmdVariableProtectionProbe.efi`.
2. Boot an X64 UEFI Shell.
3. Map filesystems if necessary with `map -r`, then select the USB/ESP mapping, e.g. `fs0:`.
4. Run:

   ```text
   AmdVariableProtectionProbe.efi
   ```

5. Photograph or capture the entire output, especially Phase 1, the protocol/ExtractConfig addresses, Phase 3 status, and Phase 4.
6. Do not run any variable editor or setup-variable write in the same Shell session.
7. Reboot or power-cycle immediately.
8. On the next Shell boot, run the same probe again and verify that the new Phase 1 reports the gate present again. Note that this second run will again trigger the hook; if only a recovery check is desired, a future `--observe-only` mode should be added before that test rather than using this v1 binary.

### If DRFXI has no built-in Shell

Use a trusted X64 EDK II Shell build. Put its `Shell.efi` on a FAT32 USB stick as `\EFI\BOOT\BOOTX64.EFI`, and put `AmdVariableProtectionProbe.efi` in the filesystem root. Boot the USB entry from the firmware boot menu. Building `ShellPkg` from an official `tianocore/edk2` stable tag is the most conservative provenance option; prebuilt shells should be treated as executable firmware tools and obtained only from a source whose provenance you trust.

If Secure Boot rejects the unsigned probe or Shell, do not work around that inside this experiment. Use the board's normal firmware Secure Boot setting only if you explicitly choose to run unsigned UEFI applications, then restore your prior setting afterwards.

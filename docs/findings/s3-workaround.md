# S3 / PCIe power-resume workaround investigation

Last updated: 2026-09-10

Scope: DRFXI 1.15 → 1.17, focused on the 1.16 changelog item:

```text
Workaround abnormal restart after S3
```

Because the 1.16 binary has not been recovered, the temporal attribution remains inferential: 1.15→1.17 mixes changes from 1.16 and 1.17.

## Negative result: old S3 modules are mostly noise

Normalized instruction comparison shows that the obvious legacy S3/PM modules do not contain a substantial new algorithm. Changes are mostly immediate constants consistent with PCD-token renumbering.

Examples include `AmiExtraS3Memory`, `S3SaveStateDxe`, `SmmS3SaveState`, `SleepSmi`, `AcpiTableDxe`, `AmdCpmOemSmm`, `AmdCpmOemInitDxe`, `AmdCpmInitDxe`; `AmdCpmInitSmm` has an identical normalized instruction sequence.

This makes a conventional patch inside the old S3 core path unlikely.

## New `AmdCpmOemAcpi` package

1.17 contains a new module absent from 1.15:

```text
AmdCpmOemAcpi.efi
FFS GUID: 3821290E-B8DD-4821-8182-0361DE51609D
PE size: 25,536 bytes
FFS version section: 1.0
```

Its DXE DEPEX explicitly requires `EfiS3SaveStateProtocolGuid`, in addition to Variable/Pcd and OEM/platform protocols.

The module contains four new valid ACPI SSDTs:

| OEM table id | Length | Role observed |
|---|---:|---|
| `GPIO` | 1,228 | GPIO/USB-C event integration |
| `EXTGPP00` | 1,754 | GPP0/GPP2 wake metadata and helper notifications |
| `GPP_PME_` | 7,449 | PCIe PME/wake GPE handler |
| `PT` | 190,556 | generated PCIe power-transition framework |

These tables were successfully decompiled with ACPICA `iasl` 20260408.

## `PT`: generated PCIe power-transition framework

`PT` contains 58 generated instances of:

- `_PRW`
- `_DSW`
- `_PS0`
- `_PS3`
- a local `PWRS` PowerResource

Each `_PRW` is effectively:

```asl
Name (_PRW, Package (0x02)
{
    0x02,
    0x04
})
```

The table probes real PCI config space, discovers bridge/device topology and initializes cached power/link state rather than exposing every template node blindly.

### D3 path: `_PS3`

For a specific root-port condition, `_PS3` reads an AMD per-port state and, when that state is `0x1B`, calls a helper identified by the firmware's own debug strings as `CpmSendPmeTurnOff`.

Cross-reference into pre-existing `CPMCMN` resolves the helper. It:

1. maps B/D/F to an AMD PCIe-port index;
2. selects platform-specific SMN/register addresses;
3. programs an indirect target-device register;
4. triggers a PME_Turn_Off-style transition;
5. polls hardware completion with bounded timeouts;
6. waits for a per-port six-bit state to become `0x1F`;
7. restores temporary trigger/register state.

The caller then records marker `DPSA = 0x43` for the matching resume path.

The precise symbolic AMD meanings of state values `0x1B`, `0x1F` and marker `0x43` remain unresolved.

### D0/resume path: `_PS0`

When the matching `DPSA == 0x43` marker is present, `_PS0` invokes `CpmWakeLink`, then polls PCIe link state for up to about 500 ms until the link is active and training is no longer in progress, and finally clears WakeLink.

The helper is resolved to `M403` in `CPMCMN`: it maps B/D/F to the AMD port register and sets/clears **bit 22** at a platform-derived register base `+0x280`.

The resulting control flow is:

```text
D3 transition (_PS3)
    ↓
AMD per-port state == 0x1B
    ↓
CpmSendPmeTurnOff
    ↓
wait for per-port state == 0x1F
    ↓
DPSA = 0x43
    ↓
resume / D0 transition (_PS0)
    ↓
CpmWakeLink = 1
    ↓
wait up to ~500 ms for DL_ACTIVE / training complete
    ↓
CpmWakeLink = 0
```

Focused, annotated excerpts are in `evidence/s3/`.

## `GPP_PME_`: dynamically specialized edge-GPE handler

The raw SSDT contains a method named `_E10` and placeholder port names `GPP0...GPPH`, `GP17`, `GP18`, `GP28`.

These names are not static board wiring. `AmdCpmOemAcpi.efi` constructs a patch array and retargets the AML before installation:

- 21 logical PCIe port NameSegs are replaced with platform-provided names;
- the raw `_E10` method is replaced with the actual edge-triggered GPE number;
- the GPE value is derived from MMIO `0xFED8025C` via `(register >> 8) & 0x1F` and converted to `_Exx`.

The handler then, per port:

1. reads PCI configuration register `0x78`;
2. checks event/status bits;
3. sends ACPI `Notify(port, 0x02)` (`Device Wake`);
4. waits 100 ms;
5. acknowledges/clears the relevant status bits by write-back and reread, potentially twice.

For GPP0/GPP7, a platform condition can also issue `Notify(..., 0)` (`Bus Check`) first.

The PCI config helper constructs a normal ECAM address:

```text
ECAM_BASE + (bus << 20) + (device << 15) + (function << 12)
```

This demonstrates that the new AML is actively specialized to the current platform, not merely embedded generic code.

## `EXTGPP00`

This SSDT adds GPP0/GPP2 wake metadata, `_S0W = 4`, local `PWR1` resources and `_GPE` helper methods that can issue Device Wake notifications.

No other static AML reference to several of its helper names was found in the decompiled 1.17 ACPI corpus, suggesting conditional/template use or C-side patching. The exact installation/activation path is still open.

## `GPIO`

`GPIO` adds `_AEI` / `_EVT` handling and an event path that notifies `\_SB.UBTC` with Status Change. Current classification: likely bundled OEM ACPI/USB-C event functionality rather than the core S3 workaround.

## Related `AmiAgesaAcpi` change

`AmiAgesaAcpi.efi` changes materially from 1.15 to 1.17. A new path recognizes FADT/FACP and changes FADT flags, including wake/power-related bits such as `PCI_EXP_WAK`, then recomputes the ACPI checksum.

The same newer firmware also adds a GNVS field named `CNSB`. Its exact semantic role in this firmware remains unresolved.

## Causal assessment

**Confirmed:** 1.17 contains a new AMD CPM/ACPI PCIe power-resume framework absent from 1.15. Its AML implements real PME_Turn_Off, power-state, WakeLink, link-training and PCIe PME event handling.

**Strongly attributable / medium-high confidence:** this framework is the implementation, or a major part of the implementation, behind 1.16's `Workaround abnormal restart after S3`. The known 1.17 changelog only describes dGPU/iGPU behavior and does not naturally explain this new PCIe S3/PM framework.

**Not proven:** that the package first appeared specifically in 1.16. Only the missing 1.16 binary can close that temporal gap.

## Remaining S3-specific work

- resolve the C-side decision logic controlling which of the four SSDTs are actually installed on this platform;
- identify actual runtime root-port names replacing the templates;
- map the AMD register/state values `0x1B` and `0x1F` to documented or independently corroborated state names;
- establish the role of `EXTGPP00` in the installed namespace;
- compare directly against 1.16 if the image is recovered.

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

## Deferred follow-up roadmap

S3-specific work is intentionally paused at this point. The current evidence is already sufficient to identify a technically plausible workaround path, and further detail is lower priority than other open firmware questions.

When this branch is resumed, the most useful next steps are, in roughly descending value:

1. **Recover DRFXI 1.16.** This is the single highest-value step because it would immediately separate the 1.16 S3 changes from unrelated 1.17 changes and convert the current temporal attribution from inference into direct evidence.
2. **Resolve `AmdCpmOemAcpi` installation logic.** Trace the DXE code that selects, patches and installs `PT`, `GPP_PME_`, `EXTGPP00` and `GPIO`; determine which tables are always installed and which are platform/configuration dependent.
3. **Recover actual runtime root-port mappings.** Determine the concrete ACPI NameSegs that replace template names such as `GPP0...GPPH`, `GP17`, `GP18`, `GP28` and the placeholder used by `PT` on BD790i X3D.
4. **Resolve the dynamic GPE mapping.** Confirm the runtime `_Exx` value derived from MMIO `0xFED8025C`, and connect it to the relevant FCH/SoC GPE source if documentation or runtime ACPI tables become available.
5. **Name the AMD link-state values.** Map `0x1B`, `0x1F`, marker `0x43`, the per-port `+0x280` WakeLink bit, and related `+0x294` state fields to AMD register/state names using public BKDG/PPR/AGESA-derived material or independent firmware corroboration.
6. **Finish `EXTGPP00` activation analysis.** Determine how `APRW`, `BPRW`, `NGP0`, `NGP2`, `OL02` and `OL08` are consumed or patched, and whether that table is part of the core S3 workaround or ancillary wake metadata.
7. **Trace the `AmiAgesaAcpi` side of the change.** Identify the inputs controlling its FADT flag edits (`PCI_EXP_WAK`, `HW_REDUCED_ACPI`, `LOW_POWER_S0_IDLE_CAPABLE`) and establish the role of the newly introduced `CNSB` GNVS field.
8. **Validate against runtime ACPI on real hardware.** From a machine running 1.15 and/or 1.17, capture `/sys/firmware/acpi/tables` (and dynamic tables if present), decompile them, and compare installed/patched SSDTs against the firmware templates. This would answer several installation and runtime-mapping questions without further static reverse engineering.
9. **Reproduce the failure/fix experimentally if practical.** If S3 is available on the board, compare suspend/resume behavior, PCIe link state and wake events between 1.15 and 1.17. This is optional and should only be attempted with a recoverable system state.

The investigation should not restart by re-reading the generic S3 modules (`S3SaveStateDxe`, `SmmS3SaveState`, `SleepSmi`, etc.) unless new 1.16 evidence points back to them; the current normalized diff indicates that path is mostly PCD-token churn.

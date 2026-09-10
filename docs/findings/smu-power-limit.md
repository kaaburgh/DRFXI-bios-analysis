# TCC / SMU power-limit investigation

Last updated: 2026-09-10

Relevant 1.15 changelog items:

```text
Set TCC to 100
Update SMU for power limit
```

## `SmuV13Dxe` result

`SmuV13Dxe.efi` does contain power/thermal-related code and strings such as:

```text
BIOSSMC_MSG_SetTjMax
BIOSSMC_MSG_SetPPTLimit
BIOSSMC_MSG_SetSlowPPTLimit
BIOSSMC_MSG_SetSustainedPowerLimit
STT_MIN_POWER_LIMIT
```

However, direct 1.12→1.15 comparison does **not** reveal an obvious new power-limit algorithm in this module.

Most observed differences are systematic PCD-token renumbering, for example immediate values shifting by the same small offset. A genuine platform constant also changes from PCI ECAM base `0xF0000000` to `0xE0000000`, but the same transition appears in multiple PCI/platform modules and is not specific to SMU.

`SmuV13Pei` shows a similarly weak semantic difference after TE/relocation normalization.

HII entries such as Thermal Control / TjMax also remain semantically stable.

## Current conclusion

The two changelog items are **not yet localized**. The current negative result is useful: the primary change is unlikely to be a simple new `SmuV13Dxe` UI/code path.

Highest-value remaining candidates are configuration/default data outside this executable module, especially:

- APCB;
- AGESA/PI configuration data;
- SMU-related tables/blobs;
- PCD/default-setting changes consumed by existing SMU code.

Until one of those data paths is mapped, `Set TCC to 100` and `Update SMU for power limit` remain unresolved rather than guessed.

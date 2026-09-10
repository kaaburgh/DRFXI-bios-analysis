# HII / IFR findings

Last updated: 2026-09-10

Scope: semantic setup-menu comparison across official DRFXI 1.12, 1.15 and 1.17.

## Extraction summary

The same 17 principal IFR-bearing modules were found in all three images.

| Version | PE32 modules scanned | IFR modules | Parameters | Forms | VarStores | References |
|---|---:|---:|---:|---:|---:|---:|
| 1.12 | 279 | 17 | 2595 | 272 | 73 | 358 |
| 1.15 | 282 | 17 | 2527 | 272 | 71 | 356 |
| 1.17 | 287 | 17 | 2523 | 273 | 72 | 354 |

## AMD CBS / memory controls

After removing extractor metadata/noise, the HII/IFR content of `CbsSetupDxeRPL` is semantically identical across 1.12, 1.15 and 1.17. `AodDxe` is also semantically stable.

The hidden tuning surface retained in newer firmware includes primary/secondary/tertiary DRAM timings, RTT/ODT, drive strengths, Power Down, TSME, memory training, ECC, address hashing, fabric-clock and voltage controls.

The original community 1.12 modification is therefore best understood as an **access/visibility unlock**, not an implementation of new memory-training features.

### Important limitation

A hidden HII question can only expose functionality that the underlying firmware/AGESA/SMU actually implements. Making a question visible does not create a missing hardware/firmware capability.

## Save / Restore User Defaults

All three versions contain real AMI actions:

```text
Save as User Defaults
Restore User Defaults
Load Optimized Defaults
```

`Save as User Defaults` and `Restore User Defaults` are nested under an unconditional suppression expression:

```text
SuppressIf
    Uint64 Value: 0x1
```

The detailed extracted context is preserved under `evidence/hii/user-defaults.txt`.

### Interpretation

This establishes the presence of a hidden **single AMI user-default save/restore mechanism**. It does not establish multiple named OC-profile slots.

## Above 4G Decoding

1.12 contains two `Above 4G Decoding` questions pointing at the same underlying setting (`VarOffset 0x9D`):

- one normally exposed entry;
- a second entry already buried under always-true suppression.

In 1.15 and 1.17, the visible copy is gone while the suppressed copy remains.

This directly demonstrates the 1.14 changelog item:

```text
Hide Above 4G Decoding
```

Focused IFR evidence is in `evidence/hii/above-4g-decoding.txt`.

## AMD Variable Protection

`AmdPbsSetupDxe` gains the following question by 1.15:

```text
AMD Variable Protection
```

Properties:

- VarStoreId: `0x1`
- VarOffset: `0x91`
- default: Enabled
- help text explicitly says it protects AMD CBS/PBS/AOD variables against runtime modification by tools such as RU.

A corresponding new executable module `AmdVariableProtection.efi` is present by 1.15.

This is a real released behavior change not explicitly listed in the known 1.13–1.15 changelog. It may be part of the PI 1.0.0.3h platform update, but that attribution is not yet proven.

Focused evidence is in `evidence/hii/amd-variable-protection.txt`.

## 1.17 TCG Storage Security setup addition

By 1.17, setup contains two `TCG Storage device Security Configuration` forms and a new VarStore associated with `TcgStorageDynamicSetupVar`. They accompany new executable modules `TcgStorageSecurity.efi` and `SmmTcgStorageSec.efi`.

No known 1.16/1.17 changelog line explicitly mentions this feature, so it is currently tracked as a confirmed released change with undocumented provenance.

## Unlock strategy implications

The safest future unlock approach is **semantic and version-specific**:

1. identify the same HII questions/forms in the target release;
2. patch the access/suppression metadata in that release;
3. avoid copying a whole SetupData blob or fixed offsets from 1.12 into 1.17;
4. validate the resulting image structurally before any flashing experiment.

The community `795iX3D.bin` is useful as an example of intent, but its complete SPI image contains donor-board runtime state and is not suitable as a clean patch source.

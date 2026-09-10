# Community `795iX3D.bin` analysis

Last updated: 2026-09-10

## Classification

The community `795iX3D.bin` image is best classified as a **full 32 MiB SPI readback from a configured board after a setup-menu modification**, not as a clean vendor-style update image.

SHA-256:

```text
c63971eedd2e03005aaeba2786aa7834b38c8ac006978e9a011156ee61122b15
```

## Parent firmware

The image is overwhelmingly based on official DRFXI 1.12.

Evidence:

- timestamp 2025-09-04, before the 1.13 release date;
- 7120/8192 4 KiB blocks match 1.12 exactly (86.91%);
- the first 16 MiB differ from 1.12 by only ~0.776%;
- the final 4 MiB are byte-identical to official 1.12;
- similarity to 1.04, 1.07 and 1.15 is materially lower.

## Intentional UEFI modification

Within the main UEFI FV:

- both images contain 399 parsed FFS files;
- 398/399 are byte-identical;
- the only changed FFS file is `FE612B72-203C-47B1-8560-A66D946EB371`;
- this file is `AMITSESetupData` / SetupData and is non-executable setup/menu data.

After decompressing the inner SetupData payload:

- stock and modified payloads are both 157,288 bytes;
- exactly 60 individual bytes differ;
- every change sets bit `0x04`;
- transitions are `0x09→0x0D` ×30, `0x01→0x05` ×24, `0x29→0x2D` ×6.

The offset list is preserved in `data/setupdata-1.12-community-mod-diff.txt`.

## Interpretation

The binary result strongly matches the accompanying community guide, which describes using AMIBCP5 to change setup access/use levels to `USER`.

No other parsed UEFI executable or data module changed. Therefore the modification does not appear to add a new memory controller implementation or new AGESA code; it changes setup visibility/access metadata.

## Why the full image is not a portable mod

Outside the intentional SetupData change, the SPI image contains state associated with the donor board, including populated NVRAM, AMD APOB/runtime-training data, APCB differences, UEFI boot variables and Secure Boot-related material.

Consequently, the complete 32 MiB image should be preserved only as evidence/reference. A future clean unlock should reproduce the relevant SetupData/HII changes against a clean target release instead of flashing this donor image wholesale.

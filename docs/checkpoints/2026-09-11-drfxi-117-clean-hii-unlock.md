# DRFXI 1.17 clean HII unlock — checkpoint

Date: 2026-09-11

## Scope

Develop a minimal, reproducible unlock for useful hidden setup controls in official DRFXI 1.17 without transplanting donor-board NVRAM/APOB/APCB/boot/security state from the community `795iX3D.bin` SPI readback.

This pass is limited to:

1. identifying the exact `AMITSESetupData` access/visibility structure changed by the community 1.12 mod;
2. mapping those records semantically to stock 1.17 rather than by fixed raw offsets;
3. deriving a fail-closed, version-specific patch procedure;
4. statically validating the rebuilt image.

Flashing is explicitly out of scope.

## Starting evidence

Official images re-extracted from the recovered acquisition bundle:

- DRFXI 1.12 SHA-256: `246e7f54a12a8c7279ef68433602264b8ecbabcde828c9c9008f571c270845b9`
- DRFXI 1.17 SHA-256: `99f3bab5ea491202bf365c23e6416f9d1e8a649ad00f90c1f3e21f1a61e35c51`
- community `795iX3D.bin` SHA-256: `c63971eedd2e03005aaeba2786aa7834b38c8ac006978e9a011156ee61122b15`

The target freeform FFS is:

- `AMITSESetupData`
- GUID `FE612B72-203C-47B1-8560-A66D946EB371`

UEFIExtract A75 finds it at main-volume file index 398 in stock/community 1.12 and index 404 in 1.17.

The decompressed inner payloads are:

- stock 1.12: 157,232 bytes, SHA-256 `d371a061cec1cf24b0c008c69494ecfde2b885306e85652d0252bd73bc5cf706`
- community 1.12: 157,232 bytes, SHA-256 `b3d75f4ed2bfa878858206ddf068583a682f7fc6a9b8a9e5e771501b51af01c1`
- stock 1.17: 156,412 bytes, SHA-256 `22879575d33dbe6d711b3f3d45c7bd46f09757d2284ad51aef7ba9358f183973`

## First reproduced result

Direct stock-1.12 vs community comparison on the current A75-extracted inner `body.bin` reproduces exactly **60 one-byte differences**.

Every difference sets bit `0x04` in one 32-bit little-endian field:

- `0x01 -> 0x05`
- `0x09 -> 0x0D`
- `0x29 -> 0x2D`

No other decompressed payload bytes differ.

The offsets in the existing `data/setupdata-1.12-community-mod-diff.txt` are consistently `+0x14` relative to the current A75 `body.bin` offsets. This is explained by the 20-byte (`0x14`) GUID-defined-section header: the historical list used a container-relative origin while A75 exposes the post-header inner body. The underlying changed bytes are the same.

The immediate byte context around multiple changed locations has a recurring record shape. The modified field occurs after a 16-byte prefix containing small IDs/index values and before further small integer fields. This strongly supports the prior interpretation that AMIBCP changed per-entry access/visibility metadata rather than setup implementation code.

## Current status

**CONFIRMED:** community unlock is a pure 60-byte access-bit transformation inside decompressed `AMITSESetupData` for the UEFI portion under study.

**NOT YET PROVEN:** the exact semantic meaning of every bit in the field, the complete record format, and the correct 1.17 record mapping.

Next bounded step: recover the record grammar / stable semantic keys and map the 60 modified 1.12 entries onto 1.17 without using raw offsets.

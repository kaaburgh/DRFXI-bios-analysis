# DRFXI firmware lineage and provenance

Last updated: 2026-09-10

This document records release metadata and artifact provenance separately from interpretation of code changes.

## Release lineage

| Version | Release date | Vendor checksum | Distribution acquired? | Notes |
|---|---|---:|---|---|
| 1.04 | 2023-12-05 | `73E7` | yes | historical support-supplied MediaFire candidate; package structure and embedded checksum are internally consistent |
| 1.05 | 2023-12-21 | `1608` | no | cumulative release note only |
| 1.06 | 2024-07-16 | `1BCF` | no | cumulative release note only; PI 1.0.0.3d, RAID, board-detection changes |
| 1.07 | 2024-08-20 | `54FB` | yes | historical MediaFire package `DRFXI_1.07_240820B.7z` |
| 1.08 | 2024-09-20 | `C3F5` | no | cumulative release note only |
| 1.09 | 2024-09-29 | `A582` | no | cumulative release note only |
| 1.10 | 2024-11-13 | `3F93` | no | cumulative release note only |
| 1.11 | 2025-02-05 | `1724` | no | cumulative note explicitly mentions X3D driver fix |
| 1.12 | 2025-02-13 | `9A63` | yes | official Aliyun package |
| 1.13 | 2025-09-28 | `BF21` | no | recovered from cumulative 1.15 release note |
| 1.14 | 2025-11-13 | `419D` | no | recovered from cumulative 1.15 release note |
| 1.15 | 2026-01-05 | `A4C4` | yes | official Aliyun + S3 copies are byte-identical |
| 1.16 | 2026-06-03 | `1EA3` | no | confirmed by cumulative 1.17 note; exact package URL unresolved |
| 1.17 | 2026-08-28 | `4B54` | yes | current official support release |

## Acquired DRFXI.BIN hashes

| Version | SHA-256 |
|---|---|
| 1.04 | `a1add065776b7b8b2425394fac9140810d238fa604239a2cccdc495796d09585` |
| 1.07 | `c38c918b39df06759f5c57a96c14422ba0f090aef5d9e50ac4e18de97b64ac46` |
| 1.12 | `246e7f54a12a8c7279ef68433602264b8ecbabcde828c9c9008f571c270845b9` |
| 1.15 | `3afaba6d916b3897d1d98bd5913008b38e89b6c51b2c6963c7109793541d8d88` |
| 1.17 | `99f3bab5ea491202bf365c23e6416f9d1e8a649ad00f90c1f3e21f1a61e35c51` |

Community reference dump:

- `795iX3D.bin`: `c63971eedd2e03005aaeba2786aa7834b38c8ac006978e9a011156ee61122b15`

## Acquired distribution-package hashes

| Artifact | Size | SHA-256 |
|---|---:|---|
| DRFXI 1.04 package | 6,703,582 | `21282224394940e0dc1d106e03eed9abcc820585e56298bffb1d1908f075f8e9` |
| DRFXI 1.07 package | 6,754,674 | `a91184bbdb9eef2d0c7cb6a9a22023683319c11ee9aef5d9e50ac4e18de97b64ac46` |
| DRFXI 1.12 package | 6,768,601 | `5b71d15872c199879224dd12fcb03808d8acadb320acdf76f72a4262a92362ab` |
| DRFXI 1.15 package | 6,845,094 | `52f2721a359a4066956e1dc57e14a4cd103f32108bf31086cb8d7ea053d42957` |
| DRFXI 1.17 package | — | acquisition corpus retained outside this repository; DRFXI.BIN hash above is authoritative for current analysis |

For 1.15, independent vendor-origin Aliyun and AWS S3 URLs returned byte-identical archives with SHA-256 `52f2721a359a4066956e1dc57e14a4cd103f32108bf31086cb8d7ea053d42957`.

## Vendor checksum behavior

For every acquired official image tested so far, the hexadecimal `BIOS Checksum` written in the release note equals:

```text
sum(all DRFXI.BIN bytes) & 0xffff
```

This is useful for identifying historical package candidates but is **not** a cryptographic authenticity mechanism.

## Known official / historical URLs

Exact historical URLs recovered during acquisition:

```text
https://pc-file-web.oss-cn-shenzhen.aliyuncs.com/BD790i%20BD770i/Bios/DRFXI_1.12_250213A.7z
https://pc-file-web.oss-cn-shenzhen.aliyuncs.com/BD790i%20BD770i/Bios/DRFXI_1.15_260105A.7z
https://pc-file.s3.us-west-1.amazonaws.com/BD790i+BD770i/Bios/DRFXI_1.15_260105A.7z
```

Current official 1.17 URL observed directly from the MINISFORUM support UI:

```text
https://pc-file.s3.us-west-1.amazonaws.com/895D7/BIOS/DRFXI_1.17_260828A.7z
```

The `895D7` path appears to be a current MINISFORUM product/platform directory. This repository does not infer that historical releases necessarily used the same directory.

### 1.16 negative probes

The reconstructed Aliyun key:

```text
BD790i BD770i/Bios/DRFXI_1.16_260603A.7z
```

returned Aliyun `NoSuchKey`, which is evidence that this exact object key does not exist there.

Several S3 candidates returned `AccessDenied`. Anonymous S3 `403 AccessDenied` does **not** prove object existence or non-existence when list permissions are absent, so those probes remain indeterminate rather than confirmed missing.

## Changelog recovered from cumulative notes

### 1.13

- Update PI 1.0.0.3h
- Fix hang at POST logo caused by Intel LAN OPROM

### 1.14

- Update DMI Base Board Manufacturer
- Hide `Above 4G Decoding`

### 1.15

- Set TCC to 100
- Update SMU for power limit
- Update DMI

### 1.16

- Workaround abnormal restart after S3
- Add AMI flash driver EIP

### 1.17

- Automatically detect dGPU and turn off iGPU when graphics configuration changes
- Alter availability/modifiability of the iGPU setup item when graphics status is unchanged

## Provenance rule

A version number, reconstructed filename, or URL pattern is not promoted to an acquired artifact unless bytes are obtained and hashed. Historical URLs and negative probes are kept because they help avoid repeating failed acquisition guesses.

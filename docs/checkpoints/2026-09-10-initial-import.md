# 2026-09-10 initial repository checkpoint

This checkpoint records the research state imported when `DRFXI-bios-analysis` was created as the durable home for the investigation.

## Source analysis artifacts retained outside Git

The following locally generated reports/bundles existed at import time and are identified here by SHA-256 for provenance:

| Artifact | SHA-256 |
|---|---|
| `bd790i-intermediate-report-2026-09-10.md` | `475fb802860bf426b7b9ac0ac82216a74d19d1b1351017c6abf1e3c411f469f6` |
| `bd790i-s3-investigation-checkpoint-2026-09-10.md` | `a9c3682a53d27b5efadda01f54f006f0c2a5b3220e0db4696f926c6ad7c18741` |
| `bd790i-s3-aml-checkpoint-2026-09-10.md` | `bfaa4cb2672e3114b7e7fb3e29b5f15e095e58851adb72808a07f2d3baf6467a` |
| `bd790i-s3-aml-checkpoint-2026-09-10.zip` | `60373b3e624f3423bb947de05bbdb61606814129bf57e6f312c43f70960fb0d3` |
| forensic pass-2 bundle | `a1f20b57b203be70fd8fd40cd5ba55bcf1a4305b8254f3664f08d2959aeec29a` |

The Git repository does not depend on those bundles for its conclusions: the current findings have been rewritten into topic-oriented living documents under `docs/findings/`, with hashes and focused evidence under `data/` and `evidence/`.

## State at this checkpoint

Confirmed or strongly supported findings imported on this date:

- official 1.12 / 1.15 / 1.17 corpus and hashes established;
- 1.13 / 1.14 / 1.16 existence and release metadata recovered, but binaries missing;
- community `795iX3D.bin` traced to official 1.12 and its intentional SetupData modification reduced to 60 byte-level access-bit changes;
- hidden AMD CBS/UMC memory controls retained through 1.17;
- hidden Save/Restore User Defaults present through 1.17;
- 1.14 Above-4G hiding directly confirmed in IFR;
- AMD Variable Protection added by 1.15;
- 1.17 dGPU/iGPU behavior localized to OEM DXE logic and `AmdSetupRPL` offset `0x44`;
- 1.16 flash-driver-EIP change strongly mapped to ReFlash/FlashDriver changes;
- 1.16 S3 workaround strongly associated with newly introduced `AmdCpmOemAcpi` PCIe power/wake AML, subject to the missing-1.16 temporal caveat;
- TCG Storage Security functionality appears by 1.17 without an explicit known changelog item;
- TCC/SMU power-limit and Intel LAN OPROM fixes remain incompletely localized.

## Repository-maintenance rule established here

Future work should update the living documents rather than continually adding one-off report files. Add a dated checkpoint only when a meaningful phase of investigation closes or before a major reinterpretation. Small reproducible excerpts belong under `evidence/`; raw firmware and complete vendor-derived decompilations remain outside Git by default.

# Research work queue

Last updated: 2026-09-11

This file records which branches are active, complete enough to stop, or intentionally deferred. Topic details remain in `docs/findings/`; immutable snapshots remain in `docs/checkpoints/`.

## Ready for next bounded investigation

No evidence-backed follow-up is currently ready for `CVE-2024-36311`: public disclosure does not identify a concrete SMM handler/module/GUID, so a binary pass would become generic SMM reverse engineering.

Other valuable bounded branches remain:

- recover missing official firmware 1.13 / 1.14 / 1.16;
- classify a remaining normalized PE/FFS change only when driven by a concrete changelog or unexplained released feature;
- if the clean 1.17 unlock is ever considered for hardware use, perform a **separate** bounded pre-flash integrity/recovery pass before discussing a flashing procedure.

## Completed enough to stop

### DRFXI 1.17 clean HII unlock — static construction

A fail-closed version-specific patcher now exists at `scripts/patch_drfxi_117_clean_hii_unlock.py` for the exact official DRFXI 1.17 image.

The first minimal target set makes 24 semantic edits before recompression:

- 22 `AMITSESetupData` access-byte edits for the selected UMC/DDR tree and `SMU Common Options` form;
- 2 `Setup` IFR constant edits exposing AMI Save/Restore User Defaults.

The two nested LZMA containers are rebuilt inside their existing allocations, with FFS/section sizes preserved. UEFIExtract A75 reports identical structure before/after. Recursive extraction yields 6926 leaves in each image with identical path sets and only two differing leaf payloads: `Setup` PE32 and `AMITSESetupData`. Patched IFR changes only the two intended unconditional `Uint64 1 -> 0` suppressors.

The reference output hash and validation are recorded in `data/drfxi-1.17-clean-hii-unlock-validation.json` and `docs/findings/clean-hii-unlock.md`.

This closes the **static construction** branch. Do not expand the unlock to unrelated CPU/power/SmartShift pages by default. Flash safety and hardware behavior are separate, unproven questions.

### PI 1.0.0.3h — first new-module triage

The three newly named PE modules are classified and do not form a single functional cluster. The first immediate dependency edge is normalized. Do not repeat broad triage of those three modules.

### `Set TCC to 100`

Static consumer path is closed:

```text
PcdPeim default 91 -> 100
    ↓
SmuV13Dxe PcdGet32
    ↓
BIOSSMC_MSG_SetTjMax
```

Further work is optional only: source-level PCD CName or runtime effective-limit validation.

See `docs/findings/tcc-pcd-consumer.md`.

## Deferred / paused deep dives

### PI 1.0.0.3h / CVE-2024-36311 SMM TOCTOU

**Paused on 2026-09-11 due to an external-evidence blocker.**

AMD directly establishes:

- `CVE-2024-36311` is a TOCTOU in an SMM communications buffer;
- Dragon Range / Ryzen 7045 is mitigated by `DragonRangeFL1PI 1.0.0.3h`.

However the public AMD/CVE record does not identify a communication GUID, handler GUID, module, function, source path, or exact TOCTOU shape. Focused public/GitHub searches found mirrors of the advisory but no patch, PoC, researcher write-up, or concrete implementation fingerprint.

Generic EDK2 SMM communication code (`PiSmmCommunication`, `PiSmmCore`, `SmmMemLib`) is only a source-family correlation; there is no evidence that CVE-2024-36311 resides in those components. Do **not** map the CVE into DRFXI by scanning all SMM modules or by selecting every caller of `SmmIsBufferOutsideSmmValid`.

Resume only if one of these appears:

1. an AMD/researcher disclosure naming the affected module/handler/function/GUID;
2. a source patch explicitly tied to CVE-2024-36311 or DragonRangeFL1PI 1.0.0.3h;
3. a strong cross-platform pre/post mitigation firmware comparison that isolates one common SMM component;
4. recovered DRFXI 1.13 plus an independent fingerprint narrowing the SMM target.

See `docs/checkpoints/2026-09-11-pi-1.0.0.3h-cve-2024-36311.md`.

### Intel LAN OPROM POST-hang fix

**Paused on 2026-09-11.**

The generic firmware-side path has been followed far enough that further broad reverse engineering has low expected value. The exact Intel NIC / PCI Device ID behind the MINISFORUM changelog is still unknown. Public BD790i evidence makes **Intel X710-DA2 / `I40eUndiDxe`** the strongest board-specific candidate found so far, but it is not proven to be the original reproducer.

The next justified development of this branch is external-artifact-driven: obtain the **actual X710-DA2 Option ROM** (or, preferably, the exact original problem NIC/ROM if it can be identified), then trace its real entrypoint / DriverBinding / hardware-init dependencies against 1.12→1.15. Do not resume generic PciBus/BDS/LoadImage/Security2/CSM/protocol-notify analysis without such an artifact.

See `docs/findings/intel-lan-oprom.md` and `docs/checkpoints/2026-09-11-intel-lan-oprom-source-dependencies-closure.md`.

### `Update SMU for power limit`

Paused. The replacement of `PSP_SMU_FN_FIRMWARE~0x108` is established, and raw-diff normalization shows extensive layout movement, but internal handler/table attribution now requires a reusable Ghidra/Xtensa-le reverse-engineering environment.

Do not resume with more raw byte diffing.

See `docs/deferred/smu-power-limit-deep-dive.md` and `docs/checkpoints/2026-09-10-smu-power-internal-intermediate.md`.

### S3 / PCIe power-resume

Paused after the AML/ACPICA investigation. Resume primarily when DRFXI 1.16 is recovered or when runtime ACPI evidence becomes useful.

See `docs/findings/s3-workaround.md`.

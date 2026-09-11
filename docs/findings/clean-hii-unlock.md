# Clean HII unlock for DRFXI 1.17

Last updated: 2026-09-11

Scope: derive a minimal, version-specific visibility unlock for official DRFXI 1.17 without transplanting NVRAM/APOB/APCB/boot/security state from the community `795iX3D.bin` SPI readback.

Flashing is intentionally out of scope. This document records static construction and validation only.

## Target image

Official DRFXI 1.17:

- size: `33554432` bytes
- SHA-256: `99f3bab5ea491202bf365c23e6416f9d1e8a649ad00f90c1f3e21f1a61e35c51`

The patcher is designed to fail closed on any other input hash.

## Community 1.12 mechanism

Re-extraction of stock DRFXI 1.12 and community `795iX3D.bin` reproduces exactly 60 one-byte changes in the decompressed `AMITSESetupData` payload.

Every community change sets only bit `0x04`:

```text
01 -> 05
09 -> 0D
29 -> 2D
```

No failsafe/default values, question IDs or implementation code change inside that payload.

This confirms that the relevant community modification is an AMI access/visibility metadata edit rather than an implementation of new AGESA features.

## AMITSESetupData record grammar

Public source from `BoringBoredom/UEFI-Editor`, pinned during this investigation at commit `44e8c9ba4a05dbd6fc4b1c247ed17948b6e58f8d`, independently documents the same record structure used by its `getAdditionalData()` parser.

For ordinary question/reference records, a stable semantic key is:

- QuestionId at record `+0x00`;
- page/context fields around `+0x0A/+0x0C`;
- access byte at `+0x10`;
- Help StringId at `+0x14`;
- Prompt StringId at `+0x30`;
- failsafe at `+0x34`;
- optimal at `+0x35`.

The UEFI-Editor parser locates a record through `(QuestionId, Help StringId, Prompt StringId)` and treats `record+0x10` as the access-level byte. This is exactly the field changed by the community image.

Source:

`https://github.com/BoringBoredom/UEFI-Editor/blob/44e8c9ba4a05dbd6fc4b1c247ed17948b6e58f8d/src/components/scripts/scripts.ts`

This allows 1.12 intent to be transferred to 1.17 by semantic identity instead of raw offsets.

## Minimal 1.17 unlock set

The first clean patch intentionally does **not** reproduce all 60 community changes. It limits the AMITSE access edits to the memory/FCLK-related path requested for the first version.

### Question/reference records

The following 13 records have access bit `0x04` enabled:

- `UMC Common Options`
- `DDR Options`
- `DDR Controller Configuration`
- `DDR Power Options`
- `Power Down Enable`
- `DDR RAS`
- `DDR ECC Configuration`
- `ECC`
- `DDR Security`
- `TSME`
- `Data Scramble`
- `DDR Memory Features`
- `Memory Context Restore`

Each is located uniquely in stock 1.17 through `(QuestionId, Prompt StringId, Help StringId)` rather than an absolute byte offset.

### Form records

Nine matching form metadata records are also unlocked:

- `UMC Common Options`
- `DDR Options`
- `DDR Controller Configuration`
- `DDR Power Options`
- `DDR RAS`
- `DDR ECC Configuration`
- `DDR Security`
- `DDR Memory Features`
- `SMU Common Options`

The 1.17 form records are uniquely matched with `(type=0x08, context/page index, Prompt StringId)`.

Unlocking the `SMU Common Options` form exposes the already-existing VDDP/FCLK branch without reproducing unrelated community changes to TDP/PPT/TjMax/TDC/EDC/PROCHOT/SmartShift controls.

Existing IFR confirms that `VDDP Voltage Control`, `VDDP Voltage`, and `Infinity Fabric Frequency and Dividers` are already present beneath this branch; their own AMITSE access bytes do not need modification in this first patch.

Total AMITSE semantic edits: **22 bytes**.

## Save / Restore User Defaults

`Save as User Defaults` and `Restore User Defaults` are not hidden by AMITSE access metadata alone. In the stock 1.17 `Setup` IFR each is wrapped in an outer unconditional suppression:

```text
SuppressIf
    Uint64 Value: 0x1
    ...
    Ref "Save as User Defaults"
```

and independently:

```text
SuppressIf
    Uint64 Value: 0x1
    ...
    Ref "Restore User Defaults"
```

The minimal transformation changes only these two constants:

```text
Uint64 1 -> Uint64 0
```

The nested conditions for setup action `0x14C == 6` and `0x14C == 7`, respectively, are left unchanged.

The patcher finds the complete stock opcode sequences uniquely and changes one byte in each. It does not use the raw IFR offsets as its locator.

Total `Setup` PE32 semantic edits: **2 bytes**.

## Structural repacking

The relevant data is nested under two LZMA GUID-defined sections:

```text
DRFXI.BIN
  -> FFS 9E21FD93-9C72-4C15-8C4B-E77F1DB2D792
     -> LZMA EE4E5898-3914-4259-9D6E-DC7BD79403CF
        -> main DXE firmware volume
           -> Setup
           -> AMITSESetupData FE612B72-203C-47B1-8560-A66D946EB371
              -> LZMA EE4E5898-3914-4259-9D6E-DC7BD79403CF
                 -> Freeform subtype FE612B72-... / SetupData
```

Therefore a direct raw-offset edit of the 32-MiB image is not appropriate.

The patcher:

1. validates the exact input SHA-256;
2. locates and validates the outer volume-image FFS/GUID-defined LZMA section;
3. decompresses the main DXE volume;
4. uniquely locates and patches the two `Setup` IFR patterns;
5. locates `AMITSESetupData` structurally;
6. decompresses its inner LZMA section;
7. validates the exact stock 1.17 SetupData size and SHA-256;
8. locates the 22 target records semantically and verifies every expected old access byte;
9. sets only bit `0x04` in those records;
10. recompresses both LZMA layers;
11. preserves every original section/FFS allocation and pads unused compressed space with erased-state `FF` bytes;
12. fails if either recompressed stream no longer fits its original allocation.

No FFS or section size changes and no downstream file relocation are required.

A no-op version of the same reconstruction procedure was first tested before applying semantic changes. UEFIExtract A75 parsed the rebuilt image with the same structural report and reproduced the exact original decompressed SetupData SHA-256.

## Generated patch and static validation

The current implementation produced:

- patched image SHA-256: `dc70d7d94d146fa3a8f75233f729648695dba07eef7245514121e2fffe7d879f`
- image size: unchanged at `33554432` bytes
- semantic pre-recompression edits: `24` bytes total
  - `22` AMITSE access-byte edits
  - `2` Setup IFR constants

Compression results fit inside the original allocations:

- inner AMITSE allocation: `19715` bytes; recompressed stream: `19527` bytes
- outer volume allocation: `4272454` bytes; recompressed stream: `4262005` bytes

### UEFI structural validation

UEFIExtract NE A75:

- parses stock and patched images without stderr/errors;
- produces an identical structural `report` for stock and patched images;
- observes unchanged firmware, FFS and section sizes.

### Decompressed target diffs

Re-extracted `AMITSESetupData`:

- stock SHA-256: `22879575d33dbe6d711b3f3d45c7bd46f09757d2284ad51aef7ba9358f183973`
- patched SHA-256: `b981b71de6570fb240f8f43996210e81b56283dc47109267f36893efa4c65684`
- exactly **22 bytes differ**;
- every difference is one of `01->05`, `09->0D`, `29->2D` at a selected access byte.

Re-extracted `Setup` PE32:

- stock SHA-256: `23a776d601ec4b0ca086abfb7a5529dfad33dda37be6b0561a509e6b264fa9e1`
- patched SHA-256: `d79ecb9e8cd48af2ce48d1bfb3480e188ed8131e42afe7ab5935233a610e09c7`
- exactly **2 bytes differ**;
- both are `01->00` for the two outer unconditional `Uint64` suppressors.

### IFR re-extraction

IFRExtractor-RS 1.6.1 was rerun on patched `Setup` PE32.

Ignoring the extractor metadata line containing the changed PE SHA-256, the semantic IFR diff contains exactly two changed instructions:

```text
Save as User Defaults:    Uint64 Value 0x1 -> 0x0
Restore User Defaults:   Uint64 Value 0x1 -> 0x0
```

No other IFR opcode differs.

### Leaf-level validation

UEFIExtract's leaf extraction yielded:

- stock leaf files: `6926`
- patched leaf files: `6926`
- path sets: identical
- differing leaf files: exactly `2`

Those two files are only:

1. `Setup/1 PE32 image section/body.bin`
2. `AMITSESetupData/.../FE612B72-.../body.bin`

Every other extracted leaf is byte-identical, including NVRAM/default stores and the rest of the executable/data/ACPI corpus.

This is strong static evidence that the reconstruction does not import or modify donor-board NVRAM/APOB/APCB/boot/security state.

## Excluded community edits

The first clean patch intentionally excludes unrelated community access changes such as:

- CPU Common Options / SMT / Thread Enablement;
- Core Watchdog;
- CPPC Dynamic Preferred Cores;
- TDP / PPT / TjMax / TDC / EDC;
- PROCHOT controls;
- SmartShift and skin-temperature controls;
- other non-memory tuning pages.

Those can be evaluated separately if desired; they are not required for the first memory/FCLK unlock.

## Confidence and limitations

**CONFIRMED:** the community 1.12 target modification is an AMITSE access-bit transformation.

**CONFIRMED:** the selected 1.17 records are located by semantic identifiers and receive only the same access bit used by the community modification.

**CONFIRMED:** the two User Defaults refs are exposed by changing only their two unconditional suppressor constants.

**STRONG STATIC EVIDENCE:** the rebuilt image is structurally parseable and only the two intended decompressed leaf payloads differ from stock.

**NOT PROVEN:** that every newly visible control is safe or functional on this board/hardware combination.

**NOT PROVEN:** that the rebuilt image is safe to flash. Static parser acceptance is not a substitute for platform firmware authentication/integrity checks, recovery planning or hardware validation.

## Before any flashing discussion

At minimum, perform a separate pass for:

1. platform/AMI capsule or flash-path integrity/authentication implications;
2. any board-specific protected/critical firmware ranges and recovery path;
3. independent reconstruction/validation of the produced image from the committed patcher;
4. a known-good backup/readback strategy suitable for this board;
5. confirmation that the intended flashing method does not overwrite unrelated runtime/NVRAM state unnecessarily.

The current result should be treated as a statically validated research image, not as a flashing recommendation.

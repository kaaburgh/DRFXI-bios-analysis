# fwtools — first-party DRFXI firmware helpers

Small, dependency-free Python helpers written for the DRFXI investigation (Python 3.10+, standard library,
system `libarchive` for 7z, binutils `objdump` with `pei-x86-64`). No vendor or third-party analysis tool is
vendored or invoked. They were written because UEFIExtract/IFRExtractor were not available in the 2026-11-22
analysis environment; where results overlap with earlier UEFIExtract-based checkpoints they agree
(18-byte AMD/PSP delta, identical memory PEI modules, identical `AmdSetupRPL` StdDefaults hash).

| script | purpose |
|---|---|
| `un7z.py` | extract a `.7z` package via libarchive (path-traversal checked) |
| `fvparse.py` | walk PI firmware volumes, FFS files, sections, LZMA / LZMA-F86 / AMD-zlib (`ce3233f5-…`) encapsulations; writes leaf payloads + `index.json` |
| `cmpidx.py` | compare two `fvparse` outputs by (UI name or FFS GUID, section kind, copy) |
| `getmod.py` | locate an extracted payload by UI name / GUID |
| `pcdnames.py` | parse the AMI PCD name table (FFS `d45f6c15-…`, sub-GUID `b81c4aa7-…`) and diff token numbering by name |
| `pcd_norm_diff.py` | classify same-size module diffs as PCD-token renumbering only vs residual bytes |
| `asmdiff.py` | normalized instruction diff (RIP displacements and branch targets abstracted) |
| `pspdir.py` | walk `$PSP/$PL2/$BHD/$BL2` directories (address modes 0/1 flash, 2 directory-relative) |
| `apcb.py` | APCB v3 walker (header per linuxboot/fiano), groups/types/board masks/tokens |
| `nvar.py` | AMI NVAR store entries |
| `ifrmini.py` | minimal IFR + HII string reader (questions, varstores, defaults, ranges, options) |
| `cbs_apcb_map.py` | recover the CbsSetupDxeRPL setup-offset → APCB-token push table from disassembly |
| `straightline_eval.py` | evaluate straight-line x64 routines from objdump text (no execution): CBS code defaults (0x3E58) and fingerprint (0x5134) |
| `run_x64_leaf.py` | optional native cross-check of a self-contained leaf function (`--exec-fingerprint`); not required |
| `memory117_evidence.py` | regenerate `evidence/memory-117/` from the two official packages (fail-closed on hashes) |
| `memory_state_report.py` | **read-only diagnostics**: offline report of effective memory configuration from an owner-made SPI dump and/or an efivarfs export of `AmdSetupRPL` |

## Reproducing the 2026-11-22 memory evidence

```bash
python3 -I scripts/fwtools/memory117_evidence.py \
    /path/DRFXI_1.15_260105A.7z /path/DRFXI_1.17_260828A.7z \
    /tmp/drfxi-work evidence/memory-117
```

Keep the work directory outside the repository; it contains complete vendor firmware trees.
Vendor code is not executed: `straightline_eval.py` interprets the disassembly text. `--exec-fingerprint` adds an
optional native cross-check of the fingerprint routine (same results).

## Read-only state report (future hardware checks)

```bash
# AmdSetupRPL exported read-only from Linux efivarfs (4-byte attribute prefix is handled):
cat /sys/firmware/efi/efivars/AmdSetupRPL-3a997502-647a-4c82-998e-52ef9486a247 > AmdSetupRPL.var
# SPI image saved by the owner with the flash utility's save-current-ROM function (reading only)
python3 -I scripts/fwtools/memory_state_report.py --spi saved_rom.bin --amdsetup AmdSetupRPL.var
```

The report never writes anything. The NVAR chain walker has been exercised on official images and on
synthetic update chains only; treat its first real-dump output as a validation run.

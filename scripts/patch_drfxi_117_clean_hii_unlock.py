#!/usr/bin/env python3
"""Minimal, fail-closed HII visibility unlock for official DRFXI 1.17.

Scope:
  * unlock selected AMD UMC/DDR memory pages in AMITSESetupData;
  * unlock SMU Common Options form so existing VDDP/FCLK controls are reachable;
  * make AMI Save/Restore User Defaults refs reachable by changing only the two
    outer always-true Uint64 suppressor constants from 1 to 0.

The script accepts ONLY the exact official DRFXI 1.17 image identified below.
It performs two in-place-size LZMA repacks, preserving all FFS/section sizes and
all offsets outside the compressed byte streams. It does not touch NVRAM/APOB/
APCB/boot/security state.

This is a research artifact. Successful static validation is not a flashing
safety guarantee.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import lzma
from pathlib import Path
import sys
import uuid

INPUT_SHA256 = "99f3bab5ea491202bf365c23e6416f9d1e8a649ad00f90c1f3e21f1a61e35c51"
INPUT_SIZE = 33_554_432
SETUPDATA_SHA256 = "22879575d33dbe6d711b3f3d45c7bd46f09757d2284ad51aef7ba9358f183973"
SETUPDATA_SIZE = 156_412
SETUP_PE_SHA256 = "23a776d601ec4b0ca086abfb7a5529dfad33dda37be6b0561a509e6b264fa9e1"

PARENT_FFS_GUID = uuid.UUID("9E21FD93-9C72-4C15-8C4B-E77F1DB2D792").bytes_le
AMITSE_FFS_GUID = uuid.UUID("FE612B72-203C-47B1-8560-A66D946EB371").bytes_le
LZMA_GUID = uuid.UUID("EE4E5898-3914-4259-9D6E-DC7BD79403CF").bytes_le
SETUP_FFS_GUID = uuid.UUID("899407D7-99FE-43D8-9A21-79EC328CAC21").bytes_le

EXPECTED_PARENT_FFS_SIZE = 0x413176
EXPECTED_OUTER_SECTION_SIZE = 0x41315E
EXPECTED_OUTER_DECOMPRESSED_SIZE = 0xBAB010
EXPECTED_AMITSE_FFS_SIZE = 0x4D33
EXPECTED_AMITSE_SECTION_SIZE = 0x4D1B
EXPECTED_INNER_DECOMPRESSED_SIZE = 0x26334
EXPECTED_FREEFORM_SECTION_SIZE = 0x26310
EXPECTED_FREEFORM_TYPE = 0x18
EXPECTED_SETUP_FFS_SIZE = 0x3CE0E
EXPECTED_SETUP_PE_SIZE = 249_152

LZMA_FILTERS = [{
    "id": lzma.FILTER_LZMA1,
    "dict_size": 0x1000000,
    "lc": 3,
    "lp": 0,
    "pb": 2,
    "mode": lzma.MODE_NORMAL,
    "nice_len": 273,
    "mf": lzma.MF_BT4,
    "depth": 0,
}]

# Records are matched semantically using the same stable fields used by
# BoringBoredom/UEFI-Editor getAdditionalData(): QID, Help StringId, Prompt StringId.
QUESTION_RECORDS = [
    # label, question_id, prompt_id, help_id, expected_access
    ("UMC Common Options",                    0x0003, 0x000B, 0x000B, 0x01),
    ("DDR Options",                           0x0037, 0x00A5, 0x00A5, 0x01),
    ("DDR Controller Configuration",          0x003A, 0x00A8, 0x00A8, 0x01),
    ("DDR Power Options",                     0x0084, 0x0157, 0x0157, 0x01),
    ("Power Down Enable",                     0x0085, 0x0158, 0x0159, 0x09),
    ("DDR RAS",                               0x003B, 0x00A9, 0x00A9, 0x01),
    ("DDR ECC Configuration",                 0x0087, 0x015C, 0x015C, 0x01),
    ("ECC",                                   0x0088, 0x015D, 0x015E, 0x09),
    ("DDR Security",                          0x003C, 0x00AA, 0x00AA, 0x01),
    ("TSME",                                  0x7022, 0x015F, 0x0160, 0x29),
    ("Data Scramble",                         0x7023, 0x0161, 0x0162, 0x29),
    ("DDR Memory Features",                   0x0040, 0x00AE, 0x00AE, 0x01),
    ("Memory Context Restore",                0x009B, 0x0196, 0x0197, 0x09),
]

# Form records have QID=0 and type=8. The context/page-index field at +0x0A,
# together with prompt StringId, uniquely identifies the intended 1.17 record.
FORM_RECORDS = [
    # label, context, prompt_id, expected_access
    ("FORM UMC Common Options",               0x003E, 0x000B, 0x01),
    ("FORM DDR Options",                      0x003F, 0x00A5, 0x01),
    ("FORM DDR Controller Configuration",     0x0046, 0x00A8, 0x01),
    ("FORM DDR Power Options",                0x0047, 0x0157, 0x01),
    ("FORM DDR RAS",                          0x0048, 0x00A9, 0x01),
    ("FORM DDR ECC Configuration",            0x0049, 0x015C, 0x01),
    ("FORM DDR Security",                     0x004A, 0x00AA, 0x01),
    ("FORM DDR Memory Features",              0x004F, 0x00AE, 0x01),
    ("FORM SMU Common Options",               0x005E, 0x000E, 0x01),
]

SAVE_PATTERN = bytes.fromhex(
    "0a82450a01000000000000000a8212064c010600"
    "0f0f69006a0046010000ffff00162729022902"
)
RESTORE_PATTERN = bytes.fromhex(
    "0a82450a01000000000000000a8212064c010700"
    "0f0f6b006c0047010000ffff00162729022902"
)


def sha256(data: bytes | bytearray) -> str:
    return hashlib.sha256(data).hexdigest()


def u24(data: bytes | bytearray, off: int) -> int:
    return int.from_bytes(data[off:off+3], "little")


def u16(data: bytes | bytearray, off: int) -> int:
    return int.from_bytes(data[off:off+2], "little")


def all_hits(data: bytes | bytearray, needle: bytes) -> list[int]:
    hits: list[int] = []
    pos = 0
    while True:
        pos = data.find(needle, pos)
        if pos < 0:
            return hits
        hits.append(pos)
        pos += 1


def unique_guid_ffs(data: bytes | bytearray, guid: bytes, *, ffs_type: int, state: int = 0xF8) -> int:
    hits = []
    for off in all_hits(data, guid):
        if off + 24 <= len(data) and data[off+18] == ffs_type and data[off+23] == state:
            hits.append(off)
    if len(hits) != 1:
        raise ValueError(f"FFS {uuid.UUID(bytes_le=guid)}: expected 1 structural match, got {hits}")
    return hits[0]


def validate_lzma_section(data: bytes | bytearray, sec: int, expected_size: int) -> tuple[int, int]:
    size = u24(data, sec)
    if size != expected_size:
        raise ValueError(f"LZMA section at {sec:#x}: size {size:#x}, expected {expected_size:#x}")
    if data[sec+3] != 0x02:
        raise ValueError(f"LZMA section at {sec:#x}: type {data[sec+3]:#x}, expected 0x02")
    if data[sec+4:sec+20] != LZMA_GUID:
        raise ValueError(f"LZMA section at {sec:#x}: unexpected GUID")
    if u16(data, sec+20) != 24 or u16(data, sec+22) != 1:
        raise ValueError(f"LZMA section at {sec:#x}: unexpected data offset/attributes")
    return sec + 24, size - 24


def compress_padded(raw: bytes, allocated: int) -> tuple[bytes, int]:
    comp = bytearray(lzma.compress(raw, format=lzma.FORMAT_ALONE, filters=LZMA_FILTERS))
    # UEFITool's LZMA compressor writes the exact decompressed size into the
    # 8-byte FORMAT_ALONE size field rather than Python's unknown-size value.
    comp[5:13] = len(raw).to_bytes(8, "little")
    if len(comp) > allocated:
        raise ValueError(f"recompressed LZMA grew beyond allocation: {len(comp)} > {allocated}")
    padded = bytes(comp) + (b"\xff" * (allocated - len(comp)))
    if lzma.decompress(padded, format=lzma.FORMAT_ALONE) != raw:
        raise ValueError("LZMA round-trip validation failed")
    return padded, len(comp)


def find_question_record(body: bytes | bytearray, qid: int, prompt: int, help_id: int) -> int:
    hits = []
    for off in range(0, len(body) - 54 + 1):
        if (u16(body, off) == qid and
            u16(body, off+20) == help_id and
            u16(body, off+48) == prompt):
            hits.append(off)
    if len(hits) != 1:
        raise ValueError(
            f"record qid={qid:#x}, prompt={prompt:#x}, help={help_id:#x}: expected 1, got {hits}"
        )
    return hits[0]


def find_form_record(body: bytes | bytearray, context: int, prompt: int) -> int:
    hits = []
    for off in range(0, len(body) - 54 + 1):
        if (u16(body, off) == 0 and
            u16(body, off+8) == 0x08 and
            u16(body, off+10) == context and
            u16(body, off+12) == 0xFFFF and
            u16(body, off+20) == 0 and
            u16(body, off+48) == prompt):
            hits.append(off)
    if len(hits) != 1:
        raise ValueError(f"form context={context:#x}, prompt={prompt:#x}: expected 1, got {hits}")
    return hits[0]


def patch_access_records(body: bytearray, report: list[dict]) -> None:
    for label, qid, prompt, help_id, expected in QUESTION_RECORDS:
        off = find_question_record(body, qid, prompt, help_id)
        access_off = off + 16
        old = body[access_off]
        if old != expected:
            raise ValueError(f"{label}: access {old:#x}, expected stock {expected:#x}")
        new = old | 0x04
        if new == old:
            raise ValueError(f"{label}: visibility bit already set")
        body[access_off] = new
        report.append({
            "kind": "AMITSESetupData access",
            "label": label,
            "semantic_key": {"question_id": qid, "prompt_string_id": prompt, "help_string_id": help_id},
            "record_offset": off,
            "byte_offset": access_off,
            "old": old,
            "new": new,
        })

    for label, context, prompt, expected in FORM_RECORDS:
        off = find_form_record(body, context, prompt)
        access_off = off + 16
        old = body[access_off]
        if old != expected:
            raise ValueError(f"{label}: access {old:#x}, expected stock {expected:#x}")
        new = old | 0x04
        if new == old:
            raise ValueError(f"{label}: visibility bit already set")
        body[access_off] = new
        report.append({
            "kind": "AMITSESetupData access",
            "label": label,
            "semantic_key": {"record_type": 8, "context": context, "prompt_string_id": prompt},
            "record_offset": off,
            "byte_offset": access_off,
            "old": old,
            "new": new,
        })


def iter_ffs_sections(ffs: bytes | bytearray):
    off = 24
    while off + 4 <= len(ffs):
        size = u24(ffs, off)
        if size < 4 or off + size > len(ffs):
            raise ValueError(f"malformed section at FFS+{off:#x}: size={size:#x}")
        yield off, size, ffs[off+3], off + 4, size - 4
        off = (off + size + 3) & ~3
    if off not in {len(ffs), (len(ffs) + 3) & ~3}:
        raise ValueError(f"unexpected end of FFS section stream: {off:#x} vs {len(ffs):#x}")


def locate_stock_setup_pe(outer: bytes | bytearray) -> tuple[int, int, int, int]:
    setup = unique_guid_ffs(outer, SETUP_FFS_GUID, ffs_type=0x07)
    setup_size = u24(outer, setup + 20)
    if setup_size != EXPECTED_SETUP_FFS_SIZE:
        raise ValueError(f"Setup FFS size {setup_size:#x}, expected {EXPECTED_SETUP_FFS_SIZE:#x}")
    ffs = outer[setup:setup+setup_size]
    pe_sections = []
    for sec_off, sec_size, sec_type, body_off, body_len in iter_ffs_sections(ffs):
        if sec_type == 0x10:
            pe = bytes(ffs[body_off:body_off+body_len])
            pe_sections.append((sec_off, sec_size, body_off, body_len, sha256(pe)))
    exact = [x for x in pe_sections if x[3] == EXPECTED_SETUP_PE_SIZE and x[4] == SETUP_PE_SHA256]
    if len(exact) != 1:
        raise ValueError(f"Setup: expected one stock PE32 section, got {pe_sections}")
    sec_off, sec_size, body_off, body_len, _ = exact[0]
    return setup, setup_size, setup + body_off, body_len


def patch_user_defaults(setup_pe: bytearray, report: list[dict]) -> None:
    for label, pat in (("Save as User Defaults", SAVE_PATTERN), ("Restore User Defaults", RESTORE_PATTERN)):
        hits = all_hits(setup_pe, pat)
        if len(hits) != 1:
            raise ValueError(f"{label}: expected one exact suppression pattern in Setup PE32, got {hits}")
        start = hits[0]
        value_off = start + 4  # 0A82 450A [Uint64 value starts here]
        if setup_pe[value_off:value_off+8] != b"\x01\x00\x00\x00\x00\x00\x00\x00":
            raise ValueError(f"{label}: expected Uint64(1) at Setup PE32+{value_off:#x}")
        setup_pe[value_off] = 0
        report.append({
            "kind": "Setup IFR suppression constant",
            "label": label,
            "pattern_offset_in_setup_pe32": start,
            "byte_offset_in_setup_pe32": value_off,
            "old": 1,
            "new": 0,
        })


def patch_image(src: bytes) -> tuple[bytes, dict]:
    if len(src) != INPUT_SIZE:
        raise ValueError(f"input size {len(src)}, expected {INPUT_SIZE}")
    got_sha = sha256(src)
    if got_sha != INPUT_SHA256:
        raise ValueError(f"input SHA-256 {got_sha}, expected official 1.17 {INPUT_SHA256}")

    bios = bytearray(src)
    changes: list[dict] = []

    parent = unique_guid_ffs(bios, PARENT_FFS_GUID, ffs_type=0x0B)
    parent_size = u24(bios, parent+20)
    if parent_size != EXPECTED_PARENT_FFS_SIZE:
        raise ValueError(f"parent FFS size {parent_size:#x}, expected {EXPECTED_PARENT_FFS_SIZE:#x}")
    outer_body_off, outer_body_len = validate_lzma_section(
        bios, parent + 24, EXPECTED_OUTER_SECTION_SIZE
    )
    outer_raw = lzma.decompress(bytes(bios[outer_body_off:outer_body_off+outer_body_len]), format=lzma.FORMAT_ALONE)
    if len(outer_raw) != EXPECTED_OUTER_DECOMPRESSED_SIZE:
        raise ValueError(f"outer decompressed size {len(outer_raw):#x}")
    outer = bytearray(outer_raw)

    # Validate the exact stock Setup PE32 payload independently of the outer
    # firmware hash, then patch only within that PE32 section.
    setup_ffs_off, setup_ffs_size, setup_pe_off, setup_pe_len = locate_stock_setup_pe(outer)
    setup_pe = bytearray(outer[setup_pe_off:setup_pe_off+setup_pe_len])
    patch_user_defaults(setup_pe, changes)
    outer[setup_pe_off:setup_pe_off+setup_pe_len] = setup_pe

    amitse = unique_guid_ffs(outer, AMITSE_FFS_GUID, ffs_type=0x02)
    amitse_size = u24(outer, amitse+20)
    if amitse_size != EXPECTED_AMITSE_FFS_SIZE:
        raise ValueError(f"AMITSE FFS size {amitse_size:#x}, expected {EXPECTED_AMITSE_FFS_SIZE:#x}")
    inner_body_off, inner_body_len = validate_lzma_section(
        outer, amitse + 24, EXPECTED_AMITSE_SECTION_SIZE
    )
    inner_raw = lzma.decompress(bytes(outer[inner_body_off:inner_body_off+inner_body_len]), format=lzma.FORMAT_ALONE)
    if len(inner_raw) != EXPECTED_INNER_DECOMPRESSED_SIZE:
        raise ValueError(f"AMITSE decompressed size {len(inner_raw):#x}")
    inner = bytearray(inner_raw)

    if u24(inner, 0) != EXPECTED_FREEFORM_SECTION_SIZE or inner[3] != EXPECTED_FREEFORM_TYPE:
        raise ValueError("unexpected leading AMITSE freeform section header")
    if inner[4:20] != AMITSE_FFS_GUID:
        raise ValueError("unexpected AMITSE freeform subtype GUID")
    setupdata = bytearray(inner[20:EXPECTED_FREEFORM_SECTION_SIZE])
    if len(setupdata) != SETUPDATA_SIZE or sha256(setupdata) != SETUPDATA_SHA256:
        raise ValueError("stock 1.17 SetupData body does not match expected hash/size")

    patch_access_records(setupdata, changes)
    patched_setupdata_sha = sha256(setupdata)
    inner[20:EXPECTED_FREEFORM_SECTION_SIZE] = setupdata

    inner_padded, inner_comp_size = compress_padded(bytes(inner), inner_body_len)
    outer[inner_body_off:inner_body_off+inner_body_len] = inner_padded

    # Re-verify the exact stock patterns no longer remain in the validated Setup PE32.
    if SAVE_PATTERN in setup_pe or RESTORE_PATTERN in setup_pe:
        raise ValueError("stock user-default suppression pattern unexpectedly remains after patch")

    outer_padded, outer_comp_size = compress_padded(bytes(outer), outer_body_len)
    bios[outer_body_off:outer_body_off+outer_body_len] = outer_padded

    result = bytes(bios)
    report = {
        "tool": "patch_drfxi_117_clean_hii_unlock.py",
        "input": {"size": len(src), "sha256": got_sha},
        "output": {"size": len(result), "sha256": sha256(result)},
        "scope": {
            "access_changes": len(QUESTION_RECORDS) + len(FORM_RECORDS),
            "setup_suppression_changes": 2,
            "total_semantic_byte_changes_before_recompression": len(changes),
        },
        "containers": {
            "outer_parent_ffs_offset": parent,
            "outer_allocated_compressed_bytes": outer_body_len,
            "outer_recompressed_bytes": outer_comp_size,
            "setup_ffs_offset_in_outer_decompressed": setup_ffs_off,
            "setup_ffs_size": setup_ffs_size,
            "stock_setup_pe32_sha256": SETUP_PE_SHA256,
            "setup_pe32_offset_in_outer_decompressed": setup_pe_off,
            "setup_pe32_size": setup_pe_len,
            "patched_setup_pe32_sha256": sha256(setup_pe),
            "amitse_ffs_offset_in_outer_decompressed": amitse,
            "amitse_allocated_compressed_bytes": inner_body_len,
            "amitse_recompressed_bytes": inner_comp_size,
            "stock_setupdata_sha256": SETUPDATA_SHA256,
            "patched_setupdata_sha256": patched_setupdata_sha,
        },
        "changes": changes,
        "warnings": [
            "Static structural validation is still required after generation.",
            "This output has not been hardware-tested and is not asserted safe to flash.",
        ],
    }
    return result, report


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("input", type=Path, help="official DRFXI 1.17 DRFXI.BIN")
    ap.add_argument("output", type=Path, help="patched output image")
    ap.add_argument("--report", type=Path, help="JSON patch report path")
    args = ap.parse_args()

    try:
        src = args.input.read_bytes()
        result, report = patch_image(src)
    except (OSError, ValueError, lzma.LZMAError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    args.output.write_bytes(result)
    report_path = args.report or args.output.with_suffix(args.output.suffix + ".patch-report.json")
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"input_sha256={report['input']['sha256']}")
    print(f"output_sha256={report['output']['sha256']}")
    print(f"semantic_changes={len(report['changes'])}")
    print(f"output={args.output}")
    print(f"report={report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

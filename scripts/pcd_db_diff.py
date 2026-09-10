#!/usr/bin/env python3
"""Semantic scalar diff for EDK II BuildVersion-7 external PCD databases.

Used for the DRFXI 1.12 -> 1.15 PcdPeim analysis. The parser follows
MdeModulePkg/Include/Guid/PcdDataBaseSignatureGuid.h. It deliberately excludes
local token numbers and physical offsets from sequence alignment so insertion
of Dynamic tokens does not look like hundreds of changed defaults.
"""

from __future__ import annotations
import argparse, difflib, hashlib, json, struct
from pathlib import Path

SIGNATURE = bytes.fromhex("3c197d3c2c68144ca68f552dea4f437e")
TYPE_MASK = 0xD0000000
DATUM_MASK = 0x0F000000
BOOL_FLAG = 0x00100000
OFFSET_MASK = (~(TYPE_MASK | DATUM_MASK | BOOL_FLAG)) & 0xffffffff
DATA = 0x00000000
SIZES = {0x01000000: 1, 0x02000000: 2, 0x04000000: 4, 0x08000000: 8}
NAMES = {0x01000000: "UINT8", 0x02000000: "UINT16", 0x04000000: "UINT32", 0x08000000: "UINT64"}


def guid_le(raw: bytes) -> str:
    a, b, c = struct.unpack_from("<IHH", raw)
    d = raw[8:]
    return f"{a:08x}-{b:04x}-{c:04x}-{d[:2].hex()}-{d[2:].hex()}"


def parse(path: Path):
    blob = path.read_bytes()
    if blob[:16] != SIGNATURE:
        raise ValueError("PCD database signature mismatch")
    vals = struct.unpack_from("<IIQ9IHHH6s", blob, 16)
    keys = ["BuildVersion", "Length", "SystemSkuId", "LengthForAllSkus",
            "UninitDataBaseSize", "LocalTokenNumberTableOffset", "ExMapTableOffset",
            "GuidTableOffset", "StringTableOffset", "SizeTableOffset", "SkuIdTableOffset",
            "PcdNameTableOffset", "LocalTokenCount", "ExTokenCount", "GuidTableCount", "Pad"]
    h = dict(zip(keys, vals))
    if h["BuildVersion"] != 7 or h["Length"] != len(blob):
        raise ValueError("unsupported/corrupt PCD database")

    guids = [guid_le(blob[h["GuidTableOffset"] + 16*i:h["GuidTableOffset"] + 16*(i+1)])
             for i in range(h["GuidTableCount"])]
    ex = []
    for i in range(h["ExTokenCount"]):
        n, local, gi = struct.unpack_from("<IHH", blob, h["ExMapTableOffset"] + 8*i)
        ex.append((guids[gi], n, local))

    raw_tokens = struct.unpack_from(f"<{h['LocalTokenCount']}I", blob, h["LocalTokenNumberTableOffset"])
    tokens = []
    for num, desc in enumerate(raw_tokens, 1):
        typ, datum = desc & TYPE_MASK, desc & DATUM_MASK
        off = desc & OFFSET_MASK
        scalar = typ == DATA and datum in SIZES
        rec = {"token_number": num, "descriptor": f"0x{desc:08x}", "type": typ,
               "datum": "BOOLEAN" if desc & BOOL_FLAG else NAMES.get(datum, f"0x{datum:x}"),
               "offset": off, "scalar": scalar}
        if scalar:
            size = SIZES[datum]
            init = off < h["Length"]
            value = int.from_bytes(blob[off:off+size], "little") if init else 0
            rec.update(size=size, initialized=init, value=value)
        tokens.append(rec)
    return {"path": str(path), "sha256": hashlib.sha256(blob).hexdigest(), "header": h,
            "ex": ex, "tokens": tokens}


def sig(t):
    return (t["type"], t["datum"], t.get("value"), t.get("initialized"))


def cat(t):
    return (t["type"], t["datum"])


def diff(a, b):
    sm = difflib.SequenceMatcher(a=[sig(x) for x in a["tokens"]],
                                 b=[sig(x) for x in b["tokens"]], autojunk=False)
    inserted, deleted, changes, equal = [], [], [], 0
    for tag, a0, a1, b0, b1 in sm.get_opcodes():
        if tag == "equal":
            equal += a1-a0
        elif tag == "insert":
            inserted.extend(b["tokens"][b0:b1])
        elif tag == "delete":
            deleted.extend(a["tokens"][a0:a1])
        elif tag == "replace" and (a1-a0) == (b1-b0):
            for x, y in zip(a["tokens"][a0:a1], b["tokens"][b0:b1]):
                if cat(x) == cat(y) and x["scalar"] and y["scalar"]:
                    changes.append({"old_token": x["token_number"], "new_token": y["token_number"],
                                    "descriptor_old": x["descriptor"], "descriptor_new": y["descriptor"],
                                    "datum": x["datum"], "offset_old": x["offset"], "offset_new": y["offset"],
                                    "old_value": x["value"], "new_value": y["value"]})
                else:
                    deleted.append(x); inserted.append(y)
        else:
            deleted.extend(a["tokens"][a0:a1]); inserted.extend(b["tokens"][b0:b1])

    ae = {(g,n): local for g,n,local in a["ex"]}
    be = {(g,n): local for g,n,local in b["ex"]}
    shifts = {}
    if set(ae) == set(be):
        for k in ae:
            d = be[k] - ae[k]
            shifts[d] = shifts.get(d, 0) + 1
    return {"old_sha256": a["sha256"], "new_sha256": b["sha256"],
            "headers": {"old": {k:v for k,v in a["header"].items() if k != "Pad"},
                        "new": {k:v for k,v in b["header"].items() if k != "Pad"}},
            "normalization": {"equal_records": equal, "inserted": len(inserted),
                              "deleted": len(deleted), "dynamic_ex_keys_equal": set(ae) == set(be),
                              "dynamic_ex_local_token_shifts": shifts},
            "scalar_value_changes": changes, "inserted_tokens": inserted, "deleted_tokens": deleted}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("old", type=Path); ap.add_argument("new", type=Path)
    ap.add_argument("--json", type=Path)
    ns = ap.parse_args()
    a, b = parse(ns.old), parse(ns.new)
    d = diff(a, b)
    print(f"old tokens={a['header']['LocalTokenCount']} sha256={a['sha256']}")
    print(f"new tokens={b['header']['LocalTokenCount']} sha256={b['sha256']}")
    print("DynamicEx local-token shifts:", d["normalization"]["dynamic_ex_local_token_shifts"])
    print("Inserted tokens:")
    for t in d["inserted_tokens"]:
        print(" ", t)
    print("Changed scalar defaults:")
    for c in d["scalar_value_changes"]:
        print(" ", c)
    if ns.json:
        ns.json.write_text(json.dumps(d, indent=2) + "\n")

if __name__ == "__main__":
    main()

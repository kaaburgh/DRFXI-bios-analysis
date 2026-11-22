#!/usr/bin/env python3
"""Minimal first-party UEFI IFR/HII-string reader for one PE image (e.g. CbsSetupDxeRPL).
Finds the en-US string package and every IFR FormSet blob, then lists questions
(OneOf/Numeric/CheckBox) with VarStoreId, VarOffset, width, prompt, default and option list.
usage: ifrmini.py PE [--varstore NAME] [--json OUT]"""
import struct, sys, json, uuid
def strings_pkg(b):
    out = {}
    i = 0
    while True:
        i = b.find(b"en-US\0", i)
        if i < 0: break
        # header: u32 len|type, u32 hdrsize, u32 strinfo_off, CHAR16 win[16], u16 langname
        h = i - 46
        if h >= 0:
            lt = struct.unpack_from("<I", b, h)[0]; ln, ty = lt & 0xFFFFFF, lt >> 24
            hs, so = struct.unpack_from("<II", b, h + 4)
            if ty == 4 and hs == 52 and so == 52 and ln < len(b):
                o = h + so; sid = 1; strs = {}
                while o < h + ln:
                    bt = b[o]
                    if bt == 0x00: break
                    if bt == 0x14:  # SIBT_STRING_UCS2
                        e = o + 1
                        while b[e:e+2] != b"\0\0": e += 2
                        strs[sid] = b[o+1:e].decode("utf-16-le", "replace"); sid += 1; o = e + 2
                    elif bt == 0x15:  # SIBT_STRING_UCS2_FONT
                        e = o + 2
                        while b[e:e+2] != b"\0\0": e += 2
                        strs[sid] = b[o+2:e].decode("utf-16-le", "replace"); sid += 1; o = e + 2
                    elif bt == 0x22: sid += b[o+1]; o += 2      # SKIP1
                    elif bt == 0x21: sid += struct.unpack_from("<H", b, o+1)[0]; o += 3  # SKIP2
                    elif bt == 0x30: o += 1 + 16 + 4 + 1 # EXT? (not expected)
                    elif bt == 0x40: o += 3  # DUPLICATE
                    else: break
                if len(strs) > len(out): out = strs
        i += 6
    return out
def ifr(b, start):
    """Parse IFR opcodes beginning at a FORM_SET opcode; returns (varstores, questions)."""
    o = start; vs = {}; qs = []; cur = None; depth = 0
    while o + 2 <= len(b):
        op = b[o]; ln = b[o+1] & 0x7F; scope = b[o+1] >> 7
        if ln < 2: break
        body = b[o+2:o+ln]
        if op == 0x24:  # VARSTORE
            g = uuid.UUID(bytes_le=bytes(body[:16])); vid, size = struct.unpack_from("<HH", body, 16)
            name = body[20:].split(b"\0")[0].decode("latin1"); vs[vid] = dict(name=name, guid=str(g), size=size)
        elif op == 0x26:  # VARSTORE_EFI
            vid = struct.unpack_from("<H", body, 0)[0]; g = uuid.UUID(bytes_le=bytes(body[2:18]))
            attr, size = struct.unpack_from("<IH", body, 18); name = body[24:].split(b"\0")[0].decode("latin1")
            vs[vid] = dict(name=name, guid=str(g), size=size)
        elif op in (0x05, 0x07, 0x06):  # ONE_OF, NUMERIC, CHECKBOX
            prompt, help_, qid, vid, voff, flags = struct.unpack_from("<HHHHHB", body, 0)
            dflags = body[10] if op != 0x06 else 0   # numeric/oneof data flags follow the 10-byte header + 1 flag byte
            dflags = body[11] if op != 0x06 and len(body) > 11 else 0
            width = {0: 1, 1: 2, 2: 4, 3: 8}.get(dflags & 3, 1) if op != 0x06 else 1
            rng = None
            if op in (0x05, 0x07):
                sz = 1 << (dflags & 3); p = 12
                fmt = {1: "<BBB", 2: "<HHH", 4: "<III", 8: "<QQQ"}[sz]
                if len(body) >= p + 3 * sz: rng = struct.unpack_from(fmt, body, p)
            cur = dict(op={5: "oneof", 7: "numeric", 6: "checkbox"}[op], prompt=prompt, qid=qid, varstore=vid,
                       offset=voff, width=width, range=rng, options=[], default=None)
            qs.append(cur)
        elif op == 0x09 and cur is not None:  # ONE_OF_OPTION
            sid, oflags, otype = struct.unpack_from("<HBB", body, 0)
            val = int.from_bytes(body[4:4 + {0: 1, 1: 2, 2: 4, 3: 8}.get(otype, 1)], "little")
            cur["options"].append((sid, val, oflags))
            if oflags & 0x10: cur["default"] = val
        elif op == 0x5B and cur is not None:  # DEFAULT
            did, typ = struct.unpack_from("<HB", body, 0)
            cur["default"] = int.from_bytes(body[3:3 + {0: 1, 1: 2, 2: 4, 3: 8}.get(typ, 1)], "little")
        if scope: depth += 1
        if op == 0x29:
            depth -= 1
            if depth <= 0: break
        o += ln
    return vs, qs
def find_formsets(b):
    out = []; i = 0
    while True:
        i = b.find(b"\x0e", i)
        if i < 0: break
        ln = b[i+1] & 0x7F
        if (b[i+1] & 0x80) and ln in (23 + 16 * k for k in range(0, 4)) and b[i+ln] in (0x24, 0x26, 0x01, 0x5c, 0x27, 0x25, 0x0f, 0x5d, 0x5f):
            out.append(i)
        i += 1
    return out
def main():
    b = open(sys.argv[1], "rb").read(); S = strings_pkg(b)
    want = sys.argv[sys.argv.index("--varstore") + 1] if "--varstore" in sys.argv else None
    rows = []; seen = set()
    for fs in find_formsets(b):
        vs, qs = ifr(b, fs)
        for q in qs:
            v = vs.get(q["varstore"], {}).get("name", "?%d" % q["varstore"])
            if want and v != want: continue
            key = (v, q["offset"], q["prompt"])
            if key in seen: continue
            seen.add(key)
            rows.append(dict(varstore=v, offset=q["offset"], width=q["width"], kind=q["op"], prompt=S.get(q["prompt"], "#%d" % q["prompt"]),
                             default=q["default"], range=q["range"], options=[(S.get(s, "#%d" % s), val) for s, val, f in q["options"]]))
    rows.sort(key=lambda r: (r["varstore"], r["offset"]))
    if "--json" in sys.argv: json.dump(rows, open(sys.argv[sys.argv.index("--json") + 1], "w"), indent=1)
    for r in rows:
        opts = ", ".join("%s=0x%X" % (n, v) for n, v in r["options"][:6]) + (" …" if len(r["options"]) > 6 else "")
        print("%-12s 0x%04X w%d %-8s %-48s def=%s %s %s" % (r["varstore"], r["offset"], r["width"], r["kind"], r["prompt"][:48], r["default"], r["range"] or "", opts))
if __name__ == "__main__": main()

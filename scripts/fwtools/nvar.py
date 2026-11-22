#!/usr/bin/env python3
"""Minimal AMI NVAR store parser. usage: nvar.py FILE [--dump NAME OUT]
Entry: 'NVAR' u16 size, u24 next, u8 attr; attr bits: 01 RT, 02 ASCII name, 04 GUID inline,
08 data-only, 10 ext hdr, 20 HW err, 40 auth, 80 valid. GUID index refers to the GUID table
growing downward from the end of the store."""
import sys, struct, uuid, hashlib
def parse(b):
    out = []; o = 0
    while True:
        o = b.find(b"NVAR", o)
        if o < 0: break
        size, = struct.unpack_from("<H", b, o+4); nxt = int.from_bytes(b[o+6:o+9], "little"); attr = b[o+9]
        if size < 10 or o + size > len(b): o += 4; continue
        body = b[o+10:o+size]; name = None; g = None; p = 0
        if not attr & 0x08:
            if attr & 0x04: g = str(uuid.UUID(bytes_le=bytes(body[:16]))); p = 16
            else:
                gi = body[0]; p = 1
                gt = len(b) - 16 * (gi + 1); g = "idx%d:%s" % (gi, uuid.UUID(bytes_le=bytes(b[gt:gt+16])))
            if attr & 0x02:
                e = body.index(b"\0", p); name = body[p:e].decode("latin1"); p = e + 1
            else:
                e = p
                while body[e:e+2] != b"\0\0": e += 2
                name = body[p:e].decode("utf-16-le"); p = e + 2
        data = body[p:]
        if attr & 0x10 and len(data) >= 3:
            ext = struct.unpack_from("<H", data, len(data)-2)[0]
            if 0 < ext <= len(data): data = data[:len(data)-ext]
        out.append(dict(off=o, size=size, next=nxt, attr=attr, guid=g, name=name, data=data)); o += size
    return out
if __name__ == "__main__":
    b = open(sys.argv[1], "rb").read()
    for e in parse(b):
        print("%06X size=%5d next=%06X attr=%02X %-34s %-46s len=%5d sha=%s" % (e["off"], e["size"], e["next"], e["attr"], e["name"], e["guid"], len(e["data"]), hashlib.sha256(e["data"]).hexdigest()[:12]))
        if len(sys.argv) > 3 and sys.argv[2] == "--dump" and e["name"] == sys.argv[3]: open(sys.argv[4], "wb").write(e["data"])

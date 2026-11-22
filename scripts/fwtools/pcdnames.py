#!/usr/bin/env python3
"""Parse the AMI PCD name blob (FFS d45f6c15-..., freeform sub-GUID b81c4aa7-...) found in the PEI volume.
Layout (observed): u64 hdr_size(0x30), u64 ?, u64 count, ... then count * 90-byte records:
u16 global_token, char name[48], char token_space[40].
usage: pcdnames.py BLOB [BLOB_B]  -> prints table, or name-level diff when two blobs are given."""
import struct, sys
def parse(path):
    b = open(path, "rb").read(); hs, _, cnt = struct.unpack_from("<QQQ", b, 0); out = {}
    o = 0x18
    for i in range(cnt):
        tok = struct.unpack_from("<H", b, o)[0]
        name = b[o+2:o+50].split(b"\0")[0].decode(); sp = b[o+50:o+90].split(b"\0")[0].decode()
        out[(sp, name)] = tok; o += 90
    return out
if __name__ == "__main__":
    a = parse(sys.argv[1])
    if len(sys.argv) == 2:
        for (sp, n), t in sorted(a.items(), key=lambda x: x[1]): print("0x%03X %s.%s" % (t, sp, n))
    else:
        b = parse(sys.argv[2])
        for k in sorted(set(a) - set(b)): print("REMOVED 0x%03X %s.%s" % (a[k], *k))
        for k in sorted(set(b) - set(a)): print("ADDED   0x%03X %s.%s" % (b[k], *k))
        sh = {}
        for k in set(a) & set(b): sh.setdefault(b[k] - a[k], []).append(a[k])
        for d, v in sorted(sh.items()): print("shift %+d: %d tokens, old range 0x%X..0x%X" % (d, len(v), min(v), max(v)))

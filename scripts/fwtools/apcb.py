#!/usr/bin/env python3
"""APCB v3 walker (layout per linuxboot/fiano pkg/amd/apcb/internal.go).
Header: 'APCB' u16 hdrsize u16 ver u32 size u32 UniqueAPCBInstance u8 cksum ... V3 ext 'ECB2' ... data at hdrsize.
Group: sig u16 gid u16 hsz u16 ver u16 rsv u32 size. Type (16 B): u16 gid u16 tid u16 size u16 inst,
u8 ctxType u8 ctxFmt u8 unit u8 prioMask u8 keySize u8 keyPos u16 boardMask.
Token group 0x3000: tid 0 bool / 1 u8 / 2 u16 / 4 u32, entries (u32 id, u32 value).
usage: apcb.py IMAGE OFFSET [--tokens]"""
import struct, sys, hashlib
def walk(d, base):
    sig, hsz, ver, size, uid, ck = struct.unpack_from("<4sHHIIB", d, base)
    assert sig == b"APCB", sig
    blob = d[base:base+size]
    info = dict(base=base, hdr_size=hsz, version=ver, size=size, unique_id=uid, checksum=ck,
                bytesum=sum(blob) & 0xFF, sha_payload=hashlib.sha256(blob[hsz:]).hexdigest())
    groups = []; o = hsz
    while o + 16 <= size:
        gsig, gid, ghs, gver, grsv, gsize = struct.unpack_from("<4sHHHHI", blob, o)
        if gsize < 16 or o + gsize > size: break
        types = []; t = o + ghs
        while t + 16 <= o + gsize:
            tg, tid, tsz, inst, ctyp, cfmt, unit, prio, ksz, kpos, bmask = struct.unpack_from("<HHHHBBBBBBH", blob, t)
            if tsz < 16: break
            body = blob[t+16:t+tsz]; toks = []
            if gid == 0x3000:
                for k in range(0, len(body) - 7, 8): toks.append(struct.unpack_from("<II", body, k))
            types.append(dict(gid=tg, tid=tid, size=tsz, inst=inst, prio=prio, board=bmask, ctx=(ctyp, cfmt, unit),
                              sha=hashlib.sha256(body).hexdigest()[:12], tokens=toks))
            t += (tsz + 3) & ~3
        groups.append(dict(sig=gsig.decode("latin1"), gid=gid, size=gsize, types=types)); o += gsize
    info["groups"] = groups; return info
if __name__ == "__main__":
    d = open(sys.argv[1], "rb").read(); i = walk(d, int(sys.argv[2], 0))
    print("APCB@%X ver=%X size=%X UniqueAPCBInstance=0x%X checksum=0x%02X bytesum=0x%02X payload_sha=%s" % (i["base"], i["version"], i["size"], i["unique_id"], i["checksum"], i["bytesum"], i["sha_payload"][:16]))
    for g in i["groups"]:
        print(" group %s 0x%04X size=%X types=%d" % (g["sig"], g["gid"], g["size"], len(g["types"])))
        for t in g["types"]:
            print("   type gid=%04X tid=%04X inst=%d size=%X prio=%02X board=%04X ctx=%s tokens=%d sha=%s" % (t["gid"], t["tid"], t["inst"], t["size"], t["prio"], t["board"], t["ctx"], len(t["tokens"]), t["sha"]))
            if "--tokens" in sys.argv:
                for tid, val in t["tokens"]: print("      token 0x%08X = 0x%X" % (tid, val))

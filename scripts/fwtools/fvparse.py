#!/usr/bin/env python3
"""First-party minimal UEFI PI firmware-volume walker (no third-party deps).

Walks every _FVH volume in a flat SPI image, FFSv2/v3 files, sections,
GUID-defined LZMA / LZMAF86 / CRC32 encapsulations and nested FV images.
Writes leaf payloads into OUTDIR and an index.json describing them.

usage: fvparse.py IMAGE OUTDIR
"""
import hashlib, json, lzma, os, struct, sys, uuid, zlib

LZMA_GUID   = uuid.UUID("ee4e5898-3914-4259-9d6e-dc7bd79403cf")
LZMAF86     = uuid.UUID("d42ae6bd-1352-4bfb-909a-ca72a6eae889")
CRC32_GUID  = uuid.UUID("fc1bcdb0-7d31-49aa-936a-a4600d9dd083")
AMD_ZLIB    = uuid.UUID("ce3233f5-2cd6-4d87-9152-4a238bb6d1c4")  # AMD compressed PEI FV: 0x100-byte header + zlib stream
SECT = {0x01:"COMPRESSION",0x02:"GUID_DEFINED",0x03:"DISPOSABLE",0x10:"PE32",0x11:"PIC",
        0x12:"TE",0x13:"DXE_DEPEX",0x14:"VERSION",0x15:"UI",0x16:"COMPAT16",0x17:"FV_IMAGE",
        0x18:"FREEFORM_GUID",0x19:"RAW",0x1B:"PEI_DEPEX",0x1C:"MM_DEPEX"}
FTYPE = {1:"RAW",2:"FREEFORM",3:"SEC_CORE",4:"PEI_CORE",5:"DXE_CORE",6:"PEIM",7:"DRIVER",
         8:"COMBINED_PEIM_DRIVER",9:"APPLICATION",0xA:"MM",0xB:"FV_IMAGE",0xC:"COMBINED_MM_DXE",
         0xD:"MM_CORE",0xE:"MM_STANDALONE",0xF:"MM_CORE_STANDALONE",0xF0:"PAD"}

def guid(b): return str(uuid.UUID(bytes_le=bytes(b)))

def lzma_alone(data):
    d = lzma.LZMADecompressor(format=lzma.FORMAT_ALONE)
    return d.decompress(data)

def bcj_x86_decode(buf):
    # x86 BCJ decoder (public-domain algorithm from LZMA SDK Bra86.c), ip=0
    data = bytearray(buf); n = len(data); i = 0; prev_mask = 0; prev_pos = -1
    MASK_TO_ALLOWED = [1,1,1,0,1,0,0,0]; MASK_TO_BIT = [0,1,2,2,3,3,3,3]
    if n < 5: return bytes(data)
    limit = n - 4; pos = 0
    while True:
        p = pos
        while p < limit and (data[p] & 0xFE) != 0xE8: p += 1
        pos = p
        if p >= limit: break
        d = pos - prev_pos - 1 if prev_pos >= 0 else 4
        prev_pos_new = pos
        if prev_pos < 0 or d > 3: prev_mask = 0
        else:
            prev_mask = (prev_mask << (d)) & 7
            if prev_mask != 0:
                b = data[pos + 4 - MASK_TO_BIT[prev_mask]]
                if (not MASK_TO_ALLOWED[prev_mask]) or b in (0, 0xFF):
                    prev_pos = pos; prev_mask = ((prev_mask << 1) | 1) & 7; pos += 1; continue
        prev_pos = prev_pos_new
        if data[pos+4] in (0, 0xFF):
            src = struct.unpack_from("<I", data, pos+1)[0]
            while True:
                dest = (src - (pos + 5)) & 0xFFFFFFFF
                if prev_mask == 0: break
                idx = MASK_TO_BIT[prev_mask] * 8
                b = (dest >> (24 - idx)) & 0xFF
                if b not in (0, 0xFF): break
                src = dest ^ ((1 << (32 - idx)) - 1)
            dest &= 0x01FFFFFF
            if dest & 0x01000000: dest |= 0xFF000000
            struct.pack_into("<I", data, pos+1, dest & 0xFFFFFFFF)
            pos += 5
        else:
            prev_mask = ((prev_mask << 1) | 1) & 7; pos += 1
    return bytes(data)

class Walker:
    def __init__(self, out):
        self.out = out; self.index = []; self.n = 0
    def emit(self, path, kind, data, **meta):
        self.n += 1
        fn = "%05d_%s.bin" % (self.n, kind)
        with open(os.path.join(self.out, fn), "wb") as f: f.write(data)
        rec = dict(file=fn, path=path, kind=kind, size=len(data),
                   sha256=hashlib.sha256(data).hexdigest(), **meta)
        self.index.append(rec); return rec

    def sections(self, data, path, fmeta):
        off = 0; n = len(data); recs = []
        while off + 4 <= n:
            size = int.from_bytes(data[off:off+3], "little"); st = data[off+3]; hdr = 4
            if size == 0xFFFFFF:
                size = struct.unpack_from("<I", data, off+4)[0]; hdr = 8
            if size < hdr or off + size > n: break
            body = data[off+hdr:off+size]; name = SECT.get(st, "SEC%02X" % st)
            p = path + "/" + name
            if st == 0x02:
                g = uuid.UUID(bytes_le=bytes(body[:16])); doff, attr = struct.unpack_from("<HH", body, 16)
                payload = data[off+doff:off+size]
                try:
                    if g == LZMA_GUID: dec = lzma_alone(payload)
                    elif g == LZMAF86: dec = bcj_x86_decode(lzma_alone(payload))
                    elif g == CRC32_GUID: dec = payload
                    elif g == AMD_ZLIB:
                        fv = zlib.decompressobj().decompress(payload[0x100:])
                        dec = (len(fv) + 4).to_bytes(3, 'little') + b'\x17' + fv   # re-wrap as an FV_IMAGE section
                    else: dec = None
                except Exception as e:
                    dec = None; self.emit(p, "GUIDSEC_FAIL", payload, guid=str(g), err=str(e), **fmeta)
                if dec is not None: self.sections(dec, p + "{" + str(g)[:8] + "}", fmeta)
                elif g not in (LZMA_GUID, LZMAF86, AMD_ZLIB): self.emit(p, "GUIDSEC", payload, sec_guid=str(g), **fmeta)
            elif st == 0x01:
                ulen, ctype = struct.unpack_from("<IB", body, 0)
                if ctype == 0: self.sections(body[5:], p, fmeta)
                else: self.emit(p, "COMPRESSED_UNSUPPORTED", body, **fmeta)
            elif st == 0x17:
                self.volumes(body, p, nested=True)
            elif st == 0x15:
                ui = body.decode("utf-16-le", "replace").rstrip("\0"); fmeta["ui"] = ui
            elif st == 0x18:
                self.emit(p, name, body[16:], sub_guid=guid(body[:16]), **fmeta)
            else:
                recs.append((p, name, body))
            off = (off + size + 3) & ~3
        for p, name, body in recs: self.emit(p, name, body, **fmeta)

    def files(self, fv, start, path, fvmeta):
        off = start; n = len(fv)
        while off + 24 <= n:
            hdr = fv[off:off+24]
            if hdr == b"\xff" * 24: break
            name = guid(hdr[:16]); ftype = hdr[18]; attr = hdr[19]
            size = int.from_bytes(hdr[20:23], "little"); hlen = 24
            if attr & 0x01 and size == 0:
                size = struct.unpack_from("<Q", fv, off+24)[0]; hlen = 32
            if size < hlen or off + size > n: break
            body = fv[off+hlen:off+size]
            fmeta = dict(ffs_guid=name, ffs_type=FTYPE.get(ftype, hex(ftype)), ffs_off=fvmeta["base"] + off if fvmeta["base"] is not None else None, ffs_size=size, fv=fvmeta["guid"])
            p = path + "/" + name
            if ftype in (0x01,):
                self.emit(p, "RAWFILE", body, **fmeta)
            elif ftype == 0xF0: pass
            else: self.sections(body, p, fmeta)
            off = (off + size + 7) & ~7

    def volumes(self, data, path, nested=False, base=0):
        pos = 0
        while True:
            i = data.find(b"_FVH", pos)
            if i < 0: break
            s = i - 40
            if s < 0: pos = i + 4; continue
            fvlen, sig, attr, hlen, cks, ext, res, rev = struct.unpack_from("<Q4sIHHHBB", data, s + 32)
            if rev not in (1, 2) or fvlen < hlen or s + fvlen > len(data) or hlen < 0x48 or hlen > 0x1000:
                pos = i + 4; continue
            if sum(struct.unpack_from("<%dH" % (hlen // 2), data, s)) & 0xFFFF != 0:
                pos = i + 4; continue
            g = guid(data[s+16:s+32]); fv = data[s:s+fvlen]
            start = hlen
            fvname = None
            if ext:
                fvname = guid(fv[ext:ext+16]); esz = struct.unpack_from("<I", fv, ext+16)[0]
                start = (ext + esz + 7) & ~7
            meta = dict(guid=g, base=None if nested else base + s)
            self.index.append(dict(kind="FV", path=path, fv_guid=g, fv_name=fvname, offset=None if nested else base + s, size=fvlen, nested=nested, sha256=hashlib.sha256(fv).hexdigest()))
            self.files(fv, start, path + "/FV@%s" % (("%X" % (base+s)) if not nested else "n"), meta)
            pos = s + fvlen
            if nested: break

def main(img, out):
    os.makedirs(out, exist_ok=True)
    data = open(img, "rb").read()
    w = Walker(out); w.volumes(data, "")
    json.dump(w.index, open(os.path.join(out, "index.json"), "w"), indent=1)
    print(len(w.index), "records")
if __name__ == "__main__": main(sys.argv[1], sys.argv[2])

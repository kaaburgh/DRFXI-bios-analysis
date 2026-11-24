#!/usr/bin/env python3
"""Extract only the APCB regions (plus non-sensitive layout metadata) from a
full AMD SPI dump, so it can be shared for analysis without sharing the
board-specific NVRAM/serial/key contents.

Read-only. Standard library only (works with plain Python 3 on Windows/Linux).

Output (a folder and a .zip with the same content):
  * APCB entries found via the PSP/BIOS directories (types 0x60 APCB and
    0x68 APCB backup), each saved as its own .bin, only if it starts with
    the 'APCB' signature;
  * the raw directory tables ($PSP/$PL2/$BHD/$BL2 headers + entries) and the
    Embedded Firmware Structure header — pure layout, no user data;
  * manifest.json: image size and SHA-256, every directory entry (type,
    offset, size), SHA-256 of each extracted region, and SHA-256 of every
    64 KiB block of the image. Block hashes let the analyst see *which*
    blocks differ from the official image without seeing their contents.

Deliberately NOT extracted: NVRAM (UEFI variables, boot entries), APOB/
APOB_NV (training data, may include DIMM SPD serial numbers), SMBIOS/DMI,
PSP NV data, or any other region.

Usage:
    python extract_apcb_regions.py DUMP.bin OUT_DIR
"""

import hashlib
import json
import os
import struct
import sys
import zipfile

BLOCK = 0x10000
EFS_OFFSETS = (0x20000, 0x820000, 0xC20000, 0xE20000, 0xF20000, 0xFA0000)
PSP_MAGICS = (b"$PSP", b"$PL2")
BIOS_MAGICS = (b"$BHD", b"$BL2")


def sha(b):
    return hashlib.sha256(b).hexdigest()


def resolve(loc, dir_base, img_size):
    mode = (loc >> 62) & 3
    raw = loc & 0x3FFFFFFFFFFFFFFF
    if mode == 2:  # relative to directory header
        return dir_base + (raw & 0xFFFFFFFF)
    return raw & (img_size - 1) if img_size & (img_size - 1) == 0 else raw % img_size


def parse_dirs(img):
    """Scan 4 KiB / 1 KiB aligned offsets for directory headers and parse entries."""
    dirs = []
    seen = set()
    for off in range(0, len(img) - 16, 0x400):
        magic = img[off:off + 4]
        if magic not in PSP_MAGICS + BIOS_MAGICS or off in seen:
            continue
        count = struct.unpack_from("<I", img, off + 8)[0]
        if not 0 < count <= 64:
            continue
        is_bios = magic in BIOS_MAGICS
        esz = 24 if is_bios else 16
        end = off + 16 + count * esz
        if end > len(img):
            continue
        entries = []
        for i in range(count):
            e = off + 16 + i * esz
            if is_bios:
                typ, region, flags, sub = struct.unpack_from("<BBBB", img, e)
                size, src, dst = struct.unpack_from("<IQQ", img, e + 4)
                entries.append(dict(type=typ, instance=flags >> 4, subprog=sub & 7, size=size,
                                    loc=src, offset=resolve(src, off, len(img)), dest=dst))
            else:
                typ, sub, _r, size, loc = struct.unpack_from("<BBHIQ", img, e)
                entries.append(dict(type=typ, subprog=sub, size=size, loc=loc,
                                    offset=resolve(loc, off, len(img))))
        seen.add(off)
        dirs.append(dict(magic=magic.decode(), offset=off, count=count, table_len=end - off,
                         entries=entries))
    return dirs


def main():
    if len(sys.argv) != 3:
        print(__doc__)
        return 2
    src, out = sys.argv[1], sys.argv[2]
    img = open(src, "rb").read()
    os.makedirs(out, exist_ok=True)
    man = {"image_size": len(img), "image_sha256": sha(img), "block_size": BLOCK,
           "block_sha256": [sha(img[i:i + BLOCK]) for i in range(0, len(img), BLOCK)],
           "efs": [], "directories": [], "apcb_regions": []}

    for o in EFS_OFFSETS:
        if o + 0x80 <= len(img) and img[o:o + 4] == b"\xaa\x55\xaa\x55":
            open(os.path.join(out, "efs_%08x.bin" % o), "wb").write(img[o:o + 0x80])
            man["efs"].append({"offset": hex(o), "sha256": sha(img[o:o + 0x80])})

    dirs = parse_dirs(img)
    written = set()
    for d in dirs:
        table = img[d["offset"]:d["offset"] + d["table_len"]]
        name = "dir_%s_%08x.bin" % (d["magic"].strip("$"), d["offset"])
        open(os.path.join(out, name), "wb").write(table)
        man["directories"].append({
            "magic": d["magic"], "offset": hex(d["offset"]), "count": d["count"],
            "entries": [{k: (hex(v) if isinstance(v, int) and k in ("type", "loc", "offset", "dest", "size") else v)
                         for k, v in e.items()} for e in d["entries"]]})
        if d["magic"] not in ("$BHD", "$BL2"):
            continue
        for e in d["entries"]:
            if e["type"] not in (0x60, 0x68) or not e["size"]:
                continue
            o, sz = e["offset"], e["size"]
            if o + sz > len(img) or img[o:o + 4] != b"APCB" or (o, sz) in written:
                continue
            written.add((o, sz))
            blob = img[o:o + sz]
            fn = "apcb_type%02x_inst%d_%08x.bin" % (e["type"], e.get("instance", 0), o)
            open(os.path.join(out, fn), "wb").write(blob)
            man["apcb_regions"].append({"file": fn, "type": hex(e["type"]), "instance": e.get("instance", 0),
                                        "offset": hex(o), "size": hex(sz), "sha256": sha(blob)})

    with open(os.path.join(out, "manifest.json"), "w") as f:
        json.dump(man, f, indent=1)
    zpath = out.rstrip("/\\") + ".zip"
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        for fn in sorted(os.listdir(out)):
            z.write(os.path.join(out, fn), fn)

    print("image   : %s (%d bytes)" % (src, len(img)))
    print("sha256  : %s" % man["image_sha256"])
    print("dirs    : %s" % ", ".join("%s@%s" % (d["magic"], hex(d["offset"])) for d in dirs))
    for r in man["apcb_regions"]:
        print("APCB    : %s type %s inst %s at %s size %s" % (r["file"], r["type"], r["instance"], r["offset"], r["size"]))
    print("written : %s and %s" % (out, zpath))
    if not man["apcb_regions"]:
        print("WARNING: no APCB regions found - is this a full 32 MiB SPI dump?")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Static audit of the AMD DDR5 tREFI (Tref) configuration chain in a BIOS image.

Read-only.  Standard library only (lzma, zlib, struct, json).

The DRFXI 1.15/1.17 analysis (docs/findings/memory-trefi.md) established a
three-layer chain for manual DDR5 timings on DragonRangePI-FL1:

    HII/IFR question (CbsSetupDxeRPL / AodDxe)
        -> CBS/AOD code writes an APCB token (CbsSetupDxeRPL, BctBaseSmmRPL, AodSmm)
        -> ABL (PSP AGESA boot loader) reads the token in its "Override Timing" path

For tREFI the ABL consumer exists (token 0x419FF338, "Override Tref"), but no
UEFI module writes that token and no setup question exists.  This script
re-checks those facts on any AMD SPI image, so that a newer AGESA image (for
example a FireRangeFL1 laptop/mini-PC BIOS where tREFI is reported editable)
can be compared layer by layer.

What it does:
  * walks UEFI firmware volumes / FFS files / sections, recursively
    decompressing LZMA GUID-defined sections, and attributes hits to FFS UI
    names;
  * scans the whole image for PSP "$PS1" images, zlib-decompresses the
    compressed ones (ABL overlays are not encrypted on DRFXI) and searches them;
  * searches module bodies for known APCB token IDs (little-endian dwords) and
    for tREFI-related strings (ASCII and UTF-16LE);
  * reports AGESA PI version strings.

Absence of the known token ID in a newer image does NOT prove absence of a
tREFI path: AMD may use a different token.  Use the string hits (e.g. a
"Trefi" IFR prompt) as the entry point in that case.

Usage:
    python3 scripts/trefi_chain_audit.py DRFXI.BIN [--json report.json]
"""

import argparse
import hashlib
import json
import lzma
import re
import struct
import sys
import zlib

LZMA_GUID = bytes.fromhex("98584eee14395942" "9d6edc7bd79403cf")  # EE4E5898-3914-4259-9D6E-DC7BD79403CF
AMD_ZLIB_GUID = bytes.fromhex("f53332ced62c874d" "91524a238bb6d1c4")  # CE3233F5-2CD6-4D87-9152-4A238BB6D1C4
FFS2_GUID = bytes.fromhex("78e58c8c3d8a1c4f" "9935896185c32dd3")  # 8C8CE578-8A3D-4F1C-9935-896185C32DD3
FFS3_GUID = bytes.fromhex("7ac07354cb3dca4d" "bd6f1e9689e7349a")  # 5473C07A-3DCB-4DCA-BD6F-1E9689E7349A

# Token IDs observed in DRFXI ABL "Override Timing" getters (ABL 32.3/35.23/4C.11.90.20).
TOKENS = {
    "Tref (tREFI)": 0x419FF338,
    "Tcksrx": 0x4F641FDE,
    "Tcksre": 0xE9868CF1,
    "Tpd": 0x7A4972A9,
    "Tcl (positive control)": 0xFC195E5C,
    "Trfc1 (positive control)": 0xBBEED68E,
}

# "Tref Ctrl" / "AodMemTimingTref*" are the AMD Overclocking (AOD) names used by
# FireRangePI (MS-A2 F1WSA_FRG); "tref " alone is only meaningful in ABL bodies.
STRINGS = ["trefi", "refresh interval", "tref ctrl", "specify the tref", "aodmemtimingtref",
           "override tref", "tref "]


def guid_str(b):
    a, b2, c = struct.unpack_from("<IHH", b, 0)
    return "%08X-%04X-%04X-%s-%s" % (a, b2, c, b[8:10].hex().upper(), b[10:16].hex().upper())


def lzma_decompress(data):
    try:
        dec = lzma.LZMADecompressor(format=lzma.FORMAT_ALONE)
        return dec.decompress(data)
    except lzma.LZMAError:
        return None


class Walker:
    def __init__(self):
        self.modules = []  # dicts: name, guid, kind, body
        self.seen_fv = set()

    # ---- firmware volumes -------------------------------------------------
    def scan_fvs(self, buf, depth=0):
        if depth > 8:
            return
        i = buf.find(b"_FVH")
        while i >= 0:
            base = i - 0x28
            if base >= 0 and buf[base + 0x10:base + 0x20] in (FFS2_GUID, FFS3_GUID):
                fvlen = struct.unpack_from("<Q", buf, base + 0x20)[0]
                hlen = struct.unpack_from("<H", buf, base + 0x30)[0]
                if 0x48 <= hlen < 0x1000 and 0 < fvlen <= len(buf) - base:
                    key = hashlib.sha256(buf[base:base + min(fvlen, 0x400)]).digest() + struct.pack("<Q", fvlen)
                    if key not in self.seen_fv:
                        self.seen_fv.add(key)
                        self.walk_fv(buf[base:base + fvlen], hlen, depth)
                    i = buf.find(b"_FVH", base + max(fvlen, 0x48))
                    continue
            i = buf.find(b"_FVH", i + 4)

    def walk_fv(self, fv, hlen, depth):
        ext = struct.unpack_from("<H", fv, 0x34)[0]
        off = hlen
        if ext:
            ext_size = struct.unpack_from("<I", fv, ext + 0x10)[0]
            off = ext + ext_size
        off = (off + 7) & ~7
        while off + 24 <= len(fv):
            hdr = fv[off:off + 24]
            if hdr == b"\xff" * 24:
                break
            fguid = hdr[:16]
            ftype = hdr[0x12]
            attr = hdr[0x13]
            size = int.from_bytes(hdr[0x14:0x17], "little")
            hsz = 24
            if attr & 0x01 and size == 0xFFFFFF:  # FFS_ATTRIB_LARGE_FILE
                size = struct.unpack_from("<Q", fv, off + 24)[0]
                hsz = 32
            if size < hsz or off + size > len(fv):
                break
            body = fv[off + hsz:off + size]
            if ftype != 0xF0:  # skip pad files
                ctx = {"guid": guid_str(fguid), "name": None, "bodies": []}
                if ftype in (0x01,):  # raw file: may itself contain a FV
                    self.scan_fvs(body, depth + 1)
                    ctx["bodies"].append(("raw", body))
                else:
                    self.walk_sections(body, ctx, depth)
                for kind, b in ctx["bodies"]:
                    self.modules.append({"name": ctx["name"] or "", "guid": ctx["guid"], "kind": kind, "body": b})
            off = (off + size + 7) & ~7

    def walk_sections(self, buf, ctx, depth):
        off = 0
        while off + 4 <= len(buf):
            size = int.from_bytes(buf[off:off + 3], "little")
            stype = buf[off + 3]
            hsz = 4
            if size == 0xFFFFFF:
                size = struct.unpack_from("<I", buf, off + 4)[0]
                hsz = 8
            if size < hsz or off + size > len(buf):
                break
            data = buf[off + hsz:off + size]
            if stype == 0x15:  # user interface
                ctx["name"] = data.decode("utf-16le", "ignore").rstrip("\x00")
            elif stype in (0x10, 0x12, 0x19):  # PE32, TE, RAW
                ctx["bodies"].append(({0x10: "pe", 0x12: "te", 0x19: "raw"}[stype], data))
            elif stype == 0x02 and len(data) >= 20:  # GUID defined
                g = data[:16]
                doff = struct.unpack_from("<H", data, 16)[0] - hsz
                if g == LZMA_GUID and 0 <= doff < len(data):
                    out = lzma_decompress(data[doff:])
                    if out:
                        self.walk_sections(out, ctx, depth + 1)
                elif g == AMD_ZLIB_GUID and len(data) > 20 + 0x100:
                    # AMD zlib section: 0x100-byte AMD header after the GUID-defined header.
                    try:
                        out = zlib.decompress(data[20 + 0x100:])
                    except zlib.error:
                        out = None
                    if out:
                        self.walk_sections(out, ctx, depth + 1)
                elif 0 <= doff < len(data):
                    self.walk_sections(data[doff:], ctx, depth + 1)
            elif stype == 0x01:  # compression section (EFI/Tiano not handled)
                pass
            elif stype == 0x17:  # firmware volume image
                self.scan_fvs(data, depth + 1)
            off = (off + size + 3) & ~3


def scan_ps1(img):
    """Return list of (offset, version, flags, body) for every $PS1 image."""
    out = []
    i = img.find(b"$PS1")
    while i >= 0:
        o = i - 0x10
        if o >= 0 and o + 0x100 <= len(img):
            h = img[o:o + 0x100]
            size_signed, enc = struct.unpack_from("<II", h, 0x14)
            comp = struct.unpack_from("<I", h, 0x48)[0]
            usz, zsz = struct.unpack_from("<II", h, 0x50)
            ver = ".".join("%X" % x for x in h[0x60:0x64][::-1])
            body = img[o + 0x100:o + 0x100 + (zsz if comp else size_signed)]
            note = []
            if enc:
                note.append("encrypted")
                body = b""
            elif comp == 1:
                try:
                    body = zlib.decompress(body)
                    note.append("zlib")
                except zlib.error:
                    note.append("zlib-failed")
                    body = b""
            out.append((o, ver, ",".join(note), body))
        i = img.find(b"$PS1", i + 4)
    return out


def search(body):
    hits = {}
    for name, tok in TOKENS.items():
        pat = struct.pack("<I", tok)
        pos = [m.start() for m in re.finditer(re.escape(pat), body)]
        if pos:
            hits["token:" + name] = [hex(p) for p in pos[:4]]
    low = body.lower()
    for s in STRINGS:
        for enc in ("ascii", "utf-16le"):
            p = low.find(s.encode(enc))
            if p >= 0:
                hits["string:%s[%s]" % (s.strip(), enc)] = hex(p)
    return hits


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("image")
    ap.add_argument("--json", help="write machine-readable report here")
    args = ap.parse_args()

    img = open(args.image, "rb").read()
    rep = {"image": args.image, "sha256": hashlib.sha256(img).hexdigest(), "size": len(img)}

    w = Walker()
    w.scan_fvs(img)
    # Also try LZMA sections that sit outside any FV we parsed (defensive).
    rep["uefi_module_bodies"] = len(w.modules)

    agesa = set()
    uefi_hits = []
    for m in w.modules:
        for mm in re.finditer(rb"AGESA!V9\x00([ -~]{4,64})\x00", m["body"]):
            agesa.add(mm.group(1).decode())
        h = search(m["body"])
        # The string "tref " is too generic in UEFI code; keep it for ABL only.
        h = {k: v for k, v in h.items() if not k.startswith("string:tref[")}
        if h:
            uefi_hits.append({"module": m["name"], "guid": m["guid"], "kind": m["kind"], "hits": h})
    rep["agesa_versions"] = sorted(agesa)
    rep["uefi_hits"] = uefi_hits

    psp_hits = []
    seen = set()
    for off, ver, note, body in scan_ps1(img):
        if not body:
            continue
        digest = hashlib.sha256(body).hexdigest()
        h = search(body)
        if h:
            psp_hits.append({"offset": hex(off), "version": ver, "note": note,
                             "sha256": digest[:16], "duplicate": digest in seen, "hits": h})
        seen.add(digest)
    rep["psp_hits"] = psp_hits

    # Summary verdict for the known DragonRange token.
    tref = "token:Tref (tREFI)"
    rep["summary"] = {
        "abl_reads_known_tref_token": any(tref in x["hits"] for x in psp_hits),
        "uefi_modules_with_known_tref_token": sorted({x["module"] for x in uefi_hits if tref in x["hits"]}),
        "uefi_modules_with_tref_string": sorted({x["module"] for x in uefi_hits
                                                 if any(k.startswith("string:") for k in x["hits"])}),
        "uefi_modules_with_tcl_control_token": sorted({x["module"] for x in uefi_hits
                                                       if "token:Tcl (positive control)" in x["hits"]}),
    }

    if args.json:
        with open(args.json, "w") as f:
            json.dump(rep, f, indent=1)

    print("image   :", args.image)
    print("sha256  :", rep["sha256"])
    print("AGESA   :", ", ".join(rep["agesa_versions"]) or "(not found)")
    print("UEFI module bodies parsed:", rep["uefi_module_bodies"])
    print()
    print("UEFI hits:")
    for x in uefi_hits:
        print("  %-28s %-5s %s" % (x["module"], x["kind"], ", ".join(sorted(x["hits"]))))
    print()
    print("PSP $PS1 hits (unique bodies):")
    for x in psp_hits:
        if not x["duplicate"]:
            print("  %s ver %s %s: %s" % (x["offset"], x["version"], x["note"], ", ".join(sorted(x["hits"]))))
    print()
    print("Summary:")
    for k, v in rep["summary"].items():
        print("  %s: %s" % (k, v))


if __name__ == "__main__":
    sys.exit(main())

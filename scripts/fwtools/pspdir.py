#!/usr/bin/env python3
"""Address modes (bits 63:62 of location): 0/1 = flash offset (masked), 2 = relative to the directory header, 3 = other.
Walk AMD PSP ($PSP/$PL2) and BIOS ($BHD/$BL2) directories in a flat SPI image.
usage: pspdir.py IMAGE [IMAGE_B]   (with two images: also reports per-entry payload equality)"""
import struct, sys, hashlib
BHD = {0x60:"APCB",0x61:"APOB(ram)",0x62:"BIOS RTM/reset image",0x63:"APOB NV",0x64:"PMU FW code",0x65:"PMU FW data",
       0x66:"microcode",0x67:"MCE data",0x68:"APCB backup",0x69:"early VGA",0x6A:"MP2 cfg",0x6B:"shared mem",0x70:"BIOS L2 dir",
       0x71:"DMCUB/APPB",0x73:"DMCU ISR",0x76:"DMCUB",0x05:"BIOS OEM key",0x07:"BIOS RTM sig"}
PSP = {0x00:"AMD pubkey",0x01:"PSP bootloader",0x02:"PSP secure OS",0x03:"PSP recovery BL",0x04:"PSP NV data",0x08:"SMU FW",
       0x09:"SD unlock key",0x0A:"OEM pubkey",0x0B:"soft fuse",0x12:"SMU FW2",0x13:"early SD unlock",0x20:"IP discovery",0x21:"wrapped iKEK",
       0x22:"token unlock",0x24:"sec policy",0x25:"MP2 FW",0x28:"sys drv",0x30:"ABL0",0x31:"ABL1",0x32:"ABL2",0x33:"ABL3",0x34:"ABL4",
       0x35:"ABL5",0x36:"ABL6",0x37:"ABL7",0x40:"PSP L2 dir",0x48:"PSP L2 dir B",0x49:"BIOS L2 dir (from PSP)",0x54:"PSP NVRAM (RPMC)",0x5A:"MSMU",0x5C:"SPIROM cfg"}
def walk(d, base_mask=0x1FFFFFF):
    out = []; seen = set()
    def phys(a): return a & base_mask
    def rd(off, lvl):
        if off in seen or off + 16 > len(d): return
        seen.add(off); magic = d[off:off+4]
        if magic in (b"$PSP", b"$PL2"):
            cnt = struct.unpack_from("<I", d, off+8)[0]
            for i in range(cnt):
                t, sub, rsv, size, loc = struct.unpack_from("<BBHIQ", d, off+16+16*i)
                mode = loc >> 62; a = loc & 0x3FFFFFFFFFFFFFFF
                addr = phys(a) if mode in (0, 1) else (off + a if mode == 2 else a)
                out.append((magic.decode(), off, t, sub, 0, size, addr, PSP.get(t, "?")))
                if t in (0x40, 0x48, 0x49, 0x70) and size != 0xFFFFFFFF: rd(addr, lvl+1)
        elif magic in (b"$BHD", b"$BL2"):
            cnt = struct.unpack_from("<I", d, off+8)[0]
            for i in range(cnt):
                t, region, flags, sub, size, loc, dest = struct.unpack_from("<BBBBIQQ", d, off+16+24*i)
                mode = loc >> 62; a = loc & 0x3FFFFFFFFFFFFFFF
                addr = phys(a) if mode in (0, 1) else (off + a if mode == 2 else a)
                out.append((magic.decode(), off, t, flags >> 4 if False else sub, flags, size, addr, BHD.get(t, "?")))
                if t == 0x70: rd(addr, lvl+1)
        elif magic == b"2PSP" or magic == b"2BHD":
            pass
    # embedded firmware structure
    for efs in (0x20000, 0x820000, 0xFA0000, 0xF20000, 0xE20000, 0xC20000):
        if d[efs:efs+4] == bytes.fromhex("aa55aa55"):
            w = struct.unpack_from("<16I", d, efs)
            out.append(("EFS", efs, 0, 0, 0, 0, 0, " ".join("%08X" % x for x in w)))
            for x in w[1:12]:
                p = phys(x)
                if x not in (0, 0xFFFFFFFF) and p + 4 <= len(d):
                    m = d[p:p+4]
                    if m in (b"$PSP", b"$BHD", b"$PL2", b"$BL2"): rd(p, 0)
                    elif m in (b"2PSP", b"2BHD"):
                        for q in struct.unpack_from("<4I", d, p+16): 
                            if q not in (0, 0xFFFFFFFF): rd(phys(q), 0)
    # brute force any directory cookies not reached
    for m in (b"$PSP", b"$BHD", b"$PL2", b"$BL2"):
        i = 0
        while True:
            i = d.find(m, i)
            if i < 0: break
            if i % 0x1000 == 0: rd(i, 0)
            i += 4
    return out
if __name__ == "__main__":
    A = open(sys.argv[1], "rb").read(); B = open(sys.argv[2], "rb").read() if len(sys.argv) > 2 else None
    for r in walk(A):
        if r[0] == "EFS": print("EFS @%X: %s" % (r[1], r[7])); continue
        size = r[5]; addr = r[6]; eq = ""
        if B is not None and size not in (0, 0xFFFFFFFF) and addr + size <= len(A):
            eq = "SAME" if A[addr:addr+size] == B[addr:addr+size] else "DIFF(%d bytes)" % sum(x != y for x, y in zip(A[addr:addr+size], B[addr:addr+size]))
            blank = A[addr:addr+size].count(0xFF) == size
            if blank: eq += " BLANK(FF)"
        print("%s@%07X type=%02X sub/inst=%02X flags=%02X size=%08X addr=%07X %-22s %s" % (r[0], r[1], r[2], r[3], r[4], size, addr, r[7], eq))

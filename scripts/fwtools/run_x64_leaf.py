#!/usr/bin/env python3
"""Execute a self-contained Microsoft-x64 leaf function (no calls, no RIP-relative refs) extracted from a PE,
natively on x86-64 Linux, with RCX = pointer to a caller-supplied buffer. Used to evaluate the CBS
settings fingerprint (CbsSetupDxeRPL 1.17 @0x5134) over AmdSetupRPL default bytes.
usage: run_x64_leaf.py PE START_HEX END_HEX(exclusive) BUFFER_FILE [PATCH_OFF=VAL ...]"""
import ctypes, mmap, struct, sys
def run(pe, start, end, buf):
    code = open(pe, "rb").read()[start:end]           # PE file offset == RVA for these images (checked by caller)
    # SysV trampoline: mov rcx, rdi ; sub rsp,0x28 ; call rel32 ; add rsp,0x28 ; ret
    tramp = b"\x48\x89\xf9" + b"\x48\x83\xec\x28" + b"\xe8" + struct.pack("<i", 4 + 1) + b"\x48\x83\xc4\x28" + b"\xc3"
    blob = tramp + code
    mem = mmap.mmap(-1, len(blob) + 4096, prot=mmap.PROT_READ | mmap.PROT_WRITE | mmap.PROT_EXEC)
    mem.write(blob)
    addr = ctypes.addressof(ctypes.c_char.from_buffer(mem))
    f = ctypes.CFUNCTYPE(ctypes.c_uint32, ctypes.c_void_p)(addr)
    b = (ctypes.c_ubyte * len(buf)).from_buffer_copy(buf)
    return f(ctypes.addressof(b))
if __name__ == "__main__":
    pe, s, e, bf = sys.argv[1], int(sys.argv[2], 16), int(sys.argv[3], 16), sys.argv[4]
    buf = bytearray(open(bf, "rb").read())
    for p in sys.argv[5:]:
        o, v = p.split("="); buf[int(o, 16)] = int(v, 16)
    print("0x%08X" % run(pe, s, e, bytes(buf)))

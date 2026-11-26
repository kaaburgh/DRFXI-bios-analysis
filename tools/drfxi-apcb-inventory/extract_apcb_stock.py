#!/usr/bin/env python3
"""Extract verified DRFXI 1.15 test inputs. No device access or firmware writes."""
import argparse
import hashlib
import lzma
import struct
import uuid
from pathlib import Path

ROM_SHA = '3afaba6d916b3897d1d98bd5913008b38e89b6c51b2c6963c7109793541d8d88'
MODULES = {
    'AmdApcbDxeV3.pe': ('4D3708A0-6D9B-47D3-AD87-E80C781BC0A7', 0x07, 56576, '7d42c7eefdb02ce232e686fa0f692200e8192b36ab98b0d2ac58b5e3db651515'),
    'AmdApcbSmmV3.pe': ('B1BAC051-D5C2-4AC1-AC7D-9D2F518A1E7B', 0x0A, 55296, '9dd2f6fc7be93f9f976c7210af6c0f7beef4b5a4bf95a511783fe6d75ced8126'),
}

def require(condition, message):
    if not condition:
        raise ValueError(message)

def sha(data):
    return hashlib.sha256(data).hexdigest()

def u24(b, off):
    return int.from_bytes(b[off:off+3], 'little')

def ffs(b, guid, typ):
    marker = uuid.UUID(guid).bytes_le
    pos = 0
    hits = []
    while (off := b.find(marker, pos)) >= 0:
        pos = off + 1
        if off + 24 <= len(b) and b[off+18] == typ and b[off+23] == 0xF8:
            n = u24(b, off+20)
            if 24 <= n <= len(b)-off:
                hits.append((off, n))
    require(len(hits) == 1, f'Expected unique FFS {guid}, got {hits}')
    return hits[0]

def pe_body(outer, guid, typ):
    p, n = ffs(outer, guid, typ)
    end = p+n
    p += 24
    found = []
    while p+4 <= end:
        n = u24(outer, p)
        require(4 <= n <= end-p, 'Invalid section size')
        if outer[p+3] == 0x10:
            found.append(outer[p+4:p+n])
        p = (p+n+3)&~3
    require(len(found) == 1, f'Expected unique PE body {guid}')
    return found[0]

def extract(rom):
    require(len(rom) == 33554432 and sha(rom) == ROM_SHA, 'Not exact stock DRFXI 1.15')
    p, n = ffs(rom, '9E21FD93-9C72-4C15-8C4B-E77F1DB2D792', 0x0B)
    sec = p+24
    size = u24(rom, sec)
    offset = struct.unpack_from('<H', rom, sec+20)[0]
    require(rom[sec+3] == 2 and 24 <= offset <= size <= n-24, 'Invalid LZMA section')
    outer = lzma.decompress(rom[sec+offset:sec+size], format=lzma.FORMAT_ALONE)
    require(len(outer) == 11927568, 'Unexpected expanded volume')
    out = {}
    for name, (guid, typ, size, digest) in MODULES.items():
        pe = pe_body(outer, guid, typ)
        require(len(pe) == size and sha(pe) == digest, f'Module hash mismatch {name}')
        out[name] = pe
    for base in (0x51D000, 0x8E5000):
        require(rom[base:base+4] == b'$BL2' and struct.unpack_from('<I',rom,base+8)[0] == 18, 'Invalid stock directory')
        entries = [struct.unpack_from('<IIQQ', rom, base+16+24*i) for i in range(18)]
        for typeword, relative, capacity in ((0x68, 0x400, 0x4000), (0x20000060, 0x5000, 0x3000), (0x00800068, 0x8000, 0x3000)):
            require(sum(t == typeword and sz == capacity and a == (1<<63)|relative for t,sz,a,d in entries) == 1, 'Unexpected APCB directory entry')
            start = base+relative
            require(rom[start:start+4] == b'APCB', 'Invalid APCB signature')
            size = struct.unpack_from('<I',rom,start+8)[0]
            require(128 <= size <= capacity, 'Invalid APCB size')
            out[f'block-{relative:x}-{base:x}.bin'] = rom[start:start+size]
    return out

def main():
    p = argparse.ArgumentParser()
    p.add_argument('stock_rom', type=Path)
    p.add_argument('new_output_directory', type=Path)
    args = p.parse_args()
    out = extract(args.stock_rom.read_bytes())
    args.new_output_directory.mkdir(exist_ok=False)
    for name, data in out.items():
        with (args.new_output_directory/name).open('xb') as f:
            f.write(data)
        print(sha(data), name)

if __name__ == '__main__':
    main()

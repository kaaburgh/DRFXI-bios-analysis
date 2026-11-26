#!/usr/bin/env python3
"""Requires locally extracted stock CbsSetupDxeRPL PE32, not a private dump."""
import hashlib, struct, subprocess, sys, tempfile, uuid, zlib
from pathlib import Path
exe, path = sys.argv[1:]
pe=Path(path).read_bytes()
assert hashlib.sha256(pe).hexdigest()=='0aafafee9e5f51d72b978a8268499c6aacbc9e3a612d22e3b4943c0021212084'
package=pe[0x8760:0x8760+0x21789]
assert hashlib.sha256(package).hexdigest()=='58d1d2dfaf5920edcf0e77225b62307b80edc28c739a77a398cda6300489f92a'
forms=package[20:20+0x75c1]
assert zlib.crc32(forms)==0x7897c39a
guid=uuid.UUID('38a0ff25-ef7b-47e7-ab63-e56d9a67361b').bytes_le
def wrap(p):return guid+struct.pack('<I',24+len(p))+p+b'\x04\x00\x00\xdf'
with tempfile.TemporaryDirectory() as t:
    f=Path(t)/'list.bin'
    def run(name,b,code,*wanted):
        f.write_bytes(b)
        p=subprocess.run([exe,str(f)],capture_output=True,text=True)
        print(name,p.returncode,p.stdout.strip())
        assert p.returncode==code and all(x in p.stdout for x in wanted)
    run('stock full list',package,0,'sets=1','forms=F','refs=7','mcr=1','stock=1')
    run('stock forms only',wrap(forms),0,'sets=1','stock=1')
    changed=bytearray(forms);changed[0xdc]^=1
    run('different valid IFR',wrap(changed),0,'sets=1','stock=0')
    malformed=bytearray(forms);malformed[0x2071]=0
    run('malformed opcode',wrap(malformed),1,'ok=0','stock=0')
    run('duplicate formset',wrap(forms+forms),0,'sets=2','stock=2')
    run('truncation',package[:-1],1,'ok=0')
    run('foreign GUID',bytes(16)+package[16:],1,'sets=0')
    run('no forms',wrap(b''),0,'sets=0','stock=0')

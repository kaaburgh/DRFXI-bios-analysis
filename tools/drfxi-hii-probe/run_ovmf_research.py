#!/usr/bin/env python3
"""VM-only reproducibility runner. Never boot the generated EFIs on real hardware."""
import argparse, hashlib, json, pathlib, re, shutil, socket, subprocess, tempfile, time
from pathlib import Path

PE_SHA = '0aafafee9e5f51d72b978a8268499c6aacbc9e3a612d22e3b4943c0021212084'
LIST_SHA = '58d1d2dfaf5920edcf0e77225b62307b80edc28c739a77a398cda6300489f92a'
ANSI = re.compile(r'\x1b\[[0-?]*[ -/]*[@-~]')
SOURCE = ('hii_probe.c', 'sendform_fixture.c', 'sync_fixture.c', 'sync_code.S', 'route_fixture.c', 'route_code.S', 'integrated_fixture.c')
SLICES = {
    'defaults.bin': (0x3e58, 0x45c3, '94553d7761d003d8ce34891656b8dd70b1e15c870b626e98fe3eb7fdf6786147'),
    'sync.bin': (0x45c4, 0x5131, '12181b63b220acde636295e511c83f3a632fde17722db54e346c7f12b7b414e5'),
    'hash.bin': (0x5134, 0x5edf, '71c6b2564a5d111852ba9b05e31763c3d1d70cba3ddc693972c27d2fc0418d1f'),
}

def check_hash(b, expected, label):
    actual = hashlib.sha256(b).hexdigest()
    if actual != expected:
        raise ValueError(f'{label}: SHA256 mismatch: {actual}')

def compile_all(src, pe):
    data = pe.read_bytes(); check_hash(data, PE_SHA, 'CBS PE')
    pack = data[0x8760:0x8760+0x21789]; check_hash(pack, LIST_SHA, 'HII list')
    (src/'stock.inc').write_text(',\n'.join(','.join(str(x) for x in pack[i:i+32]) for i in range(0,len(pack),32)))
    (src/'CbsSetupDxeRPL.pe').write_bytes(data)
    for name,(a,b,sha) in SLICES.items():
        blob = data[a:b]; check_hash(blob,sha,name); (src/name).write_bytes(blob)
    common = ['clang','-target','x86_64-pc-windows-msvc','-ffreestanding','-fno-builtin','-fno-stack-protector','-fshort-wchar','-mno-red-zone','-Oz','-Wall','-Wextra','-Werror']
    for code in ('sync_code','route_code'):
        subprocess.run(['clang','-target','x86_64-pc-windows-msvc','-c',code+'.S','-o',code+'.obj'],cwd=src,check=True)
    def build(name, source, defines=(), extra=(), more=()):
        subprocess.run(common+list(extra)+list(defines)+['-c',source,'-o',name+'.obj'],cwd=src,check=True)
        subprocess.run(['lld-link','/subsystem:efi_application','/entry:efi_main','/nodefaultlib','/machine:x64','/dynamicbase','/timestamp:0','/out:'+name+'.efi',name+'.obj']+list(more),cwd=src,check=True)
    build('root43','sendform_fixture.c',['-DSELECTOR=0x43','-DFORM_ID=0x7000'])
    build('rootff','sendform_fixture.c',['-DSELECTOR=0xff','-DFORM_ID=0x7000'])
    build('direct','sendform_fixture.c')
    build('save','sendform_fixture.c',['-DACCEPT_ROUTE'])
    build('sync','sync_fixture.c',more=['sync_code.obj'])
    build('route','route_fixture.c',more=['route_code.obj'])
    for fault in (0,4):
        build(f'integrated{fault}','integrated_fixture.c',[f'-DFAULT={fault}'],['-Wno-unused-function'],['route_code.obj'])

def plain(path):
    return ANSI.sub('',path.read_text(errors='replace')) if path.exists() else ''

def wait_text(path, needle, process, timeout=20):
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        if needle in plain(path): return
        if process.poll() is not None: raise RuntimeError(f'QEMU exited before {needle!r}')
        time.sleep(.1)
    raise TimeoutError(f'No serial marker {needle!r}')

class QMP:
    def __init__(self,path):
        self.sock=socket.socket(socket.AF_UNIX);self.sock.settimeout(5);self.sock.connect(str(path));self.f=self.sock.makefile('rwb')
        self.read();self.call('qmp_capabilities')
    def read(self):
        line=self.f.readline()
        if not line: raise RuntimeError('QMP EOF')
        return json.loads(line)
    def call(self,cmd,arguments=None):
        req={'execute':cmd}
        if arguments is not None:req['arguments']=arguments
        self.f.write((json.dumps(req)+'\n').encode());self.f.flush()
        while True:
            r=self.read()
            if 'error' in r: raise RuntimeError(str(r['error']))
            if 'return' in r:return r['return']
    def close(self):
        self.f.close();self.sock.close()

def run_case(qemu, src, out, name, binary, marker, keys=(), menu=None):
    with tempfile.TemporaryDirectory(prefix='drfxi-vm-') as d:
        w=Path(d); (w/'esp/EFI/BOOT').mkdir(parents=True);shutil.copyfile(src/(binary+'.efi'),w/'esp/EFI/BOOT/BOOTX64.EFI');shutil.copyfile(qemu/'share/OVMF/OVMF_VARS_4M.fd',w/'vars.fd')
        serial=w/'serial.log';qmp=w/'qmp';p=None;mon=None
        try:
            with (w/'stderr.log').open('wb') as err:
                p=subprocess.Popen([str(qemu/'bin/qemu-system-x86_64'),'-machine','q35,accel=tcg','-m','256','-smp','1','-display','none','-serial',f'file:{serial}','-monitor','none','-qmp',f'unix:{qmp},server=on,wait=off','-nic','none','-drive',f'if=pflash,format=raw,readonly=on,file={qemu}/share/OVMF/OVMF_CODE_4M.fd','-drive',f'if=pflash,format=raw,file={w}/vars.fd','-drive',f'format=raw,file=fat:rw:{w}/esp','-no-reboot'],stdout=subprocess.DEVNULL,stderr=err)
                if menu:
                    wait_text(serial,'Entering SendForm',p);wait_text(serial,menu,p);time.sleep(1)
                    mon=QMP(qmp);mon.call('screendump',{'filename':str(w/'screen.ppm')})
                    for key in keys:
                        mon.call('human-monitor-command',{'command-line':'sendkey '+key});time.sleep(.75)
                wait_text(serial,marker,p)
        finally:
            if mon:
                try:mon.close()
                except OSError:pass
            if p and p.poll() is None:
                p.terminate()
                try:p.wait(timeout=3)
                except subprocess.TimeoutExpired:p.kill();p.wait()
            dest=out/name;dest.mkdir();
            for f in ('serial.log','stderr.log','screen.ppm'):
                if (w/f).exists():shutil.copyfile(w/f,dest/f)
    print(f'{name}: guest marker {marker}',flush=True)
    return plain(out/name/'serial.log')

def require(s,*patterns):
    for pat in patterns:
        if pat not in s:raise AssertionError(f'missing {pat!r}')

def value(s,label,x):require(s,f'{label}: 0x{x:016X}')

def main():
    a=argparse.ArgumentParser(description=__doc__);a.add_argument('--pe',type=Path,required=True);a.add_argument('--qemu',type=Path,required=True);a.add_argument('--out',type=Path,required=True);a.add_argument('--group',choices=['all','browse','code','integrated'],default='all');args=a.parse_args()
    qemu=args.qemu.resolve();out=args.out.resolve();out.mkdir(parents=True,exist_ok=False)
    results={}
    with tempfile.TemporaryDirectory(prefix='drfxi-build-') as d:
        src=Path(d)
        for name in SOURCE:shutil.copyfile(Path(__file__).resolve().parent/name,src/name)
        compile_all(src,args.pe.resolve())
        if args.group in ('all','browse'):
            for name,selector in [('root43',0x43),('rootff',0xff)]:
                s=run_case(qemu,src,out,name,name,'FIXTURE END',['esc'],'CPU Common Options');visible=s.split('Entering SendForm',1)[1].split('SendForm status:',1)[0]
                assert ('UMC Common Options' in visible)==(selector==255);require(visible,'CPU Common Options','NBIO Common Options','FCH Common Options','SMU Common Options');value(s,'Route calls',0);results[name]='PASS'
            s=run_case(qemu,src,out,'direct','direct','FIXTURE END',['esc'],'Memory Context Restore');require(s,'DDR Memory Features','<Auto>');value(s,'SendForm status',0);value(s,'Extract calls',1);value(s,'Route calls',0);value(s,'CBS MCR still',255);results['direct']='PASS'
            s=run_case(qemu,src,out,'save','save','FIXTURE END',['ret','down','ret','f10','y','esc'],'Memory Context Restore');value(s,'Route calls',1);value(s,'changed bytes',1);value(s,'changed offset',0x263);value(s,'CBS MCR still',1);results['save']='PASS'
            s=run_case(qemu,src,out,'discard','save','FIXTURE END',['ret','down','ret','esc','n'],'Memory Context Restore');value(s,'Route calls',0);value(s,'CBS MCR still',255);results['discard']='PASS'
        if args.group in ('all','code'):
            for name,mark in [('sync','STOCK CBS SYNC FIXTURE PASS'),('route','ORIGINAL ROUTE AND STARTUP FIXTURE PASS')]:
                run_case(qemu,src,out,name,name,mark);results[name]='PASS'
        if args.group in ('all','integrated'):
            for fault in (0,4):
                name=f'integrated{fault}';run_case(qemu,src,out,name,name,'INTEGRATED FIXTURE PASS',['ret','down','down','ret','f10','y','esc'],'Memory Context Restore');results[name]='PASS'
    (out/'results.json').write_text(json.dumps(results,indent=2)+'\n');print(json.dumps(results,indent=2))

if __name__=='__main__':main()

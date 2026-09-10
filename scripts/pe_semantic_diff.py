#!/usr/bin/env python3
import struct, hashlib, json, pathlib, sys

def sha(b): return hashlib.sha256(b).hexdigest()

def parse_pe(path):
    b=bytearray(pathlib.Path(path).read_bytes())
    if b[:2] != b'MZ': raise ValueError('not MZ')
    peoff=struct.unpack_from('<I',b,0x3c)[0]
    if b[peoff:peoff+4] != b'PE\0\0': raise ValueError('not PE')
    coff=peoff+4
    machine,nsec,tstamp,ptrsym,nsym,optsz,chars=struct.unpack_from('<HHIIIHH',b,coff)
    opt=coff+20
    magic=struct.unpack_from('<H',b,opt)[0]
    if magic==0x20b:
        dd_off=opt+112
        checksum_off=opt+64
    elif magic==0x10b:
        dd_off=opt+96
        checksum_off=opt+64
    else: raise ValueError(f'opt magic {magic:x}')
    nb=bytearray(b)
    nb[coff+4:coff+8]=b'\0'*4
    nb[checksum_off:checksum_off+4]=b'\0'*4
    sec_off=opt+optsz
    secs=[]
    for i in range(nsec):
        o=sec_off+i*40
        name=bytes(b[o:o+8]).split(b'\0')[0].decode('ascii','replace')
        vsz,va,rsz,rptr=struct.unpack_from('<IIII',b,o+8)
        secs.append(dict(name=name,va=va,vsz=vsz,rsz=rsz,rptr=rptr,header=o))
    def rva_to_off(rva):
        for s in secs:
            span=max(s['vsz'],s['rsz'])
            if s['va'] <= rva < s['va']+span:
                d=rva-s['va']
                if d < s['rsz']:
                    return s['rptr']+d
        return None
    dirs=[]
    for i in range(16):
        if dd_off+i*8+8 <= len(b):
            dirs.append(struct.unpack_from('<II',b,dd_off+i*8))
        else: dirs.append((0,0))
    reloc_rva,reloc_sz=dirs[5]
    roff=rva_to_off(reloc_rva) if reloc_rva else None
    if roff is not None:
        end=min(len(b),roff+reloc_sz); p=roff
        while p+8<=end:
            page,bsz=struct.unpack_from('<II',b,p)
            if bsz<8 or p+bsz>end: break
            q=p+8
            while q+2<=p+bsz:
                e=struct.unpack_from('<H',b,q)[0]; q+=2
                typ=e>>12; ofs=e&0xfff
                rva=page+ofs; fo=rva_to_off(rva)
                if fo is not None:
                    if typ==10 and fo+8<=len(nb): nb[fo:fo+8]=b'\0'*8
                    elif typ==3 and fo+4<=len(nb): nb[fo:fo+4]=b'\0'*4
            p+=bsz
    dbg_rva,dbg_sz=dirs[6]
    doff=rva_to_off(dbg_rva) if dbg_rva else None
    if doff is not None and dbg_sz:
        for p in range(doff, min(doff+dbg_sz,len(b))-27, 28):
            _,ts,maj,minr,typ,sz,addr,ptr=struct.unpack_from('<IIHHIIII',b,p)
            if ptr and sz and ptr+sz<=len(nb): nb[ptr:ptr+sz]=b'\0'*sz
        nb[doff:min(doff+dbg_sz,len(nb))]=b'\0'*min(dbg_sz,len(nb)-doff)
    section=[]
    for s in secs:
        raw=bytes(nb[s['rptr']:s['rptr']+s['rsz']]) if s['rptr'] and s['rsz'] else b''
        section.append({**s,'sha256_norm':sha(raw),'raw_size':len(raw)})
    return {'path':str(path),'size':len(b),'sha256':sha(bytes(b)),'sha256_norm':sha(bytes(nb)),'sections':section,'norm_bytes':bytes(nb)}

def compare(a,b):
    pa,pb=parse_pe(a),parse_pe(b)
    ma={s['name']:s for s in pa['sections']}; mb={s['name']:s for s in pb['sections']}
    names=sorted(set(ma)|set(mb))
    sections=[]
    for n in names:
        x,y=ma.get(n),mb.get(n)
        sections.append({'name':n,'a_size':x['raw_size'] if x else None,'b_size':y['raw_size'] if y else None,'same_norm': bool(x and y and x['sha256_norm']==y['sha256_norm']), 'a_hash':x['sha256_norm'] if x else None,'b_hash':y['sha256_norm'] if y else None})
    return {'a':pa['sha256'],'b':pb['sha256'],'whole_same_norm':pa['sha256_norm']==pb['sha256_norm'],'sections':sections}

if __name__=='__main__':
    print(json.dumps(compare(sys.argv[1],sys.argv[2]),indent=2))

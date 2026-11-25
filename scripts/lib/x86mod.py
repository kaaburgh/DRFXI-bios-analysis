import bisect,pefile,capstone,re,sys,pickle,struct
class Mod:
    def __init__(s,p):
        s.pe=pefile.PE(p); s.img=s.pe.get_memory_mapped_image(); s.base=s.pe.OPTIONAL_HEADER.ImageBase
        t=[x for x in s.pe.sections if x.Name.startswith(b'.text')][0]
        md=capstone.Cs(capstone.CS_ARCH_X86,capstone.CS_MODE_64); md.skipdata=True
        s.ins=[(i.address,i.size,i.mnemonic,i.op_str) for i in md.disasm(s.img[t.VirtualAddress:t.VirtualAddress+t.Misc_VirtualSize],t.VirtualAddress)]
        s.idx={a:k for k,(a,_,_,_) in enumerate(s.ins)}
        s.addrs=[a for a,_,_,_ in s.ins]
    def rip(s,a,sz,o):
        m=re.search(r'\[rip ([+-]) (0x[0-9a-f]+)\]',o)
        return a+sz+int(m.group(2),16)*(1 if m.group(1)=='+' else -1) if m else None
    def cstr(s,o):
        e=s.img.find(b'\0',o); return s.img[o:e].decode('latin1')
    def strrefs(s,needle):
        out=[]
        for a,sz,m,o in s.ins:
            t=s.rip(a,sz,o)
            if t and 0<=t<len(s.img) and needle in s.cstr(t)[:200]: out.append((a,s.cstr(t)))
        return out
    def func_start(s,a):
        k=s.idx[a]
        while k>0 and s.ins[k-1][2]!='int3': k-=1
        return s.ins[k][0]
    def dump(s,lo,hi=None,n=400,annot=True):
        k=s.idx.get(lo, bisect.bisect_left(s.addrs, lo)); c=0  # snap to next instruction
        while k<len(s.ins) and c<n:
            a,sz,m,o=s.ins[k]
            if hi is not None and a>=hi: break
            if hi is None and m=='int3': break
            note=''
            t=s.rip(a,sz,o)
            if annot and t is not None and 0<=t<len(s.img):
                st=s.cstr(t)
                if len(st)>=4 and all(32<=ord(c)<127 or c in '\r\n\t' for c in st[:40]): note='  ; "%s"'%st[:60].replace('\n','\\n')
                else: note='  ; ->%#x'%t
            print('%06x %-7s %s%s'%(a,m,o,note)); k+=1; c+=1

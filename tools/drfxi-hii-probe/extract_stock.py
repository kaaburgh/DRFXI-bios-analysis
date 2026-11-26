import argparse, zipfile, ctypes as C, ctypes.util, hashlib, lzma, uuid
from pathlib import Path
parser=argparse.ArgumentParser();parser.add_argument('acquisition_zip',type=Path);parser.add_argument('output_pe',type=Path);args=parser.parse_args()
z=zipfile.ZipFile(args.acquisition_zip);data=z.read(next(n for n in z.namelist() if 'raw/official-1.15-aliyun__' in n));a=C.CDLL(ctypes.util.find_library('archive'))
for n,argtypes,rest in [('archive_read_new',[],C.c_void_p),('archive_read_support_filter_all',[C.c_void_p],C.c_int),('archive_read_support_format_all',[C.c_void_p],C.c_int),('archive_read_open_memory',[C.c_void_p,C.c_void_p,C.c_size_t],C.c_int),('archive_read_next_header',[C.c_void_p,C.POINTER(C.c_void_p)],C.c_int),('archive_entry_pathname',[C.c_void_p],C.c_char_p),('archive_entry_size',[C.c_void_p],C.c_int64),('archive_read_data',[C.c_void_p,C.c_void_p,C.c_size_t],C.c_ssize_t),('archive_read_free',[C.c_void_p],C.c_int)]:f=getattr(a,n);f.argtypes=argtypes;f.restype=rest
p=a.archive_read_new();a.archive_read_support_filter_all(p);a.archive_read_support_format_all(p);b=C.create_string_buffer(data);assert a.archive_read_open_memory(p,b,len(data))==0;ent=C.c_void_p();rom=None
while a.archive_read_next_header(p,C.byref(ent))==0:
 name=a.archive_entry_pathname(ent);n=a.archive_entry_size(ent)
 if name.lower().endswith(b'drfxi.bin') and n==33554432:
  out=C.create_string_buffer(n);pos=0
  while pos<n:
   k=a.archive_read_data(p,C.byref(out,pos),n-pos);assert k>0;pos+=k
  rom=out.raw;break
a.archive_read_free(p);assert hashlib.sha256(rom).hexdigest()=='3afaba6d916b3897d1d98bd5913008b38e89b6c51b2c6963c7109793541d8d88'
def ffs(b,g,t):
 g=uuid.UUID(g).bytes_le;hits=[];p=0
 while (i:=b.find(g,p))>=0:
  if b[i+18]==t and b[i+23]==0xf8:hits.append(i)
  p=i+1
 assert len(hits)==1,hits;return hits[0]
p=ffs(rom,'9E21FD93-9C72-4C15-8C4B-E77F1DB2D792',0x0b)+24;n=int.from_bytes(rom[p:p+3],'little');o=int.from_bytes(rom[p+20:p+22],'little');outer=lzma.decompress(rom[p+o:p+n],format=lzma.FORMAT_ALONE)
p=ffs(outer,'2848A12F-3F86-47C7-81D8-D3FD47B205B2',7);end=p+int.from_bytes(outer[p+20:p+23],'little');i=p+24
while i<end:
 n=int.from_bytes(outer[i:i+3],'little');assert n>=4
 if outer[i+3]==0x10:
  pe=outer[i+4:i+n];assert hashlib.sha256(pe).hexdigest()=='0aafafee9e5f51d72b978a8268499c6aacbc9e3a612d22e3b4943c0021212084';args.output_pe.write_bytes(pe);print(f'Wrote {args.output_pe} ({len(pe)} bytes)');break
 i=(i+n+3)&~3

else: raise ValueError("CBS PE32 section not found")

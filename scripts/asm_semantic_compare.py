#!/usr/bin/env python3
import subprocess,re,sys,pathlib,hashlib,json
ADDR_LINE=re.compile(r'^\s*[0-9a-fA-F]+:\s+(.*)$')
BYTES_PREFIX=re.compile(r'^(?:[0-9a-fA-F]{2}\s+)+')
RIP=re.compile(r'\[rip(?:[+-]0x[0-9a-fA-F]+)?\]')
COMMENT=re.compile(r'\s+#\s+0x[0-9a-fA-F]+.*$')
BRANCH=re.compile(r'^(?P<m>(?:call|jmp|j[a-z]+|loop[a-z]*))\s+0x[0-9a-fA-F]+(?:\s.*)?$',re.I)

def disasm(path):
 cp=subprocess.run(['objdump','-d','--no-show-raw-insn','-Mintel',str(path)],stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True,check=True)
 out=[]
 for line in cp.stdout.splitlines():
  m=ADDR_LINE.match(line)
  if not m: continue
  ins=m.group(1).strip()
  ins=COMMENT.sub('',ins).strip()
  ins=RIP.sub('[rip+<DISP>]',ins)
  bm=BRANCH.match(ins)
  if bm: ins=bm.group('m').lower()+' <TARGET>'
  out.append(ins)
 return out

def stats(a,b):
 import difflib
 A=disasm(a); B=disasm(b)
 ratio=difflib.SequenceMatcher(None,A,B,autojunk=False).ratio()
 return {'a_insn':len(A),'b_insn':len(B),'same_sequence':A==B,'ratio':ratio,'a_hash':hashlib.sha256('\n'.join(A).encode()).hexdigest(),'b_hash':hashlib.sha256('\n'.join(B).encode()).hexdigest()}
if __name__=='__main__': print(json.dumps(stats(sys.argv[1],sys.argv[2]),indent=2))

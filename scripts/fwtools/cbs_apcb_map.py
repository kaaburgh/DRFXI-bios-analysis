#!/usr/bin/env python3
"""Recover the CBS setup -> APCB token push table from CbsSetupDxeRPL disassembly.
For every `mov r8d,<token>` inside [start,end) it records: setup offset loaded into r9 (from [rbx+off]),
the 'skip' sentinel compared against, the nearest enclosing guard `cmp BYTE PTR [rbx+X],imm`,
and the setter register (mapped to width via the prologue loads).
usage: cbs_apcb_map.py CbsSetupDxeRPL.efi START END IFR_JSON"""
import re, subprocess, sys, json
def main(pe, start, end, ifrj):
    start = int(start, 16); end = int(end, 16)
    asm = subprocess.run(["objdump", "-d", "-M", "intel", pe], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True).stdout
    ins = []
    for l in asm.splitlines():
        m = re.match(r"\s*([0-9a-f]+):\t[0-9a-f ]+\t(.*)", l)
        if m:
            a = int(m.group(1), 16)
            if start <= a < end: ins.append((a, re.sub(r"\s+#.*", "", m.group(2).strip())))
    # setter registers from prologue:  mov REG,QWORD PTR [rdi+0xNN]
    member = {0x78: "SetBool", 0x88: "Set8", 0x98: "Set16", 0xa8: "Set32"}
    regs = {}
    for a, t in ins[:40]:
        m = re.match(r"mov\s+(\w+),QWORD PTR \[rdi\+0x([0-9a-f]+)\]", t)
        if m and int(m.group(2), 16) in member: regs[m.group(1)] = member[int(m.group(2), 16)]
    names = {}
    for r in json.load(open(ifrj)): names.setdefault(r["offset"], r)
    rows = []
    for k, (a, t) in enumerate(ins):
        m = re.match(r"mov\s+r8d,0x([0-9a-f]+)$", t)
        if not m: continue
        tok = int(m.group(1), 16); off = None; sent = None; guard = []; setter = None
        for a2, t2 in ins[k+1:k+5]:
            mm = re.match(r"call\s+(?:QWORD PTR \[rdi\+0x([0-9a-f]+)\]|(\w+))$", t2)
            if mm:
                setter = member.get(int(mm.group(1), 16)) if mm.group(1) else regs.get(mm.group(2), mm.group(2)); break
        for a2, t2 in reversed(ins[max(0, k-8):k]):
            mm = re.match(r"(?:mov|movzx)\s+r9[bwd]?,(?:BYTE|WORD|DWORD) PTR \[rbx\+0x([0-9a-f]+)\]", t2)
            if mm and off is None: off = int(mm.group(1), 16)
            mm = re.match(r"cmp\s+r9[bwd]?,(0x[0-9a-f]+|\w+)", t2)
            if mm and sent is None: sent = mm.group(1)
            mm = re.match(r"(cmp|test)\s+(?:BYTE|WORD) PTR \[rbx\+0x([0-9a-f]+)\],(\w+)", t2)
            if mm: guard.append("[0x%X] %s %s" % (int(mm.group(2), 16), mm.group(1), mm.group(3)))
        n = names.get(off, {})
        rows.append(dict(addr=a, token="0x%08X" % tok, setter=setter, setup_offset=off, skip_if=sent, guards=guard[:2],
                         prompt=n.get("prompt"), ifr_default=n.get("default")))
    return rows
if __name__ == "__main__":
    rows = main(*sys.argv[1:5])
    if "--json" in sys.argv: json.dump(rows, open(sys.argv[sys.argv.index("--json") + 1], "w"), indent=1)
    for r in rows:
        print("%05X %s %-7s off=%-6s skip_if=%-6s %-40s guards=%s" % (r["addr"], r["token"], r["setter"], "0x%X" % r["setup_offset"] if r["setup_offset"] is not None else "-", r["skip_if"], (r["prompt"] or "")[:40], ";".join(r["guards"])))

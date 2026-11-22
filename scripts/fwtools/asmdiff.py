#!/usr/bin/env python3
"""Normalized instruction-level diff of two PE images (objdump -d -M intel).
Abstracts RIP-relative displacements, direct branch/call targets and (optionally) PCD-token immediates
listed in a remap. Prints only non-equal opcodes. usage: asmdiff.py A.efi B.efi [--ctx N]"""
import re, subprocess, sys, difflib
def dis(p):
    t = subprocess.run(["objdump", "-d", "-M", "intel", p], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True).stdout
    norm = []; raw = []
    for l in t.splitlines():
        m = re.match(r"\s*([0-9a-f]+):\t([0-9a-f ]+)\t(.*)", l)
        if not m: continue
        ins = re.sub(r"\s+#.*$", "", m.group(3).strip())
        n = re.sub(r"\[rip[+-]0x[0-9a-f]+\]", "[rip+X]", ins)
        n = re.sub(r"^(call|jmp|j[a-z]+|loop[a-z]*)\s+0x[0-9a-f]+$", r"\1 T", n)
        norm.append(n); raw.append("%s: %s" % (m.group(1), ins))
    return norm, raw
if __name__ == "__main__":
    a, ra = dis(sys.argv[1]); b, rb = dis(sys.argv[2])
    sm = difflib.SequenceMatcher(None, a, b, autojunk=False); n = 0
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal": continue
        if all(x.startswith(("int3", "nop")) for x in a[i1:i2] + b[j1:j2]): continue
        n += 1
        print("@@ %s A[%d] B[%d]" % (tag, i2 - i1, j2 - j1))
        for x in ra[i1:i2][:40]: print("  - " + x)
        for x in rb[j1:j2][:40]: print("  + " + x)
    print("instructions: A=%d B=%d, differing hunks=%d, ratio=%.4f" % (len(a), len(b), n, sm.ratio()))

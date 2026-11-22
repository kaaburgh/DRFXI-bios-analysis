#!/usr/bin/env python3
"""Classify same-size module diffs: a differing position is 'PCD-explained' when a little-endian
u32 window covering it holds old token T (in the DXE-renumbered range) and new == shift(T), where the
shift map is derived from the PCD *name* tables of the two builds (tools/pcdnames.py).
Everything else is 'residual' and printed. usage: pcd_norm_diff.py DIR_A DIR_B NAMES_A NAMES_B"""
import sys, os, struct
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cmpidx, pcdnames
def main(A, B, NA, NB):
    na, nb = pcdnames.parse(NA), pcdnames.parse(NB)
    tmap = {na[k]: nb[k] for k in na if k in nb and na[k] != nb[k]}
    a, b = cmpidx.load(A), cmpidx.load(B); pcd_only = []; resid = {}
    for k in sorted(set(a) & set(b), key=str):
        x, y = a[k], b[k]
        if x["sha256"] == y["sha256"] or x["size"] != y["size"] or x["kind"] == "VERSION": continue
        da = open(os.path.join(A, x["file"]), "rb").read(); db = open(os.path.join(B, y["file"]), "rb").read()
        i = 0; n = len(da); expl = 0; res = []
        while i < n:
            if da[i] == db[i]: i += 1; continue
            ok = False
            for s in (i, i-1):
                if s < 0 or s + 4 > n: continue
                va = struct.unpack_from("<I", da, s)[0]; vb = struct.unpack_from("<I", db, s)[0]
                if tmap.get(va) == vb: ok = True; expl += 1; i = s + 4; break
            if not ok:
                j = i
                while j < n and (da[j] != db[j] or da[j+1:j+2] != db[j+1:j+2]): j += 1
                res.append((i, da[i:j], db[i:j])); i = j
        if res: resid[k] = (expl, res)
        else: pcd_only.append((k[0], expl))
    print("PCD-token-renumbering ONLY (%d modules):" % len(pcd_only))
    print("  " + ", ".join("%s(%d)" % p for p in pcd_only))
    print("RESIDUAL (%d modules):" % len(resid))
    for k, (expl, res) in resid.items():
        tot = sum(len(r[1]) for r in res)
        print("  %s %s: pcd_sites=%d residual_runs=%d residual_bytes=%d" % (k[0], k[1], expl, len(res), tot))
        for r in res[:6]:
            print("      %06X %s -> %s" % (r[0], r[1][:24].hex(), r[2][:24].hex()))
if __name__ == "__main__": main(*sys.argv[1:5])

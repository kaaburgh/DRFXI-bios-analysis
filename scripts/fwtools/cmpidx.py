#!/usr/bin/env python3
"""Compare two fvparse output dirs by (UI name|FFS GUID, section kind). Prints ONLY/DIFF rows and
byte-diff counts for equal-sized payloads. usage: cmpidx.py DIR_A DIR_B [--runs NAME]"""
import json, sys, os
def load(d):
    m = {}
    for r in json.load(open(os.path.join(d, "index.json"))):
        if r["kind"] == "FV": continue
        k = (r.get("ui") or r.get("ffs_guid"), r["kind"]); n = 0
        while (k + (n,)) in m: n += 1
        m[k + (n,)] = r
    return m
def runs(a, b):
    out = []; i = 0; n = len(a)
    while i < n:
        if a[i] != b[i]:
            j = i
            while j < n and (a[j] != b[j] or (j + 1 < n and a[j+1] != b[j+1])): j += 1
            out.append((i, a[i:j].hex(), b[i:j].hex())); i = j
        else: i += 1
    return out
if __name__ == "__main__":
    A, B = sys.argv[1], sys.argv[2]; a, b = load(A), load(B)
    want = sys.argv[4] if len(sys.argv) > 4 else None
    same = 0
    for k in sorted(set(a) | set(b), key=str):
        x, y = a.get(k), b.get(k)
        if not x or not y: print("ONLY_%s" % ("A" if x else "B"), k, (x or y)["size"], (x or y)["ffs_guid"])
        elif x["sha256"] == y["sha256"]: same += 1
        else:
            da = open(os.path.join(A, x["file"]), "rb").read(); db = open(os.path.join(B, y["file"]), "rb").read()
            if len(da) == len(db):
                rr = runs(da, db); print("DIFF", k, len(da), "runs=%d bytes=%d" % (len(rr), sum(len(r[1])//2 for r in rr)))
                if want and k[0] == want:
                    for r in rr: print("   %06X %s -> %s" % r)
            else: print("DIFF_SIZE", k, len(da), len(db))
    print("identical:", same)

#!/usr/bin/env python3
"""usage: getmod.py FVPARSE_DIR NAME_OR_GUID KIND [N] -> prints path of extracted payload"""
import json, sys, os
def find(d, name, kind, n=0):
    c = 0
    for r in json.load(open(os.path.join(d, "index.json"))):
        if r["kind"] == kind and (r.get("ui") == name or r.get("ffs_guid") == name):
            if c == n: return os.path.join(d, r["file"])
            c += 1
if __name__ == "__main__":
    print(find(sys.argv[1], sys.argv[2], sys.argv[3], int(sys.argv[4]) if len(sys.argv) > 4 else 0))

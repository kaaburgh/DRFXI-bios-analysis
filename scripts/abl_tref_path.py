#!/usr/bin/env python3
"""Trace the ABL "Override Timing" -> Tref -> UMC::DramTiming12 path.

Read-only. Requires capstone (pip install capstone); everything else is stdlib.
Reuses the $PS1 scanner from trefi_chain_audit.py.

For an AMD SPI image (or a single decompressed ABL overlay given with --overlay)
it reports:

  1. the "Override Timing" routine, every timing getter, its APCB token ID and
     the timing-structure offset the returned value is stored to;
  2. the TimingPtr helper used by "Program UMC Timings" and its base offset /
     per-P-state stride;
  3. the field that "Program UMC Timings" inserts into bits [15:0] of
     UMC::DramTiming12 (0x7000204 + 0x2C = 0x7000230);
  4. whether the Override Tref store lands on that field, and whether the
     Override routine is called immediately before Program UMC Timings.

Verified on DRFXI 1.15/1.17 (ABL 4C.11.90.20) and Minisforum MS-A2 FRG 1.02/1.04
(ABL 51.15.0.20 / 64.24.0.20). See docs/checkpoints/2026-11-24-trefi-abl-path.md.

Usage:
    python3 scripts/abl_tref_path.py IMAGE.BIN
    python3 scripts/abl_tref_path.py --overlay decompressed_abl.bin
"""

import argparse
import bisect
import hashlib
import importlib.util
import os
import re
import struct
import sys

import capstone

TREF_TOKEN = 0x419FF338


def load_audit_module():
    here = os.path.dirname(os.path.abspath(__file__))
    spec = importlib.util.spec_from_file_location("trefi_chain_audit", os.path.join(here, "trefi_chain_audit.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class Thumb:
    def __init__(self, data):
        self.d = data
        md = capstone.Cs(capstone.CS_ARCH_ARM, capstone.CS_MODE_THUMB)
        md.skipdata = True
        self.ins = [(i.address, i.mnemonic, i.op_str) for i in md.disasm(data, 0)]
        self.addrs = [a for a, _, _ in self.ins]
        self.by = {a: (m, o) for a, m, o in self.ins}
        self.starts = [a for a, m, o in self.ins if m in ("push", "push.w") and "lr" in o]

    def lit(self, a, op):
        m = re.search(r"\[pc, #(-?0x[0-9a-f]+|-?\d+)\]", op)
        if not m:
            return None
        loc = ((a + 4) & ~3) + int(m.group(1), 0)
        return struct.unpack_from("<I", self.d, loc)[0] if 0 <= loc <= len(self.d) - 4 else None

    def adr(self, a, op):
        m = re.match(r"\w+, #(-?0x[0-9a-f]+|-?\d+)$", op)
        return ((a + 4) & ~3) + int(m.group(1), 0) if m else None

    def cstr(self, o):
        e = self.d.find(b"\x00", o)
        return self.d[o:e].decode("latin1")

    def func_of(self, a):
        return self.starts[bisect.bisect_right(self.starts, a) - 1]

    def func_body(self, start, limit=0x1200):
        i = bisect.bisect_left(self.addrs, start)
        out = []
        while i < len(self.addrs) and self.addrs[i] < start + limit:
            a = self.addrs[i]
            if a != start and a in self.starts:
                break
            out.append((a,) + self.by[a])
            i += 1
        return out

    def string_refs(self, needle):
        hits = []
        for a, m, o in self.ins:
            if m == "adr":
                t = self.adr(a, o)
                if t is not None and 0 <= t < len(self.d) and needle in self.cstr(t):
                    hits.append(a)
        return hits


def analyse(data):
    t = Thumb(data)
    rep = {"overlay_sha256": hashlib.sha256(data).hexdigest()}

    # 1. Override Timing routine.
    ov_ref = t.string_refs("Override Timing:")[0]
    ov = t.func_of(ov_ref)
    body = t.func_body(ov, 0x1000)
    rows, cur = [], None
    for a, m, o in body:
        if m == "bl":
            g = int(o.lstrip("#"), 16)
            gb = t.func_body(g, 0x40)
            size = next((int(x[2].split("#")[1], 0) for x in gb if x[1] == "cmp" and x[2].startswith("r1, #")), None)
            toks = [v for v in (t.lit(x[0], x[2]) for x in gb if x[1].startswith("ldr"))
                    if v is not None and (v >> 16) != 0xF0F2 and not (0x20000 <= v < 0x40000)]
            cur = dict(getter=g, token=toks[0], size=size, name=None, store=None) if toks and size else None
            if cur:
                rows.append(cur)
        elif m == "adr" and cur is not None and cur["name"] is None:
            s = t.cstr(t.adr(a, o))
            if "Override" in s:
                cur["name"] = s.strip()
        elif cur is not None and cur["store"] is None and m in ("str.w", "strh.w"):
            mm = re.match(r"r3, \[r0, #(0x[0-9a-f]+)\]", o)
            if mm:
                cur["store"] = int(mm.group(1), 16)
    rows = [r for r in rows if r["name"]]  # drop helper calls that are not timing getters
    rep["override"] = {"routine": ov, "getters": rows}
    tref = next(r for r in rows if r["token"] == TREF_TOKEN)

    # 2./3. Program UMC Timings and its TimingPtr helper.
    pr_ref = t.string_refs("Program UMC Timings")[0]
    pr = t.func_of(pr_ref)
    pbody = t.func_body(pr, 0x1200)
    tp_helper = None
    for i, (a, m, o) in enumerate(pbody[:-1]):
        if m == "bl" and t.lit(pbody[i + 1][0], pbody[i + 1][2]) == 0x7000204:
            tp_helper = int(o.lstrip("#"), 16)
            break
    hb = t.func_body(tp_helper, 0x30)
    base_add = next(int(re.match(r"r0, r0, #(0x[0-9a-f]+|\d+)$", x[2]).group(1), 0) for x in hb
                    if x[1] in ("add.w", "addw") and re.match(r"r0, r0, #(0x[0-9a-f]+|\d+)$", x[2]))
    stride = None
    for x in hb:
        if x[1] == "movs" and x[2].endswith("#0x59"):
            stride = 0x59 * 4
        if x[1] == "add.w" and x[2].endswith("lsl #5"):
            stride = 33 * 8
    field = None
    for i, (a, m, o) in enumerate(pbody):
        if m == "bfi" and o.endswith("#0, #0x10"):
            for b in pbody[max(0, i - 5):i]:
                mm = re.match(r"r\d+, \[r4, #(0x[0-9a-f]+)\]", b[2])
                if b[1] in ("ldr", "ldrh", "ldr.w", "ldrh.w") and mm:
                    field = (int(mm.group(1), 16), a)
            if field:
                break
    rep["program"] = {"routine": pr, "timingptr_helper": tp_helper, "timingptr_base": base_add,
                      "pstate_stride": stride, "dramtiming12_tref_field": field}

    # 4. Consistency and call order.
    rep["tref_store_matches_dramtiming12_field"] = (tref["store"] - base_add == field[0])
    order = None
    for i, (a, m, o) in enumerate(t.ins[:-1]):
        if m == "bl" and o == "#%#x" % ov and t.ins[i + 1][1] == "bl" and t.ins[i + 1][2] == "#%#x" % pr:
            order = a
    rep["override_then_program_call_site"] = order
    return rep


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("image")
    ap.add_argument("--overlay", action="store_true", help="input is an already-decompressed ABL overlay")
    args = ap.parse_args()
    data = open(args.image, "rb").read()
    if args.overlay:
        overlays = [(None, None, data)]
    else:
        audit = load_audit_module()
        seen, overlays = set(), []
        for off, ver, note, body in audit.scan_ps1(data):
            if body and b"\n\tOverride Timing:\n" in body and hashlib.sha256(body).digest() not in seen:
                seen.add(hashlib.sha256(body).digest())
                overlays.append((off, ver, body))
    for off, ver, body in overlays:
        rep = analyse(body)
        print("ABL overlay at %s ver %s sha256 %s" % (hex(off) if off is not None else "-", ver or "-", rep["overlay_sha256"]))
        o = rep["override"]
        print("  Override Timing routine @%#x" % o["routine"])
        for r in o["getters"]:
            print("    %-30s getter %#06x token %08X size %s store +%s" % (
                r["name"], r["getter"], r["token"], r["size"], hex(r["store"]) if r["store"] is not None else "(other form)"))
        p = rep["program"]
        print("  Program UMC Timings @%#x; TimingPtr helper @%#x = base + Pstate*%#x + %#x" % (
            p["routine"], p["timingptr_helper"], p["pstate_stride"] or 0, p["timingptr_base"]))
        print("  DramTiming12[15:0] <- TimingPtr+%#x (bfi @%#x)" % p["dramtiming12_tref_field"])
        print("  Override Tref store lands on that field:", rep["tref_store_matches_dramtiming12_field"])
        print("  Override immediately followed by Program UMC Timings at call site:",
              hex(rep["override_then_program_call_site"]) if rep["override_then_program_call_site"] is not None else None)


if __name__ == "__main__":
    sys.exit(main())

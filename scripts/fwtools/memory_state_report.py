#!/usr/bin/env python3
"""Offline, read-only report of the *effective* DRFXI memory configuration state.

Inputs are files the owner produced with read-only operations (nothing here touches hardware):
  --spi DUMP.bin        32 MiB SPI image saved from the running board (e.g. AFU "save current ROM image to file", /O)
  --amdsetup FILE       AmdSetupRPL contents: efivarfs export (4-byte attribute prefix + 0x6D5 data) or raw 0x6D5 bytes
  --aodsetup FILE       AodSetupRpl contents: efivarfs export (4-byte attribute prefix + 0x1AC data) or raw 0x1AC bytes
                        (--amdsetup/--aodsetup alone, e.g. read from /sys/firmware/efi/efivars on a live Linux, give the
                        re-entry sheet without an SPI image; APCB state then stays unknown)
  --compare DUMP2.bin   second SPI image (e.g. after an update and re-entry): prints only what differs in the
                        effective memory configuration between --spi (A) and --compare (B)
  --map JSON            evidence/memory-117/cbs-apcb-map.json (default: repository copy)
  --questions JSON      evidence/memory-117/setup-questions.json (default: repository copy)

What it reports
  * which official build the dump's APCB belongs to (UniqueAPCBInstance),
  * APCB override tokens actually stored in SPI (purpose-3 CBS / other instances) with setup names,
  * whether APOB NV (saved training data, flash 0x125000) is blank or populated,
  * AmdSetupRPL (from the dump's NVRAM or from --amdsetup): DRAM fields, Ctrl gates,
  * the APCB tokens a CBS sync would produce from that variable and every divergence from SPI,
  * the boot-time resync predicate: AmdSetupRPL[0x08] vs APCB token 0xB331378E ('RECV' = recovery reset),
  * the AmdSetupRPL header signature (0xFC4053AA; anything else is migrated over code defaults on the next boot),
  * a re-entry sheet: every CBS (AmdSetupRPL) and AMD Overclocking (AodSetupRpl) question whose stored value differs
    from its default, with Ctrl/value pairs shown only when the Ctrl is Manual (this is what has to be typed in again
    after a full-image flash, which recreates both variables from defaults).

Limitations: the NVAR chain walker follows the public UEFITool interpretation (Next = offset relative to the
entry, 0xFFFFFF terminates). AodSetupRpl defaults are the IFR defaults (the variable is not in StdDefaults).
The question tables come from the 1.15/1.17 IFR (identical); an older build's variable layout is assumed equal
(true for 1.12 per docs/findings/hii-ifr.md).
"""
import argparse, json, os, struct, sys, uuid
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import apcb, nvar  # noqa: E402

KNOWN_APCB_IDS = {0x09CC: "1.04", 0x5BBC: "1.07", 0x272F: "1.12", 0x69FF: "1.15", 0x4E98: "1.17"}
APCB_MAIN, APCB_USER, APCB_USER_BAK, APOB_NV, APOB_NV_SIZE = 0x51D400, 0x522000, 0x525000, 0x125000, 0x28000
NV_MAIN, NV_BACKUP, NV_SIZE = 0x1BE0000, 0x1BC0000, 0x20000
SETUP_GUID = "3a997502-647a-4c82-998e-52ef9486a247"
AOD_GUID = "5ed15dc0-edef-4161-9151-6014c4cc630c"
NV_STORE_FFS = uuid.UUID("cef5b9a3-476d-497f-9fdc-e98143e0422c").bytes_le
REGVAL = {"r13b": 1, "bpl": 0xFF, "r15b": 0xF}
WIDTH = {"SetBool": 1, "Set8": 1, "Set16": 2, "Set32": 4}
AMDSETUP_SIZE, AODSETUP_SIZE = 0x6D5, 0x1AC
GEN_TOKEN, GEN_CODE_DEFAULT, RECV = 0xB331378E, 0x4B9D5809, 0x56434552
# AodSetupRpl fields that only take effect when another field selects them (from the AOD IFR layout)
AOD_GATES = {0x193: (0x192, "VDDIO Ctrl"), 0x195: (0x192, "VDDIO Ctrl"), 0x197: (0x192, "VDDIO Ctrl"),
             0x199: (0x19B, "VPP Ctrl"), 0x98: (0x97, "VDD Misc Control"), 0x1A6: (0x1A3, "LCLK Frequency Control")}
AOD_RUNTIME_Q = {0x197: dict(offset=0x197, width=2, kind="numeric", prompt="APU VDDIO Adjust (runtime question, AodDxe 0xC5C5)",
                             options=[], range=None, default=1100)}


def nvar_variables(store):
    """Return {(name, guid): latest_data} following AMI NVAR update chains."""
    ents = nvar.parse(store); by_off = {e["off"]: e for e in ents}; out = {}
    for e in ents:
        if e["name"] is None or not (e["attr"] & 0x80): continue
        cur, hops = e, 0
        while cur["next"] != 0xFFFFFF and hops < 4096:
            nxt = by_off.get(cur["off"] + cur["next"])
            if nxt is None: break
            cur, hops = nxt, hops + 1
        out[(e["name"], e["guid"].split(":", 1)[-1])] = cur["data"]
    return out


def expected_tokens(setup, cmap):
    exp = {}
    for r in cmap["entries"]:
        off = r["setup_offset"]
        if off is None or r["setter"] not in WIDTH: continue
        ok = True
        for g in r["guards"]:
            parts = g.split()
            if len(parts) == 3 and parts[1] == "cmp" and parts[2] in REGVAL:
                if setup[int(parts[0][1:-1], 16)] != REGVAL[parts[2]]: ok = False
            else:
                ok = None   # guard semantics not modelled
        val = int.from_bytes(setup[off:off + WIDTH[r["setter"]]], "little")
        sk = r["skip_if"]
        if sk is not None:
            skv = REGVAL.get(sk, int(sk, 16) if sk.startswith("0x") else None)
            if skv is not None and val == skv: ok = False
        exp[int(r["token"], 16)] = (ok, val, r["prompt"] or "(unnamed)")
    return exp


def read_efivar(path, size):
    raw = open(path, "rb").read()
    return raw[4:] if len(raw) == size + 4 else raw


def collect_spi(path):
    """Parse one SPI image into a plain dict (no printing)."""
    d = open(path, "rb").read()
    st = dict(path=path, size=len(d), notes=[], overrides={}, vars={}, nv_areas=[])
    if len(d) != 32 * 1024 * 1024:
        st["notes"].append("dump is %d bytes, expected 32 MiB (33554432); fixed flash offsets may not apply" % len(d))
    for base in (APCB_MAIN, APCB_USER, APCB_USER_BAK):
        if d[base:base + 4] != b"APCB":
            hits = []; i = d.find(b"APCB")
            while i >= 0 and len(hits) < 8: hits.append(i); i = d.find(b"APCB", i + 1)
            st["notes"].append("no APCB header at 0x%X; 'APCB' signatures found at %s" % (base, ", ".join("0x%X" % h for h in hits) or "none"))
            continue
        a = apcb.walk(d, base)
        if base == APCB_MAIN:
            st["main"] = dict(uid=a["unique_id"], build=KNOWN_APCB_IDS.get(a["unique_id"], "unknown build"), sha=a["sha_payload"])
            continue
        toks, nontok = {}, []
        for g in a["groups"]:
            for t in g["types"]:
                if g["gid"] != 0x3000: nontok.append((t["inst"], t["prio"], t["gid"], t["tid"], t["size"], t["sha"]))
                for tid, val in t["tokens"]: toks[(t["inst"], t["prio"], tid)] = val
        st["overrides"][base] = dict(uid=a["unique_id"], size=a["size"], tokens=toks, nontoken=nontok)
    apob = d[APOB_NV:APOB_NV + APOB_NV_SIZE]
    st["apob_blank"] = apob.count(0xFF) == len(apob)
    st["apob_head"] = apob[:16].hex()
    best = None
    for base in (NV_MAIN, NV_BACKUP):          # AMI alternates the live store between the two NV areas
        nv = d[base:base + NV_SIZE]
        f = nv.find(NV_STORE_FFS)
        if f < 0:
            st["nv_areas"].append((base, None)); continue
        fsize = int.from_bytes(nv[f + 20:f + 23], "little")
        vars_ = nvar_variables(nv[f + 24:f + fsize])
        st["nv_areas"].append((base, sorted(k[0] for k in vars_)))
        if best is None or len(vars_) > len(best[1]): best = (base, vars_)
    if best:
        st["live_nv"] = best[0]
        st["vars"]["AmdSetupRPL"] = best[1].get(("AmdSetupRPL", SETUP_GUID))
        st["vars"]["AodSetupRpl"] = best[1].get(("AodSetupRpl", AOD_GUID))
    return st


def _val(buf, q):
    if buf is None or q["offset"] + q["width"] > len(buf): return None
    return int.from_bytes(buf[q["offset"]:q["offset"] + q["width"]], "little")


def _fmt(q, v):
    names = {val: n for n, val in q["options"]}
    return "%s" % names[v] if v in names else str(v)


def sheet(buf, questions, varname):
    """Non-default, *active* settings of one setup variable as {offset: (prompt, text)}.
    Ctrl/value pairs are reported as the value when the Ctrl is Manual; values gated off by an Auto
    control and the AmdSetupRPL header (0x00-0x1F) or unnamed internal fields are left out."""
    out = {}
    if buf is None: return out
    by = {q["offset"]: q for q in questions if q["default"] is not None and not q["prompt"].startswith("#")}
    if varname == "AmdSetupRPL": by = {o: q for o, q in by.items() if o >= 0x20}
    if varname == "AodSetupRpl": by.update({o: q for o, q in AOD_RUNTIME_Q.items() if o not in by})
    skip = set()
    for o, q in sorted(by.items()):
        nxt = by.get(o + 1)
        if q["prompt"].endswith(" Ctrl") and nxt is not None and nxt["prompt"] == q["prompt"][:-5]:
            skip.update((o, o + 1))
            opts = {n: v for n, v in q["options"]}
            manual, auto = opts.get("Manual", 1), opts.get("Auto", 0)
            c, v = _val(buf, q), _val(buf, nxt)
            if c == manual:
                out[o] = (nxt["prompt"], "%s (%s = Manual)" % (_fmt(nxt, v), q["prompt"]))
            elif c is not None and c != auto and c != q["default"]:
                out[o] = (q["prompt"], _fmt(q, c))
    for o, q in sorted(by.items()):
        if o in skip: continue
        v = _val(buf, q)
        if v is None or v == q["default"]: continue
        if varname == "AodSetupRpl" and o in AOD_GATES and buf[AOD_GATES[o][0]] == 0: continue
        out[o] = (q["prompt"], _fmt(q, v))
    return out


def gate_notes(setup, aod):
    n = []
    if setup is not None and setup[0x116] != 1:
        n.append("CBS 'Active Memory Timing Settings' [0x116] is not Enabled -> CBS speed/timing values below are NOT pushed to APCB")
    if aod is not None and aod[0x3C] != 1:
        n.append("AOD 'Active Memory Timing Settings' [0x3C] is not Enabled -> AOD speed/timing values are not applied")
    return n


def print_sheet(setup, aod, qt):
    print("\nRe-entry sheet (stored value differs from default; Ctrl/value pairs only when Ctrl = Manual):")
    for line in gate_notes(setup, aod): print("  NOTE: " + line)
    for varname, buf, menu in (("AmdSetupRPL", setup, "AMD CBS"), ("AodSetupRpl", aod, "AMD Overclocking")):
        if buf is None:
            print("  [%s / %s] not in the input (absent from NVRAM after a full-image flash -> recreated from defaults)" % (menu, varname)); continue
        s = sheet(buf, qt[varname], varname)
        print("  [%s / %s] %d non-default entries" % (menu, varname, len(s)))
        for o, (p, t) in sorted(s.items()):
            print("    0x%04X %-44s %s" % (o, p[:44], t))


def report(st, cmap, qt, names):
    for n in st["notes"]: print("WARNING: " + n)
    if "main" in st:
        print("main APCB UniqueAPCBInstance=0x%04X (%s), payload sha256 %s" % (st["main"]["uid"], st["main"]["build"], st["main"]["sha"][:16]))
    for base, o in st["overrides"].items():
        print("override APCB @%X UniqueAPCBInstance=0x%04X size=0x%X" % (base, o["uid"], o["size"]))
        for inst, prio, gid, tid, size, _ in o["nontoken"]:
            print("   inst=%d prio=0x%02X type gid=0x%04X tid=0x%04X size=0x%X (non-token override)" % (inst, prio, gid, tid, size))
        for (inst, prio, tid), val in o["tokens"].items():
            print("   inst=%d prio=0x%02X token 0x%08X = 0x%X  %s" % (inst, prio, tid, val, names.get(tid) or ("CBS sync generation id" if tid == GEN_TOKEN else "")))
    print("APOB NV @%X: %s" % (APOB_NV, "blank (all 0xFF) -> next boot trains from scratch" if st["apob_blank"] else "populated, first bytes %s" % st["apob_head"]))
    for base, vs in st["nv_areas"]:
        if vs is None: print("NVRAM area @%X: no store (blank or foreign)" % base)
        else: print("NVRAM area @%X: %d named variables%s" % (base, len(vs), (": " + ", ".join(vs)) if len(vs) < 6 else ""))
    aod = st["vars"].get("AodSetupRpl")
    if "live_nv" in st:
        print("   using area @%X as the live store" % st["live_nv"])
        if aod is not None:
            print("   AodSetupRpl: %d bytes; VDDIO Ctrl[0x192]=%d DIMM VDD[0x193]=%d DIMM VDDQ[0x195]=%d APU VDDIO[0x197]=%d VPP[0x199]=%d UCLK DIV1[0x96]=0x%02X Active Mem Timing[0x3C]=0x%02X" % (
                len(aod), aod[0x192], struct.unpack_from("<H", aod, 0x193)[0], struct.unpack_from("<H", aod, 0x195)[0], struct.unpack_from("<H", aod, 0x197)[0], struct.unpack_from("<H", aod, 0x199)[0], aod[0x96], aod[0x3C]))
        if st["vars"].get("AmdSetupRPL") is None:
            print("   AmdSetupRPL not stored -> CbsSetupDxeRPL recreates it from code defaults (generation 0x4B9D5809);\n"
                  "   a resync runs only if the override APCB token 0xB331378E differs from 0x4B9D5809")


def report_setup(setup, spi_tokens, cmap, qt, aod):
    if len(setup) != 0x6D5: print("WARNING: AmdSetupRPL length 0x%X != 0x6D5" % len(setup))
    sig = struct.unpack_from("<I", setup, 0)[0]
    if sig != 0xFC4053AA:
        ln = struct.unpack_from("<I", setup, 4)[0]
        if 0x21 <= ln <= 0x6D4:
            print("\nAmdSetupRPL header signature 0x%08X != 0xFC4053AA -> next boot keeps bytes 0x20..0x%X and takes everything else from code defaults (generation 0x4B9D5809)" % (sig, ln))
        else:
            print("\nAmdSetupRPL header signature 0x%08X != 0xFC4053AA and length field 0x%X out of range -> next boot REPLACES all settings with code defaults" % (sig, ln))
    gen = struct.unpack_from("<I", setup, 8)[0]
    print("\nAmdSetupRPL: [0x08] sync generation = 0x%08X; Active Memory Timing Settings [0x116] = 0x%02X (%s); Memory Context Restore [0x263] = 0x%02X; Power Down [0x16F] = 0x%02X; iGPU [0x44] = 0x%02X" % (
        gen, setup[0x116], {1: "Enabled", 0xFF: "Auto -> no timing token is pushed"}.get(setup[0x116], "?"), setup[0x263], setup[0x16F], setup[0x44]))
    if spi_tokens:
        tok = spi_tokens.get(GEN_TOKEN)
        print("boot-time resync predicate: AmdSetupRPL[0x08]=0x%08X vs APCB 0xB331378E=%s -> %s" % (
            gen, "0x%08X" % tok if tok is not None else "absent",
            "in sync (no automatic resync)" if tok == gen else
            ("'RECV' -> CbsSetupDxeRPL resets CBS to code defaults and resyncs" if tok == RECV else "MISMATCH -> CbsSetupDxeRPL resyncs APCB on next boot (APCB flush -> memory context discarded)")))
    exp = expected_tokens(setup, cmap)
    print("\nDRAM-relevant CBS entries (expected after a CBS sync vs. stored in SPI override APCB):")
    for tid, (ok, val, name) in exp.items():
        off = [r["setup_offset"] for r in cmap["entries"] if int(r["token"], 16) == tid][0]
        if not (off in (0x44, 0x46, 0x260, 0x263) or 0x116 <= off <= 0x17F): continue
        want = val if ok else None
        have = spi_tokens.get(tid) if spi_tokens else "n/a"
        flag = "" if not spi_tokens or have == want or ok is None else "   <-- DIVERGES"
        print("  0x%08X %-32s setup=%-6s pushed=%-5s spi=%s%s" % (tid, name[:32], val, {True: "yes", False: "no", None: "?"}[ok], ("0x%X" % have) if isinstance(have, int) else ("absent" if spi_tokens else "n/a"), flag))
    print_sheet(setup, aod, qt)


def compare(a, b, qt, names):
    """Print every difference in the effective memory configuration between two parsed dumps."""
    diffs = 0
    def line(s):
        nonlocal diffs; diffs += 1; print("  " + s)
    print("\nComparison A=%s  B=%s" % (a["path"], b["path"]))
    print("  builds: A main APCB %s, B main APCB %s (expected to differ across an update)" % (a.get("main", {}).get("build"), b.get("main", {}).get("build")))
    print("  APOB NV: A %s, B %s (informational)" % ("blank" if a["apob_blank"] else "populated", "blank" if b["apob_blank"] else "populated"))
    ta = a["overrides"].get(APCB_USER, {}).get("tokens", {}); tb = b["overrides"].get(APCB_USER, {}).get("tokens", {})
    print("[override APCB tokens @0x%X, keyed by instance/priority/token]" % APCB_USER)
    for k in sorted(set(ta) | set(tb)):
        if ta.get(k) != tb.get(k):
            inst, prio, tid = k
            f = lambda v: "absent" if v is None else "0x%X" % v
            line("inst=%d prio=0x%02X 0x%08X %-32s A=%s B=%s" % (inst, prio, tid, (names.get(tid) or ("CBS sync generation id" if tid == GEN_TOKEN else ""))[:32], f(ta.get(k)), f(tb.get(k))))
    na = {x[:4] + (x[5],) for x in a["overrides"].get(APCB_USER, {}).get("nontoken", [])}
    nb = {x[:4] + (x[5],) for x in b["overrides"].get(APCB_USER, {}).get("nontoken", [])}
    for x in sorted(na ^ nb):
        line("non-token override inst=%d prio=0x%02X gid=0x%04X tid=0x%04X sha=%s only in %s" % (x[0], x[1], x[2], x[3], x[4], "A" if x in na else "B"))
    for varname, menu in (("AmdSetupRPL", "AMD CBS"), ("AodSetupRpl", "AMD Overclocking")):
        sa = sheet(a["vars"].get(varname), qt[varname], varname); sb = sheet(b["vars"].get(varname), qt[varname], varname)
        print("[%s / %s non-default settings]" % (menu, varname))
        if a["vars"].get(varname) is None or b["vars"].get(varname) is None:
            line("variable present: A=%s B=%s" % (a["vars"].get(varname) is not None, b["vars"].get(varname) is not None))
        for o in sorted(set(sa) | set(sb)):
            if sa.get(o) != sb.get(o):
                f = lambda e: "default/Auto" if e is None else e[1]
                line("0x%04X %-40s A=%s | B=%s" % (o, (sa.get(o) or sb.get(o))[0][:40], f(sa.get(o)), f(sb.get(o))))
    print("\nRESULT: %s" % ("no difference in the effective memory configuration" if diffs == 0 else "%d difference(s) listed above" % diffs))
    return diffs


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--spi"); ap.add_argument("--amdsetup"); ap.add_argument("--aodsetup"); ap.add_argument("--compare")
    ap.add_argument("--map", default=os.path.join(HERE, "..", "..", "evidence", "memory-117", "cbs-apcb-map.json"))
    ap.add_argument("--questions", default=os.path.join(HERE, "..", "..", "evidence", "memory-117", "setup-questions.json"))
    a = ap.parse_args()
    cmap = json.load(open(a.map)); qt = json.load(open(a.questions))
    names = {int(r["token"], 16): r["prompt"] for r in cmap["entries"]}
    if a.compare:
        if not a.spi: ap.error("--compare needs --spi")
        sys.exit(1 if compare(collect_spi(a.spi), collect_spi(a.compare), qt, names) else 0)
    setup = aod = None; spi_tokens = {}
    if a.spi:
        st = collect_spi(a.spi)
        report(st, cmap, qt, names)
        spi_tokens = {tid: v for (inst, prio, tid), v in st["overrides"].get(APCB_USER, {}).get("tokens", {}).items()}
        setup, aod = st["vars"].get("AmdSetupRPL"), st["vars"].get("AodSetupRpl")
    if a.amdsetup: setup = read_efivar(a.amdsetup, AMDSETUP_SIZE)
    if a.aodsetup: aod = read_efivar(a.aodsetup, AODSETUP_SIZE)
    if setup is None:
        if aod is not None: print_sheet(None, aod, qt)
        return
    report_setup(setup, spi_tokens, cmap, qt, aod)


if __name__ == "__main__":
    main()

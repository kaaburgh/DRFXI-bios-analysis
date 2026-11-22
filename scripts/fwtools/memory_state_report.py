#!/usr/bin/env python3
"""Offline, read-only report of the *effective* DRFXI memory configuration state.

Inputs are files the owner produced with read-only operations (nothing here touches hardware):
  --spi DUMP.bin        32 MiB SPI image saved from the running board (e.g. AFU "save current ROM image to file")
  --amdsetup FILE       AmdSetupRPL contents: efivarfs export (4-byte attribute prefix + 0x6D5 data) or raw 0x6D5 bytes
  --map JSON            evidence/memory-117/cbs-apcb-map.json (default: repository copy)

What it reports
  * which official build the dump's APCB belongs to (UniqueAPCBInstance),
  * APCB override tokens actually stored in SPI (purpose-3 CBS / other instances) with setup names,
  * whether APOB NV (saved training data, flash 0x125000) is blank or populated,
  * AmdSetupRPL (from the dump's NVRAM or from --amdsetup): DRAM fields, Ctrl gates,
  * the APCB tokens a CBS sync would produce from that variable and every divergence from SPI,
  * the boot-time resync predicate: AmdSetupRPL[0x08] vs APCB token 0xB331378E.

Limitations: the NVAR chain walker follows the public UEFITool interpretation (Next = offset relative to the
entry, 0xFFFFFF terminates) and has only been exercised on official images and synthetic chains.
"""
import argparse, json, os, struct, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import apcb, nvar  # noqa: E402

KNOWN_APCB_IDS = {0x09CC: "1.04", 0x5BBC: "1.07", 0x272F: "1.12", 0x69FF: "1.15", 0x4E98: "1.17"}
APCB_MAIN, APCB_USER, APCB_USER_BAK, APOB_NV, APOB_NV_SIZE = 0x51D400, 0x522000, 0x525000, 0x125000, 0x28000
NV_MAIN, NV_SIZE = 0x1BE0000, 0x20000
SETUP_GUID = "3a997502-647a-4c82-998e-52ef9486a247"
REGVAL = {"r13b": 1, "bpl": 0xFF, "r15b": 0xF}
WIDTH = {"SetBool": 1, "Set8": 1, "Set16": 2, "Set32": 4}

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

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--spi"); ap.add_argument("--amdsetup")
    ap.add_argument("--map", default=os.path.join(HERE, "..", "..", "evidence", "memory-117", "cbs-apcb-map.json"))
    a = ap.parse_args()
    cmap = json.load(open(a.map)); names = {int(r["token"], 16): r["prompt"] for r in cmap["entries"]}
    setup = None; spi_tokens = {}
    if a.spi:
        d = open(a.spi, "rb").read()
        if len(d) != 32 * 1024 * 1024: print("WARNING: dump is %d bytes, expected 32 MiB" % len(d))
        m = apcb.walk(d, APCB_MAIN)
        print("main APCB UniqueAPCBInstance=0x%04X (%s), payload sha256 %s" % (m["unique_id"], KNOWN_APCB_IDS.get(m["unique_id"], "unknown build"), m["sha_payload"][:16]))
        for base in (APCB_USER, APCB_USER_BAK):
            u = apcb.walk(d, base)
            print("override APCB @%X UniqueAPCBInstance=0x%04X size=0x%X" % (base, u["unique_id"], u["size"]))
            for g in u["groups"]:
                for t in g["types"]:
                    for tid, val in t["tokens"]:
                        print("   inst=%d prio=0x%02X token 0x%08X = 0x%X  %s" % (t["inst"], t["prio"], tid, val, names.get(tid) or ("CBS sync generation id" if tid == 0xB331378E else "")))
                        if base == APCB_USER: spi_tokens[tid] = val
        apob = d[APOB_NV:APOB_NV + APOB_NV_SIZE]
        print("APOB NV @%X: %s" % (APOB_NV, "blank (all 0xFF) -> next boot trains from scratch" if apob.count(0xFF) == len(apob) else "populated, first bytes %s" % apob[:16].hex()))
        nv = d[NV_MAIN:NV_MAIN + NV_SIZE]
        import uuid
        f = nv.find(uuid.UUID("cef5b9a3-476d-497f-9fdc-e98143e0422c").bytes_le)   # NVRAM store FFS file
        if f >= 0:
            fsize = int.from_bytes(nv[f + 20:f + 23], "little")
            vars_ = nvar_variables(nv[f + 24:f + fsize])
            print("NVRAM @%X: %d named variables: %s" % (NV_MAIN, len(vars_), ", ".join(sorted(k[0] for k in vars_))))
            setup = vars_.get(("AmdSetupRPL", SETUP_GUID))
            if setup is None: print("   AmdSetupRPL not stored -> StdDefaults apply ([0x08]=0 -> CBS resync on next boot)")
    if a.amdsetup:
        raw = open(a.amdsetup, "rb").read()
        setup = raw[4:] if len(raw) == 0x6D5 + 4 else raw
    if setup is None:
        return
    if len(setup) != 0x6D5: print("WARNING: AmdSetupRPL length 0x%X != 0x6D5" % len(setup))
    print("\nAmdSetupRPL: [0x08] sync generation = 0x%08X; Active Memory Timing Settings [0x116] = 0x%02X (%s); Memory Context Restore [0x263] = 0x%02X; Power Down [0x16F] = 0x%02X; iGPU [0x44] = 0x%02X" % (
        struct.unpack_from("<I", setup, 8)[0], setup[0x116], {1: "Enabled", 0xFF: "Auto -> no timing token is pushed"}.get(setup[0x116], "?"), setup[0x263], setup[0x16F], setup[0x44]))
    if spi_tokens:
        tok = spi_tokens.get(0xB331378E)
        print("boot-time resync predicate: AmdSetupRPL[0x08]=0x%08X vs APCB 0xB331378E=%s -> %s" % (
            struct.unpack_from("<I", setup, 8)[0], "0x%08X" % tok if tok is not None else "absent",
            "in sync (no automatic resync)" if tok == struct.unpack_from("<I", setup, 8)[0] else "MISMATCH -> CbsSetupDxeRPL resyncs APCB on next boot (APCB flush -> memory context discarded)"))
    exp = expected_tokens(setup, cmap)
    print("\nDRAM-relevant CBS entries (expected after a CBS sync vs. stored in SPI override APCB):")
    for tid, (ok, val, name) in exp.items():
        off = [r["setup_offset"] for r in cmap["entries"] if int(r["token"], 16) == tid][0]
        if not (off in (0x44, 0x46, 0x263) or 0x116 <= off <= 0x17F): continue
        want = val if ok else None
        have = spi_tokens.get(tid) if spi_tokens else "n/a"
        flag = "" if not spi_tokens or have == want or ok is None else "   <-- DIVERGES"
        print("  0x%08X %-32s setup=%-6s pushed=%-5s spi=%s%s" % (tid, name[:32], val, {True: "yes", False: "no", None: "?"}[ok], ("0x%X" % have) if isinstance(have, int) else ("absent" if spi_tokens else "n/a"), flag))

if __name__ == "__main__":
    main()

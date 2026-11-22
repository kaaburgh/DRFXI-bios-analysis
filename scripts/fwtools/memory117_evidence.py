#!/usr/bin/env python3
"""Regenerate the DRFXI 1.15 -> 1.17 DDR5-regression static evidence from the two official packages.

usage:
  python3 -I scripts/fwtools/memory117_evidence.py DRFXI_1.15_260105A.7z DRFXI_1.17_260828A.7z WORKDIR OUTDIR [--exec-fingerprint]

* WORKDIR receives the unpacked packages and extracted firmware trees (keep it OUTSIDE the repository).
* OUTDIR receives the small text/JSON evidence files (evidence/memory-117/ in the repository).
* Fail-closed: refuses to continue unless both DRFXI.BIN hashes match the official values.
* The CBS fingerprint (CbsSetupDxeRPL @0x5134) and the CBS code defaults (@0x3E58) are computed by
  scripts/fwtools/straightline_eval.py, which interprets the objdump text; no vendor code is executed.
* --exec-fingerprint optionally adds a native cross-check of the fingerprint (pure-arithmetic leaf function).

Requirements: Python 3.10+, system libarchive (for 7z), binutils objdump with pei-x86-64 support.
Only first-party code is used; no vendor tools are invoked.
"""
import hashlib, json, os, re, struct, subprocess, sys, uuid

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import un7z, fvparse, cmpidx, pcdnames, pspdir, apcb, nvar, ifrmini, cbs_apcb_map, getmod  # noqa: E402
import straightline_eval  # noqa: E402,F401

EXPECTED = {
    "115": "3afaba6d916b3897d1d98bd5913008b38e89b6c51b2c6963c7109793541d8d88",
    "117": "99f3bab5ea491202bf365c23e6416f9d1e8a649ad00f90c1f3e21f1a61e35c51",
}
FINGERPRINT_FN = (0x5134, 0x5EDF)            # CbsSetupDxeRPL file offset == RVA (.text RVA == raw offset)
APCB_MAIN, APCB_USER, APCB_USER_BAK = 0x51D400, 0x522000, 0x525000
CBS_SYNC_FN = ("45c4", "5112")
PCD_NAME_FFS = "d45f6c15-a525-4f32-9191-676fa086918b"
DEFAULTS_FFS = "9221315b-30bb-46b5-813e-1b1bf4712bd3"

def sha(b): return hashlib.sha256(b).hexdigest()
def w(outdir, name, text):
    with open(os.path.join(outdir, name), "w") as f: f.write(text.rstrip() + "\n")
    print("wrote", name)
def objdump(path):
    return subprocess.run(["objdump", "-d", "-M", "intel", path], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True).stdout
def asm_range(asm, lo, hi):
    out = []
    for l in asm.splitlines():
        m = re.match(r"\s*([0-9a-f]+):\t[0-9a-f ]+\t(.*)", l)
        if m and lo <= int(m.group(1), 16) < hi: out.append("%6X: %s" % (int(m.group(1), 16), re.sub(r"\s+", " ", m.group(2).strip())))
    return out
def mod(tree, name, kind="PE32", n=0):
    p = getmod.find(tree, name, kind, n)
    if not p: raise SystemExit("module not found: %s %s in %s" % (name, kind, tree))
    return p
def default_vars(tree):
    raw = open(mod(tree, DEFAULTS_FFS, "RAW"), "rb").read()
    inner = nvar.parse(raw)[0]["data"]
    return {(e["name"], e["guid"].split(":", 1)[-1]): e["data"] for e in nvar.parse(inner)}

def main():
    a7z, b7z, work, out = sys.argv[1:5]; execfp = "--exec-fingerprint" in sys.argv
    os.makedirs(work, exist_ok=True); os.makedirs(out, exist_ok=True)
    V = {"115": a7z, "117": b7z}; T = {}; BIN = {}; PKG = {}
    ident = ["# Image identity (fail-closed check)", ""]
    for v, pkg in V.items():
        x = os.path.join(work, "x" + v)
        if not os.path.isdir(x):
            os.makedirs(x); un7z.main(pkg, x)
        files = sorted(os.path.join(dp, f) for dp, dn, fn in os.walk(x) for f in fn)
        ident.append("package %s  sha256=%s" % (os.path.basename(pkg), sha(open(pkg, "rb").read())))
        for f in files:
            ident.append("  %-22s %9d  %s" % (os.path.basename(f), os.path.getsize(f), sha(open(f, "rb").read())))
        binp = [f for f in files if f.endswith("DRFXI.BIN")][0]
        BIN[v] = open(binp, "rb").read(); PKG[v] = {os.path.basename(f): sha(open(f, "rb").read()) for f in files}
        if sha(BIN[v]) != EXPECTED[v]: raise SystemExit("DRFXI.BIN %s hash mismatch: %s" % (v, sha(BIN[v])))
        t = os.path.join(work, "t" + v)
        if not os.path.exists(os.path.join(t, "index.json")):
            fvparse.main(binp, t)
        T[v] = t
    same_tools = [k for k in PKG["115"] if k not in ("DRFXI.BIN", "Release_Note.txt") and PKG["115"][k] == PKG["117"].get(k)]
    ident += ["", "byte-identical non-image package files 1.15 vs 1.17: " + ", ".join(sorted(same_tools)),
              "flash command (both): " + open([os.path.join(dp, f) for dp, dn, fn in os.walk(os.path.join(work, "x117")) for f in fn if f == "EfiFlash.nsh"][0]).read().strip()]
    w(out, "01-image-identity.txt", "\n".join(ident))

    # 02 PSP / BIOS directories + ROM layout
    rows = ["# AMD PSP/BIOS directory entries (1.15 image; equality vs 1.17 at the same flash range)", "# tool: scripts/fwtools/pspdir.py", ""]
    tmpA, tmpB = os.path.join(work, "a.bin"), os.path.join(work, "b.bin")
    for p, d in ((tmpA, BIN["115"]), (tmpB, BIN["117"])):
        if not os.path.exists(p): open(p, "wb").write(d)
    r = subprocess.run([sys.executable, "-I", os.path.join(HERE, "pspdir.py"), tmpA, tmpB], stdout=subprocess.PIPE, text=True).stdout
    rows += [l for l in r.splitlines() if l.startswith(("EFS", "$PL2@019D000", "$BL2@051D000"))]
    first16 = sum(1 for i in range(0x1000000) if BIN["115"][i] != BIN["117"][i])
    rows += ["", "differing bytes in first 16 MiB (AMD/PSP part): %d" % first16]
    rl = None
    for rec in json.load(open(os.path.join(T["117"], "index.json"))):
        if rec.get("sub_guid") == "88a15a4f-977d-4682-b17c-da1f316c1f32": rl = open(os.path.join(T["117"], rec["file"]), "rb").read()
    rl115 = None
    for rec in json.load(open(os.path.join(T["115"], "index.json"))):
        if rec.get("sub_guid") == "88a15a4f-977d-4682-b17c-da1f316c1f32": rl115 = open(os.path.join(T["115"], rec["file"]), "rb").read()
    rows += ["", "# AMI ROM layout table (FFS 0dca793a-..., sub-GUID 88a15a4f-...), 24-byte records: addr(u64) offset size type attributes",
             "# identical in 1.15 and 1.17: %s (sha256 %s)" % (rl == rl115, sha(rl)[:16])]
    for o in range(0, len(rl) - 23, 24):
        a, off, size, ty, at = struct.unpack_from("<QIIII", rl, o)
        if size: rows.append("  off=0x%07X size=0x%07X type=%d attr=0x%08X" % (off, size, ty, at))
    rows.append("# attribute bit meanings are AMI-private and NOT decoded here; no conclusion is drawn from them.")
    w(out, "02-psp-bios-directories-and-rom-layout.txt", "\n".join(rows))

    # 03 APCB
    rows = ["# APCB v3 blobs (header layout per linuxboot/fiano pkg/amd/apcb/internal.go: UniqueAPCBInstance @+0x0C)", ""]
    infos = {}
    for v in ("115", "117"):
        for base in (APCB_MAIN, APCB_USER, APCB_USER_BAK):
            i = apcb.walk(BIN[v], base); infos[(v, base)] = i
            rows.append("%s APCB@%X size=0x%X UniqueAPCBInstance=0x%04X checksum=0x%02X payload_sha256=%s" % (v, base, i["size"], i["unique_id"], i["checksum"], i["sha_payload"][:16]))
    for base in (APCB_MAIN, APCB_USER, APCB_USER_BAK):
        rows.append("payload (after header) identical 1.15 vs 1.17 @%X: %s" % (base, infos[("115", base)]["sha_payload"] == infos[("117", base)]["sha_payload"]))
    rows += ["", "## 1.17 type inventory (group, type, instance, priority mask, board mask)"]
    for base in (APCB_MAIN, APCB_USER):
        for g in infos[("117", base)]["groups"]:
            for t in g["types"]:
                rows.append("@%X %s gid=%04X tid=%04X inst=%d size=0x%X prio=0x%02X board=0x%04X tokens=%d body_sha=%s" % (base, g["sig"], t["gid"], t["tid"], t["inst"], t["size"], t["prio"], t["board"], len(t["tokens"]), t["sha"]))
    # SPD placeholder entries of board-mask 0x0002
    blob = BIN["117"][APCB_MAIN:APCB_MAIN + infos[("117", APCB_MAIN)]["size"]]
    o = 0
    while True:
        o = blob.find(struct.pack("<HH", 0x1704, 0x30), o)
        if o < 0: break
        tsz = struct.unpack_from("<H", blob, o + 4)[0]; bm = struct.unpack_from("<H", blob, o + 14)[0]
        if tsz > 0x100:
            body = blob[o + 16:o + tsz]
            rows.append("MEMG tid=0x30 board=0x%04X: %d DIMM entries" % (bm, struct.unpack_from("<I", body, 0)[0]))
            for k in range(4):
                e = body[4 + k * 1036:4 + (k + 1) * 1036]
                rows.append("   dimm%d SpdValid=%d DimmPresent=%d smbus=0x%02X nonzero_spd_bytes=%d" % (k, e[0], e[1], e[4], sum(1 for x in e[12:] if x)))
        o += 4
    rows += ["", "## user/override APCB tokens (1.17 @%X; identical in 1.15)" % APCB_USER]
    for g in infos[("117", APCB_USER)]["groups"]:
        for t in g["types"]:
            for tid, val in t["tokens"]: rows.append("   inst=%d prio=0x%02X token 0x%08X = 0x%X" % (t["inst"], t["prio"], tid, val))
    w(out, "03-apcb.txt", "\n".join(rows))
    main_tokens = {}
    for g in infos[("117", APCB_MAIN)]["groups"]:
        for t in g["types"]:
            for tid, val in t["tokens"]: main_tokens[tid] = ({0: "bool", 1: "u8", 2: "u16", 4: "u32"}[t["tid"]], val)

    # 04 module classification
    rpt = subprocess.run([sys.executable, "-I", os.path.join(HERE, "pcd_norm_diff.py"), T["115"], T["117"],
                          mod(T["115"], PCD_NAME_FFS, "FREEFORM_GUID"), mod(T["117"], PCD_NAME_FFS, "FREEFORM_GUID")], stdout=subprocess.PIPE, text=True).stdout
    sizes = subprocess.run([sys.executable, "-I", os.path.join(HERE, "cmpidx.py"), T["115"], T["117"]], stdout=subprocess.PIPE, text=True).stdout
    pcdd = subprocess.run([sys.executable, "-I", os.path.join(HERE, "pcdnames.py"), mod(T["115"], PCD_NAME_FFS, "FREEFORM_GUID"), mod(T["117"], PCD_NAME_FFS, "FREEFORM_GUID")], stdout=subprocess.PIPE, text=True).stdout
    mem = ["AmdMemFl1Pei", "AmdSocFl1RplPei", "AmdMemRestorePei", "AmdAgesaParameterGroupPei", "AmdMemoryHobInfoPeimRpl", "AodPei", "PcdPeim",
           "AmdMemRestoreDxe", "AmdMemRestoreDxeV2", "AmdApcbDxeV3", "AmdApcbSmmV3", "ApobRplDxe", "CbsBaseDxeRPL", "CbsSetupDxeRPL", "AodDxe", "AodSmm", "AmdPspDxeV2Rpl", "AmdMemFl1Dxe"]
    a_, b_ = cmpidx.load(T["115"]), cmpidx.load(T["117"])
    memrows = []
    for m in mem:
        ks = [k for k in a_ if k[0] == m and k[1] in ("PE32", "TE")]
        for k in ks:
            memrows.append("  %-28s %-4s copy%d  %s" % (m, k[1], k[2], "IDENTICAL" if b_.get(k) and a_[k]["sha256"] == b_[k]["sha256"] else "differs (see classification)"))
    w(out, "04-module-classification.txt", "\n".join(["# PE/TE/RAW payload classification 1.15 -> 1.17 (whole image, DXE + both PEI copies)",
        "# tools: scripts/fwtools/fvparse.py, cmpidx.py, pcdnames.py, pcd_norm_diff.py", "", "## PCD name-table diff (by name)", pcdd,
        "## memory-path modules", *memrows, "", "## size changes / added modules", *[l for l in sizes.splitlines() if l.startswith(("ONLY", "DIFF_SIZE")) and "'VERSION'" not in l],
        "", "## same-size payloads: PCD-renumbering-only vs residual", rpt,
        "## manual classification of every residual (see checkpoint 2026-11-22 for details)",
        "  build timestamps (0105101023 -> 081c110d25 = 01-05 10:10:23 -> 08-28 17:13:37): Crypto*, Nvram*, SecureBoot*, HardwareSignatureEntry, AmiRedFishApi, SecurityStubDxe, 3fd1d3a2/709e6472/daf4bf89/a59a0056 version strings",
        "  shared flash-library function (same 164-byte change): Smbios, SmbiosBoard, SmiFlash, RpmcDxe, RpmcSmm, PrepareWhiteListSmm; plus FlashDriver/FlashDriverSmm (AMI flash driver EIP)",
        "  HII string-id shifts: FboGroupForm; Setup DEPEX gains TCG storage protocol; 414d94ad: two 256-byte signature/key blobs",
        "  AmdCcxZen4Dxe: PCD token computed as 0x400-k (0x3ED -> 0x3F0, same +3 shift); CrbDxe/CrbPei: function returning BIOS version 0x10F -> 0x111",
        "  AmdCpmOemInitPeim: GPIO table reordered, identical entry set; two stores swapped (compiler order)",
        "  cef5b9a3 NVRAM store: StdDefaults shrinks by the ReFlash 7-byte 'Setup' default (see 05)"]))

    # 05 NVRAM / defaults
    rows = ["# Shipped NVRAM store and StdDefaults (AMI NVAR), tool: scripts/fwtools/nvar.py", ""]
    for v in ("115", "117"):
        store = None
        for rec in json.load(open(os.path.join(T[v], "index.json"))):
            if rec.get("ffs_guid") == "cef5b9a3-476d-497f-9fdc-e98143e0422c": store = open(os.path.join(T[v], rec["file"]), "rb").read()
        ents = nvar.parse(store)
        rows.append("%s NVRAM area @0x1BE0000 (FFS cef5b9a3): %d NVAR entries: %s" % (v, len(ents), ", ".join("%s(%d B)" % (e["name"], len(e["data"])) for e in ents)))
    D = {v: default_vars(T[v]) for v in ("115", "117")}
    rows.append("")
    for k in sorted(set(D["115"]) | set(D["117"])):
        x, y = D["115"].get(k), D["117"].get(k)
        st = "identical" if x == y else ("only in 1.15" if y is None else ("only in 1.17" if x is None else "DIFFERENT"))
        rows.append("StdDefaults %-20s %-38s %s%s" % (k[0], k[1], st, (" sha256=%s" % sha(x or y)) if k[0] == "AmdSetupRPL" else ""))
    rows += ["", "Not present in StdDefaults (created by their drivers when absent): AodSetupRpl, AMD_PBS_SETUP", "",
             "## ReFlash setup questions (GUID 80e1202e-..., the 7-byte 'Setup' removed from 1.17 StdDefaults)"]
    for v in ("115", "117"):
        txt = subprocess.run([sys.executable, "-I", os.path.join(HERE, "ifrmini.py"), mod(T[v], "ReFlash")], stdout=subprocess.PIPE, text=True).stdout
        rows += ["%s: %s" % (v, l.strip()) for l in txt.splitlines() if "checkbox" in l] or ["%s: (no checkbox questions)" % v]
    w(out, "05-nvram-and-defaults.txt", "\n".join(rows))

    # 06 IFR memory subset (CBS + AOD), identity check
    ifr = {}
    for v in ("115", "117"):
        for m, vs in (("CbsSetupDxeRPL", "AmdSetupRPL"), ("AodDxe", "AodSetupRpl")):
            j = os.path.join(work, "%s_%s_ifr.json" % (m, v))
            subprocess.run([sys.executable, "-I", os.path.join(HERE, "ifrmini.py"), mod(T[v], m), "--varstore", vs, "--json", j], stdout=subprocess.DEVNULL)
            ifr[(m, v)] = json.load(open(j))
    pat = re.compile(r"(?i)^(Active Memory|Memory Target|T(cl|rcd|rp|ras|rc|wr|rfc1|rfc2|rfcsb|rtp|faw)\b|T(cl|rcd|rp|ras|rc|wr|rfc1|rfc2|rfcsb|rtp|faw) Ctrl|Power Down|Memory Context|iGPU Configuration|UMA Frame|UCLK|VDD Misc|SoC|DIMM VDD|VDDIO|Processor ODT|DFE Read)")
    rows = ["# IFR questions relevant to DRAM (first-party scripts/fwtools/ifrmini.py)",
            "CbsSetupDxeRPL/AmdSetupRPL table identical 1.15 vs 1.17: %s (%d questions)" % (ifr[("CbsSetupDxeRPL", "115")] == ifr[("CbsSetupDxeRPL", "117")], len(ifr[("CbsSetupDxeRPL", "117")])),
            "AodDxe/AodSetupRpl table identical 1.15 vs 1.17: %s (%d questions)" % (ifr[("AodDxe", "115")] == ifr[("AodDxe", "117")], len(ifr[("AodDxe", "117")])), ""]
    dflt = D["117"][[k for k in D["117"] if k[0] == "AmdSetupRPL"][0]]
    for m in ("CbsSetupDxeRPL", "AodDxe"):
        for q in ifr[(m, "117")]:
            if pat.search(q["prompt"]):
                cur = ""
                if m == "CbsSetupDxeRPL":
                    cur = " StdDefault=%d" % int.from_bytes(dflt[q["offset"]:q["offset"] + q["width"]], "little")
                rows.append("%-12s 0x%04X w%d %-8s %-32s ifr_default=%s range=%s%s %s" % (q["varstore"], q["offset"], q["width"], q["kind"], q["prompt"], q["default"], tuple(q["range"]) if q["range"] else "", cur,
                            ", ".join("%s=0x%X" % (n, val) for n, val in q["options"][:5])))
    w(out, "06-ifr-dram-questions.txt", "\n".join(rows))
    # question tables for scripts/fwtools/memory_state_report.py (owner re-entry sheet / dump comparison)
    assert ifr[("CbsSetupDxeRPL", "115")] == ifr[("CbsSetupDxeRPL", "117")] and ifr[("AodDxe", "115")] == ifr[("AodDxe", "117")]
    qt = dict(source="DRFXI 1.17 CbsSetupDxeRPL / AodDxe IFR (identical in 1.15); AmdSetupRPL defaults = shipped StdDefaults, AodSetupRpl defaults = IFR defaults",
              AmdSetupRPL=[dict(offset=q["offset"], width=q["width"], kind=q["kind"], prompt=q["prompt"], options=q["options"], range=q["range"],
                                default=int.from_bytes(dflt[q["offset"]:q["offset"] + q["width"]], "little")) for q in ifr[("CbsSetupDxeRPL", "117")]],
              AodSetupRpl=[dict(offset=q["offset"], width=q["width"], kind=q["kind"], prompt=q["prompt"], options=q["options"], range=q["range"],
                                default=q["default"]) for q in ifr[("AodDxe", "117")]])
    json.dump(qt, open(os.path.join(out, "setup-questions.json"), "w"), indent=0)

    # 07 CBS -> APCB map
    maps = {}
    for v in ("115", "117"):
        maps[v] = cbs_apcb_map.main(mod(T[v], "CbsSetupDxeRPL"), CBS_SYNC_FN[0], CBS_SYNC_FN[1], os.path.join(work, "CbsSetupDxeRPL_%s_ifr.json" % v))
    strip = lambda rows: [{k: r[k] for k in r if k != "addr"} for r in rows]
    rows = ["# CBS setup -> APCB token push (CbsSetupDxeRPL sync routine @0x%s..0x%s), tool: scripts/fwtools/cbs_apcb_map.py" % CBS_SYNC_FN,
            "# protocol members (AMD APCB service, table in AmdApcbDxeV3 .data): +0x60 acquire, +0xC0(purpose) purge tokens, +0x78 SetBool, +0x88 Set8, +0x98 Set16, +0xA8 Set32, +0x08 flush, +0x68 release",
            "# every Set uses purpose dl=3; the routine starts with +0xC0(3), i.e. all purpose-3 tokens are purged before re-adding non-Auto values",
            "map identical 1.15 vs 1.17: %s (%d tokens)" % (strip(maps["115"]) == strip(maps["117"]), len(maps["117"])), ""]
    for r in maps["117"]:
        mt = main_tokens.get(int(r["token"], 16))
        rows.append("%s %-7s setup_off=%-6s skip_if=%-11s guards=%-34s platform_default_in_main_APCB=%-10s %s" % (
            r["token"], r["setter"], "0x%X" % r["setup_offset"] if r["setup_offset"] is not None else "-", r["skip_if"], ";".join(r["guards"]), ("%s:0x%X" % mt) if mt else "-", r["prompt"] or ""))
    w(out, "07-cbs-to-apcb-token-map.txt", "\n".join(rows))
    json.dump(dict(source="DRFXI 1.17 CbsSetupDxeRPL (identical in 1.15)", sync_routine="0x%s-0x%s" % CBS_SYNC_FN, purpose=3,
                   entries=[dict(r, platform_default_main_apcb=(dict(type=main_tokens[int(r["token"], 16)][0], value=main_tokens[int(r["token"], 16)][1]) if int(r["token"], 16) in main_tokens else None)) for r in strip(maps["117"])]),
              open(os.path.join(out, "cbs-apcb-map.json"), "w"), indent=1)

    # 08 fingerprint resync
    cbs = {v: mod(T[v], "CbsSetupDxeRPL") for v in ("115", "117")}
    cbs_asm = objdump(cbs["117"])
    rows = ["# Boot-time CBS generation check (CbsSetupDxeRPL 1.17; byte-identical routine in 1.15)",
            "## call site: Get32(APCB token 0xB331378E) vs stored AmdSetupRPL[0x08]; on mismatch store fingerprint(AmdSetupRPL) into [0x08] and run the full sync (which writes the token from [0x08])"]
    rows += asm_range(cbs_asm, 0x3C73, 0x3CBA)
    fnb = {v: open(cbs[v], "rb").read()[FINGERPRINT_FN[0]:FINGERPRINT_FN[1]] for v in ("115", "117")}
    fields = sorted(set(int(x, 16) for x in re.findall(r"\[r(?:10|cx)\+0x([0-9a-f]+)\]", "\n".join(asm_range(cbs_asm, *FINGERPRINT_FN)))))
    rows += ["", "fingerprint routine 0x%X..0x%X bytes identical 1.15/1.17: %s (sha256 %s)" % (FINGERPRINT_FN[0], FINGERPRINT_FN[1], fnb["115"] == fnb["117"], sha(fnb["117"])[:16]),
             "routine contains call/RIP-relative references: %s" % bool(re.search(r"call|rip", "\n".join(asm_range(cbs_asm, *FINGERPRINT_FN)))),
             "AmdSetupRPL offsets hashed (%d): %s" % (len(fields), " ".join("%X" % f for f in fields)),
             "boot-time trigger = AmdSetupRPL[0x08] (as prepared by the loader, see 15-*) != APCB token 0xB331378E (or Get32 fails); the fingerprint is only computed/stored on mismatch.",
             "  -> a missing variable or one with a foreign header is rebuilt from CODE defaults whose [0x08] is already 0x4B9D5809 (15-*),",
             "     so an NVRAM reset alone does NOT trigger the resync when the APCB carries the image token (CORRECTION of the first 2026-11-22 reading);",
             "  -> a Setup 'Save' calls the sync directly (RouteConfig, call site 0xC38, after SetVariable) without changing [0x08];",
             "  -> out-of-band edits of AmdSetupRPL (setup_var/AMISCE/efivar) change neither [0x08] nor the token, so they are NOT pushed to APCB by this path.",
             "fields 0x116 (Active Memory Timing Settings) and the *Ctrl bytes are not part of the fingerprint input.",
             "shipped user-APCB token 0xB331378E = 0x%X" % [val for g in infos[("117", APCB_USER)]["groups"] for t in g["types"] for tid, val in t["tokens"] if tid == 0xB331378E][0]]
    import straightline_eval as se
    for v in ("115", "117"):
        dv = D[v][[k for k in D[v] if k[0] == "AmdSetupRPL"][0]]
        _, _, fpv = se.run(se.lines_from(cbs[v], FINGERPRINT_FN[0], skip_to=0x5140), 0x6D5, init=dv)
        rows.append("evaluated %s routine (text interpreter, no execution) on %s StdDefaults AmdSetupRPL -> 0x%08X" % (v, v, fpv))
    L117 = se.lines_from(cbs["117"], FINGERPRINT_FN[0], skip_to=0x5140)
    for label, off, val in (("Active Memory Timing Settings=Enabled", 0x116, 1), ("Twr Ctrl=Manual", 0x128, 1), ("Twr=96", 0x129, 96), ("iGPU Configuration=Disabled", 0x44, 0)):
        t = bytearray(dflt); t[off] = val
        rows.append("evaluated 1.17 routine, defaults with %-38s -> 0x%08X" % (label, se.run(L117, 0x6D5, init=bytes(t))[2]))
    if execfp:
        import run_x64_leaf
        for v in ("115", "117"):
            dv = D[v][[k for k in D[v] if k[0] == "AmdSetupRPL"][0]]
            rows.append("native cross-check (--exec-fingerprint) %s -> 0x%08X" % (v, run_x64_leaf.run(cbs[v], FINGERPRINT_FN[0], FINGERPRINT_FN[1], dv)))
    w(out, "08-cbs-fingerprint-resync.txt", "\n".join(rows))

    # 09 APCB flush -> memory-context discard
    apcbm = mod(T["117"], "AmdApcbDxeV3"); a_asm = objdump(apcbm); pe = open(apcbm, "rb").read()
    rows = ["# AmdApcbDxeV3 1.17 (PCD-renumbering-only vs 1.15): APCB flush -> memory-context discard",
            "## protocol function table (.data @0xA160, member offset -> function RVA)"]
    for k in range(27):
        q = struct.unpack_from("<Q", pe, 0xA160 + 8 * k)[0]; rows.append("  +0x%02X -> 0x%X" % (8 * k, q))
    rows += ["", "## discard routine excerpt (CMOS bank 2: port 0x72/0x73 index 0x0D; bit 0x02 generic / bit 0x08 'for APCB update' per CPUID check)"]
    rows += asm_range(a_asm, 0x4101, 0x41CC)
    w(out, "09-apcb-flush-discards-memory-context.txt", "\n".join(rows + ["", "static call-graph result (depth<=4): +0x08 reaches 0x3F10 discard routine; +0x88 Set8, +0xC0 purge, +0x60, +0x68 do not",
        "strings: 0xCD00 '[AMD MemRestore] Discard current memory context', 0xCD40 '[AMD MemRestore] Discard current memory context for APCB update'"]))

    # 10 OemDxe 1.17 APCB write
    o_asm = objdump(mod(T["117"], "OemDxe"))
    w(out, "10-oemdxe-117-apcb-write.txt", "\n".join(["# OemDxe 1.17 (new in 1.17): after SetVariable(AmdSetupRPL) it mirrors iGPU Configuration into APCB token 0x1FB35295 and flushes",
        "# protocol GUID 7189e04e-6284-4953-a543-a31f89a1a7bf located via BS->LocateProtocol(+0x140); +0x80 Get8, +0x88 Set8 (purpose 3), +0x08 flush; then CF9h=06h hard reset"] + asm_range(o_asm, 0xAE1, 0xBAB)))

    # 11 SMU STABILITY_BOOST
    s = {v: mod(T[v], "SmuV13Dxe") for v in ("115", "117")}
    diff = subprocess.run([sys.executable, "-I", os.path.join(HERE, "asmdiff.py"), s["115"], s["117"]], stdout=subprocess.PIPE, text=True).stdout
    hunks = re.split(r"(?m)^@@ ", diff); keep = [h for h in hunks if re.search(r"0x496|0x4df|0x57c4|0x5b7c", h) and "+ " in h]
    tmpl = {}
    for v in ("115", "117"):
        asm = objdump(s[v]); m = re.search(r"mov +edi,0x594\n(?:.*\n){2}.*call.*\n.*lea +rdx,\[rip\+0x[0-9a-f]+\] +# 0x([0-9a-f]+)", asm)
        tmpl[v] = open(s[v], "rb").read()[int(m.group(1), 16):int(m.group(1), 16) + 0x594]
    db = open(mod(T["117"], "PcdDxe", "RAW"), "rb").read()
    length = struct.unpack_from("<I", db, 20)[0]; lt = struct.unpack_from("<I", db, 40)[0]
    e = struct.unpack_from("<I", db, lt + 4 * (0x496 - 966 - 1))[0]
    setters = []
    for rec in json.load(open(os.path.join(T["117"], "index.json"))):
        if rec["kind"] in ("PE32", "TE"):
            d = open(os.path.join(T["117"], rec["file"]), "rb").read()
            for opc in (b"\xb9", b"\xba", b"\x41\xb8"):
                if opc + b"\x96\x04\x00\x00" in d: setters.append(rec.get("ui"))
    w(out, "11-smu-stability-boost.txt", "\n".join(["# SmuV13Dxe: only non-renumbering code change 1.15 -> 1.17", diff.strip().splitlines()[-1]] + ["@@ " + h.strip() for h in keep] + [
        "", "PCD 0x496 name: gEfiAmdAgesaPkgTokenSpaceGuid.PcdCfgSmuStabilityBoost (PEI name table)",
        "PcdDxe DB 1.17: initialized length 0x%X, local token entry 0x%08X -> DATA offset 0x%X (%s)" % (length, e, e & 0xFFFFFF, "zero-initialized area" if (e & 0xFFFFFF) >= length else "initialized"),
        "modules containing a 'mov ecx|edx|r8d, 0x496' immediate (any PE/TE in 1.17): %s" % sorted(set(setters)),
        "SMU config template (0x594 bytes, copied into the structure before fields are filled) identical 1.15/1.17: %s; template[0x4DF] = 0x%02X/0x%02X" % (tmpl["115"] == tmpl["117"], tmpl["115"][0x4DF], tmpl["117"][0x4DF]),
        "=> with the PCD at its zero default the 0x594-byte table handed to the SMU is byte-identical to 1.15 at +0x4DF"]))

    # 12 AFU option evidence
    afu = open([os.path.join(dp, f) for dp, dn, fn in os.walk(os.path.join(work, "x117")) for f in fn if f == "AfuEfix64.efi"][0], "rb").read()
    strs = [m.decode() for m in re.findall(rb"[ -~]{6,}", afu)]
    want = re.compile(r"(?i)preserv|/CLRCFG|/BCPALL|Program PSP block|Program NVRAM|Program Boot Block|Program Main BIOS|non-critical blocks|Rom layout change|Entire BIOS|PLDM is|BIOS does not support|Use /CLRCFG|NVRAM/SETUP|afu5\.16")
    picked = []
    for x in strs:
        if want.search(x):
            if re.match(r"(?i)e:\\ami_code", x):
                if not re.search(r"(?i)pspflash\\pspflash\.cpp|preserveconfig|nvram\\nvramflash|afu5\.16\.01\\gdkappafu_[^\\]+\\GdkCoreSourcePkg\\Main", x): continue
                x = re.sub(r"(?i)^e:\\ami_code\\flash\\[^\\]+\\([^\\]+)\\[^\\]+\\", r"<AFU \1 build>\\", x)
            if x not in picked: picked.append(x)
    w(out, "12-afu-option-strings.txt", "\n".join(["# AfuEfix64.efi (byte-identical in the 1.15 and 1.17 packages), sha256 %s; selected strings" % sha(afu),
        "# command used by both packages: /p /b /n /k /r /l /RLC:E /reboot  (no /SP, no PSP-block option, no /CLRCFG)"] + picked[:80] + [
        "", "# firmware side: no PLDM/BCP preserve handler strings in any 1.15/1.17 module (searched PLDM, Bcp/BCP handler names); OFBD core present (Ofbd.efi)"]))

    # 13 timing arithmetic
    rows = ["# DDR5 timing arithmetic (AMD CBS/AOD timings are in MEMCLK cycles; tCK[ns] = 2000 / data-rate[MT/s])",
            "# JEDEC 16 Gb die: tRFC1 = 295 ns, tRFC2 = 160 ns, tWR = 30 ns", "",
            "%-8s %-8s %-10s %-10s %-8s %-12s %-12s %-12s" % ("MT/s", "tCK ns", "tRFC1 clk", "tRFC2 clk", "tWR clk", "968 clk=ns", "96 clk=ns", "480 clk=ns")]
    import math
    for mts in (5200, 5600, 6000, 6200, 6400, 6600):
        tck = 2000 / mts
        rows.append("%-8d %-8.4f %-10d %-10d %-8d %-12.1f %-12.1f %-12.1f" % (mts, tck, math.ceil(295 / tck - 1e-9), math.ceil(160 / tck - 1e-9), math.ceil(30 / tck - 1e-9), 968 * tck, 96 * tck, 480 * tck))
    rows += ["", "CBS/AOD Twr numeric range is 48..96 (IFR), so 96 is also the field maximum.",
             "tWR 96 clk equals exactly 30 ns at DDR5-6400; tRFC 968 clk is ~302 ns at 6400 (295 ns JEDEC 16 Gb + rounding/guard) - the pair is most consistent with ~6400 MT/s Auto (INFERENCE; the reporter's data rate is unknown).",
             "Reported 'auto' tRFC ~968 / tWR 96 are consistent with SPD/JEDEC-derived Auto values at a high data rate; they are not, by themselves, evidence that 1.17 computes Auto differently (no 1.15 Auto reading at the same frequency exists)."]
    w(out, "13-timing-arithmetic.txt", "\n".join(rows))
    # 14 SmiFlash block classification of the ROM layout (what AFU /B /P /N /K see)
    rl = {}
    for v in ("115", "117"):
        for rec in json.load(open(os.path.join(T[v], "index.json"))):
            if rec.get("sub_guid") == "00781ca1-5de3-405f-abb8-379c3c076984" and rec["kind"] == "FREEFORM_GUID":
                rl[v] = open(os.path.join(T[v], rec["file"]), "rb").read()
    def areas(b):
        out = []; o = 0x10
        while o + 40 <= len(b):
            g = str(uuid.UUID(bytes_le=b[o:o + 16])); addr, off, size, ty, at = struct.unpack_from("<QIIII", b, o + 16)
            if size == 0: break
            out.append((off, size, ty, at, g)); o += 40
        return sorted(out)
    BB, MAIN = "61c0f511-a691-4f54-974f-b9a42172ce53", ("5c60f367-a505-419a-859e-2a4ff6ca6fe5", "4f1c52d3-d824-4d2a-a2f0-ec40c23c5916")
    NV = ("fa4974fc-af1d-4e5d-bdc5-dacd6d27baec", "a7edebd8-a8d7-48f8-81fb-837656b82077")
    sf = mod(T["117"], "SmiFlash"); sf_asm = objdump(sf)
    rows = ["# SmiFlash 1.17 block-type classifier (identical logic in 1.15: SmiFlash differs only in a shared flash-library routine, see 04-*)",
            "# ROM layout source: HOB/config table 00781ca1-5de3-405f-abb8-379c3c076984 (FFS c91c3c17-..., 40-byte AMI_ROM_AREA: GUID, addr, offset, size, type, attributes)",
            "ROM layout with area GUIDs identical 1.15 vs 1.17: %s" % (rl["115"] == rl["117"]), "",
            "## classifier excerpt (entries sorted by offset; +0x20 receives the block type, +0x24 holds the attributes)"]
    rows += asm_range(sf_asm, 0x2BC0, 0x2C6A)
    rows += ["", "## rules: GUID FV_BB -> 0 BOOT_BLOCK; GUID FV_MAIN (5c60f367/4f1c52d3) -> 1 MAIN_BLOCK; GUID fa4974fc / a7edebd8 -> 2 NV_BLOCK;",
             "##        else attributes & 0x400 -> 0 BOOT_BLOCK; else -> 0x80+n NON-CRITICAL BLOCK (n counts in offset order). No area is filtered out.", ""]
    ncb = 0
    for off, size, ty, at, g in areas(rl["117"]):
        if g == BB: t = "BOOT_BLOCK (/B)"
        elif g in MAIN: t = "MAIN_BLOCK (/P)"
        elif g in NV: t = "NV_BLOCK (/N)"
        elif at & 0x400: t = "BOOT_BLOCK (/B)"
        else: t = "NCB 0x%02X (/K)" % (0x80 + ncb); ncb += 1
        what = ""
        if off == 0xC1000: what = "  <- contains PSP NV data 0xC1000, RPMC NV 0xE1000, APOB NV 0x125000, PSP L2, BIOS L2 + APCB 0x51D400-0x528000, PMU FW, microcode, mirror"
        if off == 0x1BAF000: what = "  <- ROM-layout FV"
        rows.append("  off=0x%07X size=0x%07X type=%d attr=0x%04X guid=%s -> %s%s" % (off, size, ty, at, g, t, what))
    rows += ["", "=> /p /b /n /k (the shipped command) covers every one of the %d areas, i.e. the whole 32 MiB part; the AMD/PSP range is non-critical blocks programmed by /K." % len(areas(rl["117"])),
             "AFU side (strings, 12-*): /K 'Program all non-critical blocks', 'Erasing/Updating/Verifying NCB Block'; the separate 'Program PSP block' option is not used and not needed for these NCBs."]
    w(out, "14-smiflash-block-classification.txt", "\n".join(rows))

    # 15 CBS loader / code defaults / APCB-recovery reset
    import straightline_eval
    cd = {}
    for v in ("115", "117"):
        asm = subprocess.run(["objdump", "-d", "-M", "intel", "--no-show-raw-insn", cbs[v]], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True).stdout
        lines = []; on = False
        for l in asm.splitlines():
            m = re.match(r"\s*([0-9a-f]+):\t(.*)", l)
            if not m: continue
            if int(m.group(1), 16) == 0x3E58: on = True
            if on:
                lines.append(m.group(2))
                if m.group(2).strip().startswith("ret"): break
        cd[v] = straightline_eval.run(lines, 0x6D5)[:2]
    rows = ["# CbsSetupDxeRPL boot sequence (entry 0x10C4..0x1129, identical in 1.15): allocate 'CBSD' private data, HII ConfigAccess",
            "#   (ExtractConfig 0x894, RouteConfig 0xB58 = Setup save -> sync, Callback 0xC60), then 0xD68 (APCB-recovery reset) and 0xE68 (loader)."]
    rows += asm_range(cbs_asm, 0x10E2, 0x112E)
    rows += ["", "## 0xD68: if APOB-protocol(0de50221-faaa-45ba-90b9-7bcc26ec60cf, installed by ApobRplDxe) +0x08 'ApobApcbRecoveryFlag' is set,",
             "##   or APCB token 0xB331378E == 'RECV' (0x56434552), the CBS buffer is rebuilt from code defaults, resynced and written back."]
    rows += asm_range(cbs_asm, 0xDA6, 0xE56)
    rows += ["", "fingerprint routine never returns 'RECV' (tail: cmp edx,0x56434552 / cmovne):"] + asm_range(cbs_asm, 0x5ED5, 0x5EDF)
    rows += ["", "## 0xE68 loader: GetVariable(AmdSetupRPL); missing or size != 0x6D5 -> code defaults (0x3E58) -> 0x3CC0 -> generation check -> SetVariable;",
             "##   present with header signature != code-default signature -> migrate bytes 0x20..[+4) over code defaults -> check -> SetVariable;",
             "##   present with matching signature -> generation check only."]
    rows += asm_range(cbs_asm, 0xE68, 0xFEE)
    rows += ["", "## code defaults (0x3E58) evaluated from the disassembly text by scripts/fwtools/straightline_eval.py (no native execution):"]
    for v in ("115", "117"):
        mem, mask = cd[v]; std = D[v][[k for k in D[v] if k[0] == "AmdSetupRPL"][0]]
        body_diff = [i for i in range(0x20, 0x6D5) if mask[i] and mem[i] != std[i]]
        unw_nonzero = sum(1 for i in range(0x6D5) if not mask[i] and std[i])
        rows.append("%s: header sig=0x%08X len=0x%X gen=0x%08X | written bytes %d; body differences vs StdDefaults: %d; StdDefaults non-zero where builder writes nothing: %d; StdDefaults header = %s" % (
            v, struct.unpack_from("<I", mem, 0)[0], struct.unpack_from("<I", mem, 4)[0], struct.unpack_from("<I", mem, 8)[0], sum(mask), len(body_diff), unw_nonzero, std[:12].hex()))
    rows.append("code defaults identical 1.15 vs 1.17: %s" % (cd["115"][0] == cd["117"][0]))
    rows += ["=> after an NVRAM reset the variable is recreated as StdDefaults-equivalent settings with generation 0x4B9D5809 = the image's APCB token:",
             "   no automatic resync and no CBS-side APCB flush occur when the APCB in SPI is the image copy (see 14-*)."]
    ap = mod(T["117"], "ApobRplDxe"); ap_pe = open(ap, "rb").read()
    rows += ["", "## ApobRplDxe APOB protocol interface (@0x28F0): " + ", ".join("+0x%02X->0x%X" % (8 * k, struct.unpack_from("<Q", ap_pe, 0x28F0 + 8 * k)[0]) for k in range(8)),
             "   +0x00 'Fail to get ApobApcbInstance', +0x08 'Fail to get ApobApcbRecoveryFlag' (byte +0x65 of the APOB entry), +0x10 'Fail to get DimmCfgUpdatedFlag'"]
    rows += asm_range(objdump(ap), 0x15C8, 0x162B)
    w(out, "15-cbs-loader-defaults-and-recovery-reset.txt", "\n".join(rows))

    # 16 consumers of AmdSetupRPL DRAM fields and DRAM APCB tokens
    smap = {int(r["token"], 16): r for r in maps["117"]}
    dram = {t for t, r in smap.items() if r["setup_offset"] is not None and (0x116 <= r["setup_offset"] <= 0x17F or r["setup_offset"] == 0x263)}
    g_setup = uuid.UUID("3a997502-647a-4c82-998e-52ef9486a247").bytes_le; n_setup = "AmdSetupRPL".encode("utf-16-le")
    rows = ["# Every 1.17 module that references the AmdSetupRPL GUID/name or any DRAM-related CBS APCB token (%d tokens: offsets 0x116-0x17F + MCR)" % len(dram), ""]
    for rec in json.load(open(os.path.join(T["117"], "index.json"))):
        if rec["kind"] not in ("PE32", "TE"): continue
        d = open(os.path.join(T["117"], rec["file"]), "rb").read()
        nt = sum(1 for t in dram if struct.pack("<I", t) in d)
        if g_setup in d or n_setup in d or nt:
            rows.append("  %-24s %-4s guid=%d name=%d dram_tokens=%d" % (rec.get("ui"), rec["kind"], g_setup in d, n_setup in d, nt))
    rows += ["", "## roles (manual analysis, see checkpoint 2026-11-22 AFU coverage / consumers)",
             "  CbsSetupDxeRPL  : only in-image path that pushes CBS DRAM values to APCB (Setup save; boot generation mismatch; APCB-recovery reset)",
             "  CbsBaseDxeRPL   : same loader/code defaults for its own copy; reads no DRAM field (stores only, defaults builder at 0x934)",
             "  CbsBasePeiRPL   : 32-bit PEI copy; of the CBS fields it reads only 0x110-0x113 (USB3 Port 2..5); other accesses are default stores",
             "  BctBaseSmmRPL   : SMM duplicate of the CBS sync, exposed only as SMM protocol 147f8bda-da41-45bb-bc9b-827e72dc30a1 (CPUID 0xA60F00/0xB40F00);",
             "                    no module in 1.15 or 1.17 references that protocol GUID -> not invoked by in-image code",
             "  AodSmm          : AMD Overclocking apply path: purpose-2 token writes (59-token list) and, for VDDIO Ctrl Manual/Separate,",
             "                    AodSetupRpl[0x197] (APU VDDIO Adjust, runtime-created question: AodDxe 0xC5C5 prompt 367 VarOffset 0x197)",
             "                    -> extended CMOS 0xA1 (low) / 0xA0 (high); never cleared when Ctrl returns to Auto",
             "  AmdApcbDxeV3/SmmV3: MCR token only inside the token-registration whitelist table (no code use)",
             "  OemDxe          : offset 0x44 only (iGPU), token 0x1FB35295",
             "  AmdVariableProtection: variable-policy protection, no data use"]
    rows += ["", "## AodSmm extended-CMOS write (VDDIO hand-off)"] + asm_range(objdump(mod(T["117"], "AodSmm")), 0x4CC1, 0x4D07)
    rows.append("BctBaseSmmRPL protocol GUID references outside BctBaseSmmRPL: %s" % [rec.get("ui") for v in ("115", "117") for rec in json.load(open(os.path.join(T[v], "index.json")))
        if rec["kind"] not in ("FV",) and rec.get("ui") != "BctBaseSmmRPL" and uuid.UUID("147f8bda-da41-45bb-bc9b-827e72dc30a1").bytes_le in open(os.path.join(T[v], rec["file"]), "rb").read()])
    w(out, "16-dram-setting-consumers.txt", "\n".join(rows))

    print("done")

if __name__ == "__main__":
    main()

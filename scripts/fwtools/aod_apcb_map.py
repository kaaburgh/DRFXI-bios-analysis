#!/usr/bin/env python3
"""Static AodSetupRpl -> APCB token map from AodSmm (AMD Overclocking apply path, purpose 2).

Input: `objdump -d -M intel` text of AodSmm. Every purpose-2 write is `mov r8d,TOKEN` + `mov dl,0x2` + call
through the APCB service (rsi = Set16/32, r14 = Set8, r12 = SetBool). The source is the nearest preceding
`[rbx+OFF]` load into r9, and guards are the preceding `cmp BYTE PTR [rbx+OFF],r13b|0xff` (r13b = 1) with the
direction taken from the following branch: `jne skip` -> the write needs [OFF] == v ("eq"), `je skip` -> it needs
[OFF] != v ("ne"); `cmp r9b,0xff; je` -> skip Auto. Guards are [offset, "eq"|"ne", [values]]. Two blocks are not plain loads and are matched by exact instruction shape:
  * FCLK: WORD [rbx+0x94] (MHz) is skipped when 0xFFFF and converted by a helper to the CBS FCLK option code;
  * VDDIO: `mov al,[rbx+0x192]; sub al,r13b; cmp al,r13b; ja` -> the DIMM VDDQ/VDD values and two TRUE flags are
    written only when VDDIO Ctrl is Manual (1) or Separate (2).
usage: aod_apcb_map.py AodSmm.efi [--json OUT]
"""
import json, re, subprocess, sys

SETTERS = {"rsi": "Set16/32", "r14": "Set8", "r12": "SetBool"}


def parse(asm):
    ins = []
    for l in asm.splitlines():
        m = re.match(r"\s*([0-9a-f]+):\t(?:[0-9a-f]{2} )+\s*\t(.*)$", l)
        if m: ins.append((int(m.group(1), 16), re.sub(r"\s+", " ", m.group(2).strip())))
    return ins


def build(asm):
    ins = parse(asm); rows = []
    txt = [t for _, t in ins]
    for i, (a, t) in enumerate(ins):
        m = re.match(r"mov r8d,0x([0-9a-f]+)$", t)
        if not m: continue
        near = txt[max(0, i - 3):i + 3]
        if "mov dl,0x2" not in near: continue
        call = next((x for x in txt[i + 1:i + 4] if x.startswith("call ")), "")
        setter = SETTERS.get(call.split()[-1], call)
        r = dict(addr="0x%X" % a, token="0x%08X" % int(m.group(1), 16), setter=setter, offset=None, width=None,
                 const=None, transform=None, skip_if=None, guards=[])
        for j in range(i - 1, max(-1, i - 10), -1):
            tj = txt[j]
            if tj.startswith("call ") or tj.startswith("jmp "): break
            ms = re.match(r"(?:movzx r9d,(WORD|BYTE) PTR|mov r9b,BYTE PTR|mov r9d,DWORD PTR) \[rbx\+0x([0-9a-f]+)\]", tj)
            if ms and r["offset"] is None and r["const"] is None:
                r["offset"] = int(ms.group(2), 16)
                r["width"] = {"WORD": 2, "BYTE": 1}.get(ms.group(1), 1 if "r9b" in tj else 4)
            if tj in ("mov r9b,r13b", "mov r9d,r13d") and r["offset"] is None: r["const"] = 1
            mc = re.match(r"cmp BYTE PTR \[rbx\+0x([0-9a-f]+)\],(r13b|0xff)$", tj)
            if mc:
                br = txt[j + 1].split()[0]
                assert br in ("jne", "je"), (hex(ins[j][0]), txt[j + 1])
                r["guards"].append([int(mc.group(1), 16), "eq" if br == "jne" else "ne", [1 if mc.group(2) == "r13b" else 0xFF]])
            if tj == "cmp r9b,0xff": r["skip_if"] = 0xFF
        rows.append(r)
    by = {r["token"]: r for r in rows}
    # FCLK block: movzx ecx,WORD PTR [rbx+0x94]; mov eax,0xffff; cmp cx,ax; je; call helper; mov r9b,al; ... mov r8d,0xf1823f38
    f = by.get("0xF1823F38")
    k = txt.index("movzx ecx,WORD PTR [rbx+0x94]")
    assert f and txt[k + 1] == "mov eax,0xffff" and txt[k + 2] == "cmp cx,ax" and txt[k + 3].startswith("je ") and txt[k + 5] == "mov r9b,al"
    f.update(offset=0x94, width=2, skip_if=0xFFFF, transform="fclk_mhz_to_cbs_option_code")
    # VDDIO block
    k = txt.index("mov al,BYTE PTR [rbx+0x192]", k)
    assert txt[k + 1] == "sub al,r13b" and txt[k + 2] == "cmp al,r13b" and txt[k + 3].startswith("ja ")
    end = int(txt[k + 3].split()[-1], 16)
    for r in rows:
        if int(r["addr"], 16) > ins[k][0] and int(r["addr"], 16) < end:
            r["guards"].append([0x192, "eq", [1, 2]])
    return rows


def main(pe, out=None):
    asm = subprocess.run(["objdump", "-d", "-M", "intel", pe], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True).stdout
    rows = build(asm)
    if out: json.dump(rows, open(out, "w"), indent=1)
    return rows


if __name__ == "__main__":
    rows = main(sys.argv[1], sys.argv[sys.argv.index("--json") + 1] if "--json" in sys.argv else None)
    for r in rows:
        src = ("[0x%X] w%d" % (r["offset"], r["width"])) if r["offset"] is not None else ("const %d" % r["const"] if r["const"] is not None else "computed")
        g = ";".join("[0x%X]%s%s" % (o, "==" if op == "eq" else "!=", "/".join(map(str, v))) for o, op, v in r["guards"])
        print("%s %s %-9s %-14s skip=%-6s guards=%s %s" % (r["addr"], r["token"], r["setter"], src, r["skip_if"], g or "-", r["transform"] or ""))

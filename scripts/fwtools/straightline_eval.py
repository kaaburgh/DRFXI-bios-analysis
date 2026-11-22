#!/usr/bin/env python3
"""Evaluate a straight-line x64 routine *symbolically from its objdump text* (no native execution).

Supported: mov/lea/xor/or/and/add/sub with 8/16/32/64-bit registers, immediates and [reg+disp] memory
operands where reg is the buffer argument (RCX on entry). Any branch, call, RIP-relative access or
unsupported form aborts with an error, so a result is only produced for genuinely self-contained code.
Used for CbsSetupDxeRPL's AmdSetupRPL code-defaults builder (0x3E58), which consists only of
mov/lea/or/xor and ret.

usage: straightline_eval.py PE START_HEX [--size 0x6D5] [--out FILE]
"""
import argparse, re, subprocess, sys

R64 = ["rax", "rbx", "rcx", "rdx", "rsi", "rdi", "rbp", "rsp"] + ["r%d" % i for i in range(8, 16)]
ALIAS = {}
for i, r in enumerate(["rax", "rbx", "rcx", "rdx"]):
    b = r[1]
    ALIAS.update({r: (r, 64), "e%sx" % b: (r, 32), "%sx" % b: (r, 16), "%sl" % b: (r, 8)})
for r, e, w, l in (("rsi", "esi", "si", "sil"), ("rdi", "edi", "di", "dil"), ("rbp", "ebp", "bp", "bpl"), ("rsp", "esp", "sp", "spl")):
    ALIAS.update({r: (r, 64), e: (r, 32), w: (r, 16), l: (r, 8)})
for i in range(8, 16):
    ALIAS.update({"r%d" % i: ("r%d" % i, 64), "r%dd" % i: ("r%d" % i, 32), "r%dw" % i: ("r%d" % i, 16), "r%db" % i: ("r%d" % i, 8)})
SIZE = {"BYTE": 8, "WORD": 16, "DWORD": 32, "QWORD": 64}

class Abort(Exception): pass

def run(lines, size, init=None):
    """Evaluate `lines`. With init=None the buffer is an output (unknown content, writes tracked);
    with init=bytes it is a fully known input buffer. Returns (buffer, written-mask, final eax)."""
    reg = {r: None for r in R64}; reg["rcx"] = ("BUF", 0)
    mem = bytearray(size) if init is None else bytearray(init)
    touched = bytearray(size) if init is None else bytearray(b"\x01" * size)
    zf = [None]
    def rget(name):
        base, bits = ALIAS[name]; v = reg[base]
        if v is None or isinstance(v, tuple):
            if isinstance(v, tuple) and bits == 64: return v
            raise Abort("read of unknown/pointer register %s" % name)
        return v & ((1 << bits) - 1)
    def rset(name, val):
        base, bits = ALIAS[name]
        if isinstance(val, tuple): reg[base] = val; return
        old = reg[base] if isinstance(reg[base], int) else 0
        if bits == 32: reg[base] = val & 0xFFFFFFFF                     # zero-extends
        elif bits == 64: reg[base] = val & ((1 << 64) - 1)
        else:
            m = (1 << bits) - 1; reg[base] = (old & ~m) | (val & m)
    def ea(expr):
        """[base(+index*scale)(+/-disp)] for register arithmetic (lea)."""
        m = re.fullmatch(r"\[(\w+)(?:\+(\w+)\*([1248]))?(?:([+-])0x([0-9a-f]+))?\]", expr)
        if not m: raise Abort("unsupported address expression %s" % expr)
        base = reg[ALIAS[m.group(1)][0]]
        disp = (int(m.group(5), 16) * (-1 if m.group(4) == "-" else 1)) if m.group(5) else 0
        if isinstance(base, tuple):
            if m.group(2): raise Abort("scaled index on buffer pointer")
            return (base[0], base[1] + disp)
        if base is None: raise Abort("lea from unknown register: " + expr)
        idx = 0
        if m.group(2):
            iv = reg[ALIAS[m.group(2)][0]]
            if not isinstance(iv, int): raise Abort("unknown index register")
            idx = iv * int(m.group(3))
        return base + idx + disp
    def addr(op):
        m = re.fullmatch(r"(?:(BYTE|WORD|DWORD|QWORD) PTR )?\[(\w+)(?:([+-])0x([0-9a-f]+))?\]", op)
        if not m: raise Abort("unsupported memory operand %s" % op)
        base = reg[ALIAS[m.group(2)][0]]
        if not (isinstance(base, tuple) and base[0] == "BUF"): raise Abort("memory base is not the buffer: %s" % op)
        disp = int(m.group(4), 16) * (-1 if m.group(3) == "-" else 1) if m.group(4) else 0
        return base[1] + disp, SIZE.get(m.group(1))
    def val(op, bits=None):
        if op.startswith("0x") or op.isdigit(): return int(op, 0)
        if op in ALIAS: return rget(op)
        if "PTR" in op or op.startswith("["):
            a, b = addr(op); b = b or bits; n = b // 8
            if not all(touched[a:a + n]): raise Abort("read of unwritten buffer byte at 0x%X" % a)
            return int.from_bytes(mem[a:a + n], "little")
        raise Abort("operand %s" % op)
    def store(op, v):
        a, b = addr(op); n = b // 8
        if a < 0 or a + n > size: raise Abort("store outside buffer: 0x%X" % a)
        mem[a:a + n] = (v & ((1 << b) - 1)).to_bytes(n, "little"); touched[a:a + n] = b"\x01" * n
    for ins in lines:
        ins = re.sub(r"\s+#.*$", "", ins).strip()
        op, _, rest = ins.partition(" "); rest = rest.strip()
        if op == "ret": break
        if op.startswith("j") or op in ("call", "loop") or "rip" in rest: raise Abort("non-straight-line: " + ins)
        args = [a.strip() for a in re.split(r",(?![^\[]*\])", rest)]
        if op == "mov":
            d, s = args
            if ("PTR" in d or d.startswith("[")) and re.search(r"\[rsp", d):
                pass  # callee-saved register spill to the caller's home space: no effect on the buffer
            elif "PTR" in d or d.startswith("["):
                bits = SIZE[d.split()[0]]
                store(d, val(s, bits))
            elif "PTR" in s and s.split()[0] == "QWORD" and re.search(r"\[rsp|\[rax\+0x", s):
                pass  # saving callee-saved registers to the shadow area: no effect on the buffer
            else:
                rset(d, val(s) if not (s in ALIAS and isinstance(reg[ALIAS[s][0]], tuple)) else reg[ALIAS[s][0]])
        elif op == "lea":
            d, s = args
            rset(d, ea(s))
        elif op == "movzx":
            d, s = args
            bits = SIZE[s.split()[0]]; rset(d, val(s, bits))
        elif op == "imul":
            if len(args) == 3: d, a1, imm = args; rset(d, val(a1) * int(imm, 0))
            else: d, a1 = args; rset(d, val(d) * val(a1))
        elif op in ("rol", "ror", "shr", "shl"):
            d, c = args; bits = ALIAS[d][1]; v = val(d); n = int(c, 0) % bits; m = (1 << bits) - 1
            r = {"rol": ((v << n) | (v >> (bits - n))) & m, "ror": ((v >> n) | (v << (bits - n))) & m,
                 "shr": v >> n, "shl": (v << n) & m}[op]
            rset(d, r)
        elif op == "cmp":
            a1, a2 = args; zf[0] = (val(a1) == (val(a2) & ((1 << ALIAS[a1][1]) - 1) if a1 in ALIAS else val(a2)))
        elif op == "cmovne":
            d, a1 = args
            if zf[0] is None: raise Abort("cmovne without cmp")
            if not zf[0]: rset(d, val(a1))
        elif op in ("xor", "or", "and", "add", "sub"):
            d, s = args
            if op == "xor" and d == s and d in ALIAS: rset(d, 0); continue
            if "PTR" in d or d.startswith("["):
                bits = SIZE[d.split()[0]]; a, _ = addr(d); n = bits // 8
                cur = int.from_bytes(mem[a:a + n], "little") if all(touched[a:a + n]) else None
                if cur is None and op != "or": raise Abort("rmw on unwritten memory: " + ins)
                cur = cur or 0   # 'or' on untouched memory: caller's buffer content is unknown -> only exact when operand is all-ones
                v = val(s)
                if op == "or" and v != (1 << bits) - 1 and not all(touched[a:a + n]): raise Abort("partial or on unknown memory: " + ins)
                store(d, {"or": cur | v, "and": cur & v, "xor": cur ^ v, "add": cur + v, "sub": cur - v}[op])
            else:
                cur = val(d); v = val(s)
                rset(d, {"or": cur | v, "and": cur & v, "xor": cur ^ v, "add": cur + v, "sub": cur - v}[op])
        elif op == "push" or op == "pop":
            pass
        else:
            raise Abort("unsupported instruction: " + ins)
    eax = reg["rax"] & 0xFFFFFFFF if isinstance(reg["rax"], int) else None
    return bytes(mem), bytes(touched), eax

def lines_from(pe, start, skip_to=None):
    """objdump text of the routine at `start` up to its last 'ret'; with skip_to, keep only the first
    instruction and resume at `skip_to` (used to step over a null-pointer guard)."""
    asm = subprocess.run(["objdump", "-d", "-M", "intel", "--no-show-raw-insn", pe], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True).stdout
    out = []; on = False; first = True
    for l in asm.splitlines():
        m = re.match(r"\s*([0-9a-f]+):\t(.*)", l)
        if not m: continue
        a = int(m.group(1), 16)
        if a == start: on = True
        if not on: continue
        if skip_to and not first and a < skip_to: continue
        out.append(m.group(2)); first = False
        if m.group(2).strip().startswith("ret") and (not skip_to or a > skip_to): break
    return out

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("pe"); ap.add_argument("start")
    ap.add_argument("--size", default="0x6D5"); ap.add_argument("--out")
    a = ap.parse_args(); start = int(a.start, 16); size = int(a.size, 0)
    asm = subprocess.run(["objdump", "-d", "-M", "intel", "--no-show-raw-insn", a.pe], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True).stdout
    lines = []; on = False
    for l in asm.splitlines():
        m = re.match(r"\s*([0-9a-f]+):\t(.*)", l)
        if not m: continue
        if int(m.group(1), 16) == start: on = True
        if on:
            lines.append(m.group(2))
            if m.group(2).strip().startswith("ret"): break
    mem, touched, _ = run(lines, size)
    print("instructions: %d, bytes written: %d of 0x%X" % (len(lines), sum(touched), size))
    if a.out: open(a.out, "wb").write(mem); open(a.out + ".mask", "wb").write(touched)

if __name__ == "__main__":
    try: main()
    except Abort as e: sys.exit("ABORT: %s" % e)

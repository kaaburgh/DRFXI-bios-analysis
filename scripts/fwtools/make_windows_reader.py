#!/usr/bin/env python3
"""Generate scripts/win/drfxi-mem.ps1: a READ-ONLY Windows PowerShell reader that needs no Python.

It reads the UEFI variables AmdSetupRPL / AodSetupRpl with GetFirmwareEnvironmentVariableEx, saves them in
efivarfs layout (4-byte attributes + data, accepted by memory_state_report.py --amdsetup/--aodsetup) and prints
the same re-entry sheet as memory_state_report.py. With -Rom <AFU /O image> it adds the override-APCB tokens,
the CBS-sync expectation/divergence table, the resync predicate and the APOB NV state.

usage: make_windows_reader.py [OUT.ps1]   (tables from evidence/memory-117/setup-questions.json + cbs-apcb-map.json)
"""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
EV = os.path.join(HERE, "..", "..", "evidence", "memory-117")
REGVAL = {"r13b": 1, "bpl": 0xFF, "r15b": 0xF}
WIDTH = {"SetBool": 1, "Set8": 1, "Set16": 2, "Set32": 4}
DRAM_OFFS = lambda o: o in (0x44, 0x46, 0x260, 0x263) or 0x116 <= o <= 0x17F
AOD_RUNTIME = (0x197, 2, 1100, "APU VDDIO Adjust (runtime question, AodDxe 0xC5C5)")


def table_lines():
    qt = json.load(open(os.path.join(EV, "setup-questions.json")))
    cm = json.load(open(os.path.join(EV, "cbs-apcb-map.json")))
    out = []
    for tag, vs in (("C", "AmdSetupRPL"), ("A", "AodSetupRpl")):
        seen = set()
        for q in qt[vs]:
            if q["default"] is None or q["prompt"].startswith("#"): continue
            if vs == "AmdSetupRPL" and q["offset"] < 0x20: continue
            seen.add(q["offset"])
            opts = ";".join("%d=%s" % (v, n) for n, v in q["options"])
            out.append("%s|%X|%d|%d|%s|%s" % (tag, q["offset"], q["width"], q["default"], q["prompt"], opts))
        if vs == "AodSetupRpl" and AOD_RUNTIME[0] not in seen:
            out.append("A|%X|%d|%d|%s|" % AOD_RUNTIME)
    for r in cm["entries"]:
        off = r["setup_offset"]
        if off is None or r["setter"] not in WIDTH or not DRAM_OFFS(off): continue
        sk = r["skip_if"]
        skv = "-" if sk is None else str(REGVAL.get(sk, int(sk, 16) if sk.startswith("0x") else -1))
        gs = []
        for g in r["guards"]:
            p = g.split()
            gs.append("%X:%s" % (int(p[0][1:-1], 16), REGVAL[p[2]] if (len(p) == 3 and p[1] == "cmp" and p[2] in REGVAL) else "?"))
        out.append("M|%s|%d|%X|%s|%s|%s" % (r["token"][2:], WIDTH[r["setter"]], off, skv, ",".join(gs), r["prompt"] or "(unnamed)"))
    return out


CSHARP = r'''
using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
using System.Text;

public static class DrfxiMem
{
    [DllImport("kernel32.dll", SetLastError = true, CharSet = CharSet.Unicode)]
    static extern uint GetFirmwareEnvironmentVariableExW(string lpName, string lpGuid, byte[] pBuffer, uint nSize, out uint pdwAttributes);
    [DllImport("kernel32.dll")]
    static extern IntPtr GetCurrentProcess();
    [DllImport("kernel32.dll", SetLastError = true)]
    static extern bool CloseHandle(IntPtr h);
    [DllImport("advapi32.dll", SetLastError = true)]
    static extern bool OpenProcessToken(IntPtr processHandle, uint desiredAccess, out IntPtr tokenHandle);
    [DllImport("advapi32.dll", SetLastError = true, CharSet = CharSet.Unicode)]
    static extern bool LookupPrivilegeValueW(string systemName, string name, out long luid);
    [StructLayout(LayoutKind.Sequential, Pack = 1)]
    struct TokPriv1Luid { public int Count; public long Luid; public int Attr; }
    [DllImport("advapi32.dll", SetLastError = true)]
    static extern bool AdjustTokenPrivileges(IntPtr token, bool disableAll, ref TokPriv1Luid newState, int bufferLength, IntPtr previousState, IntPtr returnLength);

    // Enables SeSystemEnvironmentPrivilege for this process (required by the read API). Returns a Win32 error code, 0 = ok.
    public static int EnablePrivilege()
    {
        IntPtr tok;
        if (!OpenProcessToken(GetCurrentProcess(), 0x28, out tok)) return Marshal.GetLastWin32Error();
        try
        {
            long luid;
            if (!LookupPrivilegeValueW(null, "SeSystemEnvironmentPrivilege", out luid)) return Marshal.GetLastWin32Error();
            TokPriv1Luid tp = new TokPriv1Luid();
            tp.Count = 1; tp.Luid = luid; tp.Attr = 2;
            if (!AdjustTokenPrivileges(tok, false, ref tp, 0, IntPtr.Zero, IntPtr.Zero)) return Marshal.GetLastWin32Error();
            return Marshal.GetLastWin32Error();
        }
        finally { CloseHandle(tok); }
    }

    // READ-ONLY: GetFirmwareEnvironmentVariableExW. Returns null and the Win32 error on failure.
    public static byte[] ReadVar(string name, string guid, out uint attr, out int err)
    {
        byte[] buf = new byte[0x10000];
        uint n = GetFirmwareEnvironmentVariableExW(name, guid, buf, (uint)buf.Length, out attr);
        if (n == 0) { err = Marshal.GetLastWin32Error(); return null; }
        err = 0;
        byte[] r = new byte[n];
        Array.Copy(buf, r, (int)n);
        return r;
    }

    public static byte[] WithAttr(byte[] d, uint attr)
    {
        byte[] r = new byte[d.Length + 4];
        BitConverter.GetBytes(attr).CopyTo(r, 0);
        d.CopyTo(r, 4);
        return r;
    }

    class Q { public int Off; public int Width; public long Def; public string Prompt; public List<long> OV = new List<long>(); public List<string> ON = new List<string>(); }
    class M { public uint Token; public int Width; public int Off; public bool HasSkip; public long Skip; public List<int> GOff = new List<int>(); public List<long> GVal = new List<long>(); public bool GUnknown; public string Name; }
    static Dictionary<string, SortedDictionary<int, Q>> T = new Dictionary<string, SortedDictionary<int, Q>>();
    static List<M> Map = new List<M>();

    public static void Load(string text)
    {
        T["AmdSetupRPL"] = new SortedDictionary<int, Q>();
        T["AodSetupRpl"] = new SortedDictionary<int, Q>();
        Map.Clear();
        foreach (string raw in text.Split('\n'))
        {
            string line = raw.TrimEnd('\r');
            if (line.Length == 0) continue;
            string[] f = line.Split('|');
            if (f[0] == "C" || f[0] == "A")
            {
                Q q = new Q();
                q.Off = Convert.ToInt32(f[1], 16); q.Width = Int32.Parse(f[2]); q.Def = Int64.Parse(f[3]); q.Prompt = f[4];
                if (f.Length > 5 && f[5].Length > 0)
                    foreach (string o in f[5].Split(';'))
                    {
                        int e = o.IndexOf('=');
                        q.OV.Add(Int64.Parse(o.Substring(0, e))); q.ON.Add(o.Substring(e + 1));
                    }
                T[f[0] == "C" ? "AmdSetupRPL" : "AodSetupRpl"][q.Off] = q;
            }
            else if (f[0] == "M")
            {
                M m = new M();
                m.Token = Convert.ToUInt32(f[1], 16); m.Width = Int32.Parse(f[2]); m.Off = Convert.ToInt32(f[3], 16);
                if (f[4] != "-") { m.HasSkip = true; m.Skip = Int64.Parse(f[4]); }
                if (f[5].Length > 0)
                    foreach (string g in f[5].Split(','))
                    {
                        string[] p = g.Split(':');
                        if (p[1] == "?") m.GUnknown = true;
                        else { m.GOff.Add(Convert.ToInt32(p[0], 16)); m.GVal.Add(Int64.Parse(p[1])); }
                    }
                m.Name = f[6];
                Map.Add(m);
            }
        }
    }

    static long Get(byte[] b, int off, int width)
    {
        if (b == null || off + width > b.Length) return -1;
        long v = 0;
        for (int i = width - 1; i >= 0; i--) v = (v << 8) | b[off + i];
        return v;
    }
    static string Fmt(Q q, long v) { int i = q.OV.IndexOf(v); return i >= 0 ? q.ON[i] : v.ToString(); }
    static long Opt(Q q, string name, long dflt) { int i = q.ON.IndexOf(name); return i >= 0 ? q.OV[i] : dflt; }
    static readonly int[] GateFrom = { 0x193, 0x195, 0x197, 0x199, 0x98, 0x1A6 };
    static readonly int[] GateCtl = { 0x192, 0x192, 0x192, 0x19B, 0x97, 0x1A3 };

    // Same rules as memory_state_report.py sheet(): Ctrl/value pairs only when Manual, gated-off AOD values suppressed.
    static SortedDictionary<int, string> Sheet(byte[] buf, string vs)
    {
        SortedDictionary<int, string> res = new SortedDictionary<int, string>();
        if (buf == null) return res;
        SortedDictionary<int, Q> by = T[vs];
        Dictionary<int, bool> skip = new Dictionary<int, bool>();
        foreach (KeyValuePair<int, Q> kv in by)
        {
            int o = kv.Key; Q q = kv.Value; Q nxt;
            if (q.Prompt.EndsWith(" Ctrl") && by.TryGetValue(o + 1, out nxt) && nxt.Prompt == q.Prompt.Substring(0, q.Prompt.Length - 5))
            {
                skip[o] = true; skip[o + 1] = true;
                long manual = Opt(q, "Manual", 1), auto = Opt(q, "Auto", 0);
                long c = Get(buf, q.Off, q.Width), v = Get(buf, nxt.Off, nxt.Width);
                if (c == manual) res[o] = String.Format("0x{0:X4} {1,-40} {2} ({3} = Manual)", o, nxt.Prompt, Fmt(nxt, v), q.Prompt);
                else if (c != -1 && c != auto && c != q.Def) res[o] = String.Format("0x{0:X4} {1,-40} {2}", o, q.Prompt, Fmt(q, c));
            }
        }
        foreach (KeyValuePair<int, Q> kv in by)
        {
            int o = kv.Key; Q q = kv.Value;
            if (skip.ContainsKey(o)) continue;
            long v = Get(buf, q.Off, q.Width);
            if (v == -1 || v == q.Def) continue;
            if (vs == "AodSetupRpl")
            {
                int gi = Array.IndexOf(GateFrom, o);
                if (gi >= 0 && buf[GateCtl[gi]] == 0) continue;
            }
            res[o] = String.Format("0x{0:X4} {1,-40} {2}", o, q.Prompt, Fmt(q, v));
        }
        return res;
    }

    static string Build(uint uid)
    {
        switch (uid) { case 0x09CC: return "1.04"; case 0x5BBC: return "1.07"; case 0x272F: return "1.12"; case 0x69FF: return "1.15"; case 0x4E98: return "1.17"; default: return "unknown build"; }
    }

    static bool IsApcb(byte[] d, int o) { return o + 16 <= d.Length && d[o] == 0x41 && d[o + 1] == 0x50 && d[o + 2] == 0x43 && d[o + 3] == 0x42; }

    public static string Report(byte[] cbs, byte[] aod, byte[] rom)
    {
        StringBuilder sb = new StringBuilder();
        if (cbs != null)
        {
            uint sig = BitConverter.ToUInt32(cbs, 0), gen = BitConverter.ToUInt32(cbs, 8);
            sb.AppendLine(String.Format("AmdSetupRPL: {0} bytes, header 0x{1:X8}{2}, sync generation 0x{3:X8}", cbs.Length, sig, sig == 0xFC4053AA ? " (ok)" : " (UNEXPECTED)", gen));
        }
        else sb.AppendLine("AmdSetupRPL: not available");
        sb.AppendLine(aod != null ? String.Format("AodSetupRpl: {0} bytes", aod.Length) : "AodSetupRpl: not available");

        Dictionary<uint, long> tok = null;
        if (rom != null)
        {
            sb.AppendLine();
            if (rom.Length != 32 * 1024 * 1024) sb.AppendLine(String.Format("WARNING: ROM image is {0} bytes, expected 33554432", rom.Length));
            if (IsApcb(rom, 0x51D400)) { uint mu = BitConverter.ToUInt32(rom, 0x51D400 + 12); sb.AppendLine(String.Format("main APCB UniqueAPCBInstance=0x{0:X4} ({1})", mu, Build(mu))); }
            else sb.AppendLine("main APCB: no header at 0x51D400");
            if (IsApcb(rom, 0x522000))
            {
                tok = new Dictionary<uint, long>();
                int b = 0x522000;
                int hsz = BitConverter.ToUInt16(rom, b + 4); int size = (int)BitConverter.ToUInt32(rom, b + 8); uint uid = BitConverter.ToUInt32(rom, b + 12);
                sb.AppendLine(String.Format("override APCB @522000 UniqueAPCBInstance=0x{0:X4} size=0x{1:X}", uid, size));
                int o = hsz;
                while (o + 16 <= size && b + o + 16 <= rom.Length)
                {
                    int gid = BitConverter.ToUInt16(rom, b + o + 4), ghs = BitConverter.ToUInt16(rom, b + o + 6);
                    int gsize = (int)BitConverter.ToUInt32(rom, b + o + 12);
                    if (gsize < 16 || o + gsize > size) break;
                    int t = o + ghs;
                    while (t + 16 <= o + gsize)
                    {
                        int tg = BitConverter.ToUInt16(rom, b + t), tid = BitConverter.ToUInt16(rom, b + t + 2), tsz = BitConverter.ToUInt16(rom, b + t + 4), inst = BitConverter.ToUInt16(rom, b + t + 6);
                        int prio = rom[b + t + 11];
                        if (tsz < 16) break;
                        if (gid == 0x3000)
                        {
                            for (int k = 16; k + 8 <= tsz; k += 8)
                            {
                                uint id = BitConverter.ToUInt32(rom, b + t + k); uint val = BitConverter.ToUInt32(rom, b + t + k + 4);
                                tok[id] = val;
                                string nm = id == 0xB331378E ? "CBS sync generation id" : "";
                                foreach (M m in Map) if (m.Token == id) nm = m.Name;
                                sb.AppendLine(String.Format("   inst={0} prio=0x{1:X2} token 0x{2:X8} = 0x{3:X}  {4}", inst, prio, id, val, nm));
                            }
                        }
                        else sb.AppendLine(String.Format("   inst={0} prio=0x{1:X2} type gid=0x{2:X4} tid=0x{3:X4} size=0x{4:X} (non-token override)", inst, prio, tg, tid, tsz));
                        t += (tsz + 3) & ~3;
                    }
                    o += gsize;
                }
            }
            else sb.AppendLine("override APCB: no header at 0x522000");
            if (0x125000 + 0x28000 <= rom.Length)
            {
                bool blank = true;
                for (int i = 0x125000; i < 0x125000 + 0x28000; i++) if (rom[i] != 0xFF) { blank = false; break; }
                sb.AppendLine("APOB NV @125000: " + (blank ? "blank -> next boot trains from scratch" : "populated (saved training data present)"));
            }
            if (tok != null && cbs != null)
            {
                uint gen = BitConverter.ToUInt32(cbs, 8);
                string pred;
                if (!tok.ContainsKey(0xB331378E)) pred = "token absent -> CbsSetupDxeRPL resyncs APCB on next boot";
                else if (tok[0xB331378E] == gen) pred = "in sync (no automatic resync)";
                else if (tok[0xB331378E] == 0x56434552) pred = "'RECV' -> CBS reset to code defaults and resync";
                else pred = "MISMATCH -> CbsSetupDxeRPL resyncs APCB on next boot (memory context discarded)";
                sb.AppendLine(String.Format("resync predicate: AmdSetupRPL[0x08]=0x{0:X8} vs APCB 0xB331378E -> {1}", gen, pred));
                sb.AppendLine("CBS DRAM entries that are pushed to APCB or present in it (setup -> expected vs stored):");
                int quiet = 0, div = 0;
                foreach (M m in Map)
                {
                    long val = Get(cbs, m.Off, m.Width);
                    int ok = 1; // 1 yes, 0 no, 2 unknown
                    for (int i = 0; i < m.GOff.Count; i++) if (Get(cbs, m.GOff[i], 1) != m.GVal[i]) ok = 0;
                    if (ok == 1 && m.GUnknown) ok = 2;
                    if (m.HasSkip && val == m.Skip) ok = 0;
                    bool has = tok.ContainsKey(m.Token);
                    bool diverges = ok != 2 && (ok == 1 ? (!has || tok[m.Token] != val) : has);
                    if (ok == 0 && !has) { quiet++; continue; }
                    if (diverges) div++;
                    sb.AppendLine(String.Format("  0x{0:X8} {1,-32} setup={2,-6} pushed={3,-4} spi={4}{5}", m.Token, m.Name.Length > 32 ? m.Name.Substring(0, 32) : m.Name, val,
                        ok == 1 ? "yes" : (ok == 0 ? "no" : "?"), has ? "0x" + tok[m.Token].ToString("X") : "absent", diverges ? "   <-- DIVERGES" : ""));
                }
                sb.AppendLine(String.Format("  ({0} further DRAM entries on Auto: not pushed, absent; {1} divergence(s))", quiet, div));
            }
        }

        sb.AppendLine();
        sb.AppendLine("Re-entry sheet (stored value differs from default; Ctrl/value pairs only when Ctrl = Manual):");
        if (cbs != null && cbs.Length > 0x116 && cbs[0x116] != 1) sb.AppendLine("  NOTE: CBS 'Active Memory Timing Settings' is not Enabled -> CBS speed/timing values are NOT pushed to APCB");
        if (aod != null && aod.Length > 0x3C && aod[0x3C] != 1) sb.AppendLine("  NOTE: AOD 'Active Memory Timing Settings' is not Enabled -> AOD speed/timing values are not applied");
        string[] vss = { "AmdSetupRPL", "AodSetupRpl" };
        string[] menus = { "AMD CBS", "AMD Overclocking" };
        byte[][] bufs = { cbs, aod };
        for (int i = 0; i < 2; i++)
        {
            if (bufs[i] == null) { sb.AppendLine(String.Format("  [{0} / {1}] not available", menus[i], vss[i])); continue; }
            SortedDictionary<int, string> s = Sheet(bufs[i], vss[i]);
            sb.AppendLine(String.Format("  [{0} / {1}] {2} non-default entries", menus[i], vss[i], s.Count));
            foreach (KeyValuePair<int, string> kv in s) sb.AppendLine("    " + kv.Value);
        }
        return sb.ToString();
    }
}
'''

PS_HEAD = r'''<#
DRFXI memory-state reader for Windows - READ-ONLY.
Generated by scripts/fwtools/make_windows_reader.py from evidence/memory-117/setup-questions.json
and evidence/memory-117/cbs-apcb-map.json (DRFXI 1.15/1.17 question tables are identical).

What it does
  * reads the UEFI variables AmdSetupRPL and AodSetupRpl with GetFirmwareEnvironmentVariableEx
    (read-only API; nothing in this file writes firmware variables or flash),
  * saves them next to this script as AmdSetupRPL.var / AodSetupRpl.var (efivarfs layout, usable with
    scripts/fwtools/memory_state_report.py --amdsetup/--aodsetup),
  * prints the re-entry sheet: every CBS / AMD Overclocking setting that differs from its default,
  * with -Rom <image saved by "AFUWINx64.EXE <file> /O">: also the override-APCB tokens, the CBS-sync
    divergence table, the resync predicate and whether saved training data (APOB NV) is present.

Usage (PowerShell started with "Run as administrator"):
  powershell -ExecutionPolicy Bypass -File .\drfxi-mem.ps1
  powershell -ExecutionPolicy Bypass -File .\drfxi-mem.ps1 -Rom .\backup_115.bin
#>
param([string]$Rom = "")
$ErrorActionPreference = "Stop"
$principal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Host "Start PowerShell with 'Run as administrator' and run this script again." -ForegroundColor Yellow
    exit 1
}
'''

PS_TAIL = r'''
Add-Type -TypeDefinition $cs -Language CSharp
[DrfxiMem]::Load($tables)

$outDir = $PSScriptRoot
if (-not $outDir) { $outDir = (Get-Location).Path }

$perr = [DrfxiMem]::EnablePrivilege()
if ($perr -ne 0) { Write-Host ("Note: SeSystemEnvironmentPrivilege not enabled (Win32 error {0})" -f $perr) -ForegroundColor Yellow }

$vars = @(
    @{ Name = "AmdSetupRPL"; Guid = "{3A997502-647A-4C82-998E-52EF9486A247}"; File = "AmdSetupRPL.var" },
    @{ Name = "AodSetupRpl"; Guid = "{5ED15DC0-EDEF-4161-9151-6014C4CC630C}"; File = "AodSetupRpl.var" }
)
$data = @{}
foreach ($v in $vars) {
    [uint32]$attr = 0
    [int]$err = 0
    $b = [DrfxiMem]::ReadVar($v.Name, $v.Guid, [ref]$attr, [ref]$err)
    if ($null -eq $b) {
        Write-Host ("{0}: cannot read (Win32 error {1}; 203 = not found / not runtime-visible, 1314 = privilege missing)" -f $v.Name, $err) -ForegroundColor Yellow
        $data[$v.Name] = $null
        continue
    }
    $path = Join-Path $outDir $v.File
    [IO.File]::WriteAllBytes($path, [DrfxiMem]::WithAttr($b, $attr))
    Write-Host ("{0}: {1} bytes, attributes 0x{2:X}, saved to {3}" -f $v.Name, $b.Length, $attr, $path)
    $data[$v.Name] = $b
}

$romBytes = $null
if ($Rom -ne "") {
    $rp = (Resolve-Path -LiteralPath $Rom).Path
    $romBytes = [IO.File]::ReadAllBytes($rp)
    Write-Host ("ROM image: {0} ({1} bytes)" -f $rp, $romBytes.Length)
}

$report = [DrfxiMem]::Report($data["AmdSetupRPL"], $data["AodSetupRpl"], $romBytes)
Write-Host ""
Write-Host $report
$rpt = Join-Path $outDir "drfxi-mem-report.txt"
[IO.File]::WriteAllText($rpt, $report)
Write-Host ("Report saved to {0}" -f $rpt)
'''


def main():
    out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "..", "win", "drfxi-mem.ps1")
    lines = table_lines()
    body = PS_HEAD + "\n$cs = @'\n" + CSHARP.strip("\n") + "\n'@\n\n$tables = @'\n" + "\n".join(lines) + "\n'@\n" + PS_TAIL
    assert "\n'@" not in CSHARP and not any(l.startswith("'@") for l in lines)
    assert all(ord(c) < 128 for c in body)
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    with open(out, "w", newline="\r\n") as f:
        f.write(body)
    print("wrote %s (%d table lines)" % (out, len(lines)))


if __name__ == "__main__":
    main()

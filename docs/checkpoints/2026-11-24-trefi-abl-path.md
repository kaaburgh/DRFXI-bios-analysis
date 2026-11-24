# ABL path Override Timing → Tref → UMC::DramTiming12: Dragon Range vs Fire Range

Date: 2026-11-24

Follow-up to [`2026-11-24-trefi-static-narrowing.md`](2026-11-24-trefi-static-narrowing.md) and [`2026-11-24-trefi-firerange-msa2.md`](2026-11-24-trefi-firerange-msa2.md). Question: once APCB token `0x419FF338` is present, does the ABL actually program it into the effective tREFI register, and does Fire Range ABL differ from Dragon Range ABL here?

Method: static Thumb-2 disassembly (capstone 5.0.9) of zlib-decompressed PSP `$PS1` ABL overlays. The result is reproducible with [`../../scripts/abl_tref_path.py`](../../scripts/abl_tref_path.py). No hardware.

| ABL | Source image | Overlay (flash) | Decompressed SHA-256 |
|---|---|---|---|
| 32.3.90.20 | DRFXI 1.04 | `0x28A290` | `c4820bdff16ba4d731b939f13a9d64e8be0e184393fc82b4da11cf41c53ba586` |
| 35.23.90.20 | DRFXI 1.07 / 1.12 | `0x28B530` | `be90ebf29fdb88bb024bc73da868c154da3b51b41f47dcb4655b9c7c637c478e` |
| 4C.11.90.20 | DRFXI 1.15 / 1.17, MS-A2 DRG | `0x289940` | `f4ec135a998b81ef7547e6b303fec72dd219b786442aad85c48ee6eaf4330c1c` |
| 51.15.0.20 | MS-A2 FRG 1.02 (FireRangePI 1.0.0.0) | `0x2ACC50` | `abf037c81aea0b6ac8543ee4ad3a1f8407cbea1e78bf2286bed5c5e3c8630739` |
| 64.24.0.20 | MS-A2 FRG 1.04 (FireRangePI 1.0.0.0g) | `0x2AD530` | `214cbe9013604b961b7a68fe9d7dbbcbecb01af1d61b6c4bff1decebee1a5012` |

## The path (same structure in all five ABLs)

```text
JEDEC timing setup     TimingPtr->Tref = ns_to_MEMCLK(DramDoubleRefreshRate ? 1.95 us : 3.9 us)
        │
        ▼  (memory-init overlay, per MemPstate × channel, gated by "Memory Present")
Override Timing        if APCB word token 0x419FF338 exists: TimingPtr->Tref = token
        │              (called immediately before ↓ at the same call site)
        ▼
Program UMC Timings    UMC::DramTiming12 (0x7000204 + 0x2C = 0x7000230)[15:0] = TimingPtr->Tref
        │
        ▼
Later overlays         save DramTiming11/12, write (value & 0xC00FFFFF), restore saved value
                       → bits [15:0] (Tref) are preserved; no other writer of DramTiming12[15:0]
```

## Version comparison

| | Dragon Range 4C.11.90.20 (32.3 / 35.23 identical in shape) | Fire Range 51.15.0.20 / 64.24.0.20 |
|---|---|---|
| Override Timing routine | `0x9D8C` (32.3: `0x9E88`) | `0xB198` / `0xB23C` |
| Tref getter → token | `0x2D30` → `0x419FF338`, size 2 | `0x2DF4` → `0x419FF338`, size 2 |
| APCB token service | core table `+0xD8` | core table `+0xA8` |
| Override store | `str.w` (32-bit) at `base + Ps*0x164 + 0x218` | `strh.w` (16-bit) at `base + Ps*0x108 + 0x208` |
| TimingPtr helper | `0x55FC`: `base + Ps*0x164 + 0x1AC` | `0x5D52`: `base + Ps*0x108 + 0x1CC` |
| Tref field in TimingPtr | `+0x6C` (= `0x218 − 0x1AC`) | `+0x3C` (= `0x208 − 0x1CC`) |
| DramTiming12[15:0] write | `ldr r0,[r4,#0x6C]; bfi r1,r0,#0,#16` at `0x8D52`, no clamp (bfi truncates to 16 bits) | `ldrh r0,[r4,#0x3C]`, clamp to `0xFFFF`, `bfi` at `0x9D24` |
| DramTiming12[29:20] in same write | `[TimingPtr+0xE0] >> (10 or 20)`, clamp `0x3FF` | `[TimingPtr+0x7C] >> (10 or 20)`, clamp `0x3FF` |
| Call site Override → Program → DRAM Config | `0x4DC0` → `0x8B68` → `0xB098` | `0x53C4` → `0x9AB0` → `0xC8C0` (64.24: `0xC964`) |
| Default Tref | `0x3B8260` ps (3.9 µs) or `0x1DC130` ps (1.95 µs) if DramDoubleRefreshRate | same constants |
| Later DramTiming12 handling | `00291670` (refresh enable), `0026CFA0` / `0029EBF0` (P-state sequences): mask `0xC00FFFFF`, save/restore | `002B5550` (refresh enable), `00289C10`: mask `0xC00FFFFF`, save/restore |

The other overlay-local `bfi …, #0, #0x10` sites write different registers: DR `0x92CC` and FR `0xA45C` target `0x1001530`, and DR `0xB110` / FR `0xC938` target DramConfiguration `0x7000200`.

Other differences in Override Timing:

- Fire Range adds separate Trcdrd/Trcdwr tokens (`0xB44E0290` / `0xF8B62812`) next to the legacy combined `0xE31F1FCE`.
- All Fire Range fields are 16-bit and clamped.

These do not affect Tref.

## Resolved open questions

1. **Does a `0x419FF338` token reach the effective register on Dragon Range?** Statically yes. In ABL 4C.11.90.20, as in 32.3/35.23, the override value overwrites `TimingPtr->Tref`. The very next call writes that field to `UMC::DramTiming12[15:0]`, and no later ABL code rewrites those bits. The path is the same as on Fire Range, where the AOD producer is known to exist.
2. **Override gate:** the gate checked before both Override and Program (`0x4508` DR / `0x4A38` FR) is the per-channel "Memory Present" check. Program prints "Memory Present" right after it. It is not a separate tREFI/user-timing enable.

## Remaining limits

- These are static results. A runtime check would need an ABL debug log or a register read (e.g. ZenTimings) with the token present.
- The override value is applied unchanged to every memory P-state (MEMCLK units). Lower-clock P-states therefore get a proportionally longer real interval.
- Code outside ABL was not examined: PMU firmware, SMU/PMFW at runtime, and the OS. Memory Context Restore replays saved register state, which would contain the programmed value.
- On Dragon Range there is still no stock producer of the token (no CBS/AOD question). Any experiment that inserts it modifies APCB/boot configuration and needs its own safety and recovery analysis.

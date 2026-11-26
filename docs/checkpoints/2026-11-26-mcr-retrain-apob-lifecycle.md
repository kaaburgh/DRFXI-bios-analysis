# DRFXI 1.15: MCR, APCB update and saved APOB lifecycle

Scope: read-only static investigation of stock DRFXI 1.15, comparison to stock 1.17 and historical third-party 1.12 donor. No hardware writes, flash, protection bypass, private AFU transfer or new board setting changes. All addresses below are analysis anchors, not a procedure for writing firmware state.

## Inputs

Stock DRFXI.BIN 1.15 SHA-256 3afaba6d916b3897d1d98bd5913008b38e89b6c51b2c6963c7109793541d8d88; 1.17 SHA-256 99f3bab5ea491202bf365c23e6416f9d1e8a649ad00f90c1f3e21f1a61e35c51. UEFIExtract NE A75, IFRExtractor-RS 1.6.1, objdump (PE RVAs or TE mapped addresses). The owner supplied only local allowlisted reports. Two actual 1.15 AFUs before/after removing AC power have different full image contents but byte-identical entire 72576-byte APOB and all remaining bytes of its 0x28000-byte NV region. No independent training variation observed.

## Menu and defaults

CbsSetupDxeRPL: Advanced / AMD CBS / UMC Common Options / DDR Options / DDR Memory Features / Memory Context Restore. QuestionId 0x9B, FormId 0x701B. AmdSetupRPL GUID 3A997502-647A-4C82-998E-52EF9486A247, size 0x6D5, offset 0x263: 0 Disabled, 1 Enabled, FF Auto. Stock external defaults 1.15/1.17 identical SHA-256 e4c97468779e948fc9df86fe43a613bbc4ece4b32b0c9f85a5fc86d16fbacc51. MCR=FF. DDR Memory Features and DDR Training Options conditional on Combo CBS; separate AMITSE access metadata also affects visibility. All 282 stock 1.15 PE32 modules scanned for IFR; no separate one-time retrain question established. DDR Training Options holds other tuning options, not an explicit one-shot retrain control.

Combo CBS offset 0x20 factory FE. CbsBasePeiRPL TE VA 0x9b7a765..0x9b7a7df and CbsSetupDxeRPL RVA 0x3d4f..0x3e12 independently compute platform selector from CPUID/package and a CMOS service-mode marker, instead of relying on a persistent user-set selector. No supported menu/keyboard sequence or safe external writer for that marker established. The 1.12 community donor has saved FE and MCR FF despite AMITSE visibility edits. Therefore stored FE alone cannot determine runtime visibility, and editing Combo CBS is not a reliable unlock strategy.

## APCB synchronization and retraining request

CbsSetupDxeRPL PE SHA-256 0aafafee9e5f51d72b978a8268499c6aacbc9e3a612d22e3b4943c0021212084.
- RouteConfig RVA 0xb58, full SetVariable at 0xbfa; APCB sync call 0xc38 to 0x45c4.
- Transfer 0x45c4 reconstructs token records for priority 3 (protocol +0xc0 at 0x462d), not a one-field update. Includes saved CBS fingerprint token 0xB331378E. At 0x4eed MCR byte 0x263 is compared to FF; non-Auto value goes to Boolean token 0xFEDB01F8 (protocol +0x78); Auto skips explicit token. Writeback protocol +8 at 0x5104/0x5107.
- Startup sync 0x3c3c reads existing fingerprint token and computes a settings hash via 0x5134; MCR included at 0x5bdf. Branch at 0x3ca5 compares the *stored* CBS+8 word with APCB token, not the newly computed hash. If equal, skips transfer. If different, stores newly computed fingerprint and transfers settings. Directly editing only the MCR byte may therefore not synchronize; no direct variable editor is proposed.
- AmdApcbDxeV3 legacy getter table at 0xbd70, mapping 0x0020 -> 0xFEDB01F8 at 0xbdb8. Getter walks priority indices and masks; do not assume active board selection from a static snapshot alone.
- Both stock BL2 copies at 0x51d000/0x8e5000 reference main APCB at relative +0x400, secondary +0x5000 and third +0x8000. Main Boolean token 0xFEDB01F8=1, priority mask 0x20, instance 0, board mask FFFF, in both stock images. No other instance of this token found in other five factory/donor blocks. Thus CBS Auto and APCB default Enabled are compatible. Historical donor's saved CBS fingerprint matches the recognized APCB sync tokens. Raw fingerprint values not needed for external report.

AmdApcbDxeV3 SHA-256 7d42c7eefdb02ce232e686fa0f692200e8192b36ab98b0d2ac58b5e3db651515:
- Writeback function 0x3f10 receives retrain-request Boolean; compare shadow vs SPI checksum/size/bytes, equal path skips; on change increment UniqueApcbID and adjust checksum. Calls SPI write at 0x4101; checks saved Boolean at 0x4106. Debug string "Trigger memory re-training in the next boot" and CPUID family/model selector; RPL/Dragon Range match sets APCB-update discard flag (bit 3), older fallback discard flag (bit 1). Public protocol +8 caller at 0xa9a passes true; initial DXE path 0x4c3d passes false.
- AmdApcbSmmV3 SHA-256 9dd2f6fc7be93f9f976c7210af6c0f7beef4b5a4bf95a511783fe6d75ced8126: write path near 0x5155 followed by same retrain diagnostic and CPU-specific flag selection.
- AmdCcxZen4Pei discard path mapped VA 0x9b1dc03 sets bit 1. AmdMemRestoreDxe ReadyToBoot callback RVA 0x730 clears restore-failure bit 0 and sets boot signoff bit 2. AmdMemRestoreDxeV2 has analogous path after recovery check; AmdMemRestorePei S3 notify also signoff. These four bits are in a shared extended CMOS register. Exact ABL consumption, clear timing and safe standalone trigger are not established; no direct write procedure.
- This proves a firmware-supported invalidation request exists independently of erasing memory settings, not that an external one-shot tool is safe.

## APOB writeback

AmdPspDxeV2Rpl SHA-256 a02a604e957946d4a33f24a1ac5743e440da3e710c5121c31310e3716048e9d7. APCB protocol notify routine 0x17f4 gets legacy parameter 0x20 at 0x18e2, invokes IDS hook, logs MCR requested, tests nonzero at 0x1902, checks restore failure flag at 0x1908, calls PspWriteApobS3Entry at 0x193b if clear. Writeback routine 0xb28 gets APOB RAM pointer from HOB GUID 30b174f3-7712-4cca-bd13-d0b8a8801997, obtains type 0x63 SPI region, validates size, reads existing contents and compares RAM table against flash at 0xc22. Equal -> skip; different -> flash write helper at 0xc49. Helper result not independently checked here. Static directory gives advertised RAM 0x0A200000, NV offset 0x125000, size 0x28000.

This explains why the saved copy can stay unchanged without any flash write. Cold-boot equality supports persistent reuse but cannot distinguish it from a fresh training run whose RAM result is not persisted (gated writeback), or an identical result. LastTrainingDate word has day resolution.

## Protection setting bridge (previously unresolved)

AmdPbsSetupDxe IFR VarStore AMD_PBS_SETUP GUID A339D746-F678-49B3-9FC7-54CE0F9DF226 size 0x100, AMD Variable Protection offset 0x91, question 0x1D, default 1.
PcdPeim local token 6 descriptor 0x011015E6 (Dynamic BOOLEAN DATA), initialized byte 1 at +0x15e6, identical in 1.15 and 1.17.
PlatformCustomizePei TE size 2976, SHA-256 12a7d510ffa337a3efb9df3e62959bb29747af7c480f2536ecd401c11479be3a, byte-identical in both. The PCD PPI GUID and native interface ordering identify SetBool at +0x50 (IA32). A direct literal-token scan over 225 distinct PCD-GUID-bearing executable bodies found the matching PEI writer. At VA 0x9b7f5cf call reads PBS via helper 0x9b7f77b (GetVariable name/GUID in data, 0x100-byte buffer at caller esp+0x10); after success, 0x9b7f5d8 loads byte [esp+0xa1] = buffer+0x91, then 0x9b7f5ec pushes 6 and 0x9b7f5ee calls [eax+0x50]. Helper extends old structure versions to size marker 0x96/defaults where applicable. AmdVariableProtection at RVA 0x119e consumes native PCD GetBool(6). This closes the direct intended PBS->PEI PCD->DXE policy gate chain. Current board runtime value/visibility not tested; do not disable protection or use HII gate-opening probe as a prerequisite for this read-only work. Donor PBS structure has older size/version marker 0x92; byte 0x91 cannot be interpreted without version check.

EDK II interface references: https://github.com/tianocore/edk2/blob/master/MdePkg/Include/Ppi/Pcd.h and https://github.com/tianocore/edk2/blob/master/MdePkg/Include/Protocol/Pcd.h .

## Version comparison

1.15 to 1.17 extracted CbsSetupDxeRPL, AmdApcbDxeV3, AmdApcbSmmV3, AmdPspDxeV2Rpl, AmdMemRestoreDxeV2 have respectively 5/11/11/12/3 changed bytes, all increments of 3 in PCD token immediate operands. MemRestoreDxe, AmdVariableProtection, CbsBasePeiRPL, CbsBaseDxeRPL and PlatformCustomizePei identical. Together with identical CBS defaults and first-16-MiB APCB payloads, no substantive MCR logic change identified. No runtime migration, dispatch or actual regression causal proof.

## Next experiment and privacy

A separate local read-only Python tool inspect_bd790i_mcr.py was prepared for two existing 32 MiB AFU images: validate known BL2 layout/checksum, APCB v3 checksum and TOKN records, exact CBS NVAR name/GUID/size/version and observed forward data chains; compare candidate saved settings and token priority/board/instance metadata; export fingerprint match and bank equality only. It refuses unsupported/ambiguous target records and existing output files. Verified on factory 1.15/1.17, historical donor and synthetic corruption/duplicate/linked-record and privacy tests. Script delivered separately, not part of this checkpoint. Original owner AFUs not accessed. No actual active precedence or runtime MCR state claimed. The PBS byte is deliberately not included in this export. The next useful step is this local report from already existing AFUs; no further boot, changed tuning, Secure Boot or protection modifications required. 


## Owner's two-AFU MCR report: observed configuration and negative controls

The owner ran the read-only MCR inspector locally on the same two 1.15 captures. Both parsed observations are equal. One recognized CBS candidate is in an NVAR file marked for update; the other file is marked deleted. This is not proof of live selection. CBS MCR is Auto; Combo CBS is neither FE nor FF. Both main APCB blocks contain Enabled at instance 0, priority mask 0x20, board mask FFFF, and no other MCR token was found. All four secondary blocks carry the saved-fingerprint token at instance 1, priority mask 4, board mask FFFF; all four match the CBS stored fingerprint. This is a comparison of stored values, not a recomputation. All six declared APCB blobs and the selected CBS payload are byte-identical between captures. The previously established full APOB equality is unchanged. These observations strongly support enabled MCR policy and retention across AC loss; do not infer actual ABL restore branch from them.

The owner reports APCB mirror equality [true,false,true] in both captures. Independent reinspection of the historical community donor reproduces exactly that equality pattern, whereas stock 1.15/1.17 have [true,true,true]. In the donor, the first directory's second block (type 0x20000060) is 840 bytes, its counterpart 296 bytes; the entire difference after the 128-byte header is an extra 544-byte GNBG group (group header 16, type header 16, type 0x1002 instance 0 priority mask 0x10 board mask FFFF, payload 512). The TOKN group is byte-identical between the pair. The header differs only at byte offsets 8,9,12,16 (size, unique ID, checksum). Purpose of the extra type not established; the owner's report does not reveal whether its difference is the same group. No evidence of corrupt MCR or CBS token state. Do not infer or attempt mirror repair.

Static CbsSetupDxeRPL platform selector table at RVA 0x7130 contains six-byte match keys followed by codes 1,2,3,10,FE; RPL-specific branch can add 0x40 to a matched code, and the service-mode branch uses FF. Thus a saved selector other than FE/FF is expected for normal platform identification and not by itself an anomaly. The exact owner value is intentionally not exported. IFR DDR Memory Features reference remains suppressed when QuestionId 9 != FF. No safe supported one-shot retrain interface established.

No private report, actual firmware bytes, identifiers, fingerprints, date or unknown values committed. No hardware changes performed. A remaining high-value read-only comparison would be current live APOB vs persisted APOB (where the OS permits access), or a verified full retrain followed by another dump only if an ordinary supported UI path is available. Neither the existing captures nor the factory images alone can establish actual ABL execution or generate independent training variation.

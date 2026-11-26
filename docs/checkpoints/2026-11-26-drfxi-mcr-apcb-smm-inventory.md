# DRFXI 1.15: typed APCB getter, SMM transport and passive inventory

2026-11-26. Follow-up to [getter precedence](2026-11-26-drfxi-mcr-apcb-getter-precedence.md). Offline only; no physical-board operations, protection changes, writes, or real SMI experiments.

## Reviewed images

Exact stock 1.15 ROM SHA256 3afaba6d916b3897d1d98bd5913008b38e89b6c51b2c6963c7109793541d8d88. Extracted DXE FV and PE bodies:
- AmdApcbDxeV3 FFS 4D3708A0-6D9B-47D3-AD87-E80C781BC0A7, PE 56576, SHA256 7d42c7eefdb02ce232e686fa0f692200e8192b36ab98b0d2ac58b5e3db651515.
- AmdApcbSmmV3 FFS B1BAC051-D5C2-4AC1-AC7D-9D2F518A1E7B, PE 55296, SHA256 9dd2f6fc7be93f9f976c7210af6c0f7beef4b5a4bf95a511783fe6d75ced8126. SMM .text RVA1000/raw400; .data RVA b000/raw9600; use mapped RVAs below, not raw offsets.
- PiSmmIpl FFS 2FA2A6DA-11D5-4DC3-999A-749648B03C56, PE SHA256 be8ecdeb6cf69d2155c1fd62257706b1845cc3b3a1bf59c1c43d3917354200ce.
- PiSmmCore FFS E94F54CD-81EB-47ED-AEC3-856F5DC157A9, PE SHA256 911024661dc4e7cf51d4022fc1f6afc11fc9f46b65d55aab48db8a2f125bb441.

## DXE typed getter ABI

Protocol GUID 7189E04E-6284-4953-A543-A31F89A1A7BF at DXE RVA A050; registered by InstallMultipleProtocolInterfaces at 886 on a new handle, interface table A160 revision 3 (uint64), 27 relocated method pointers. GetTokenBool table+70 -> DEC. Recovered signature EFI_STATUS EFIAPI GetTokenBool(This, UINT8 *Priority, UINT32 Token, UINT8 *Value). Both output pointers must be valid; no NULL test in SMM success path. Local getter EA1 searches priority 1..6. CFA8 controls dispatch: callback 22DC writes 1 at 22F8, registered for DXE SMM Ready-to-Lock (60FF8964-E906-41D0-AFED-F241E974E08E) at 91A/964. The PI header describes this as a transition at the end of DXE before third-party extensible code, not a proof of actual platform callback execution: https://github.com/tianocore/edk2/blob/master/MdePkg/Include/Protocol/DxeSmmReadyToLock.h .

## SMM path and validation

DXE uses standard EFI_SMM_COMMUNICATION_PROTOCOL. SMM handler registered at 33AD; handler 2D3C bounds input and invokes external buffer validator at 2D97, copies to internal scratch. Boolean dispatch leads to 1F28. If both E069 and E068 are 1, calls permission lookup 1AC4 with read permission; entries 5 bytes (DWORD token, byte permission bits: read1/write2), missing read permission returns EFI_ACCESS_DENIED. Actual runtime permission flags/list are unknown; no attempt to circumvent, inspect SMRAM, or send raw SMM requests. Both stock raw flags are zero; not a runtime observation. SMM 4CF4 uses same priority sequence as DXE, 5778->649C searches Boolean type 3000, board mask E13C. DXE and SMM shadow providers 3DC4/4E20 may refresh existing shadow from SPI when UID differs. They clear RAM buffer and read header, use declared size on mismatch; this path does not visibly enforce a capacity limit at caller, and not all alternate transport paths were audited. No flash program/erase found on reviewed Dragon Range memory-mapped read paths. Do not infer zero side effects or safety on hardware.

Transport defect: DXE 9A8 obtains reusable AMD heap buffer (via protocol at A0C0, method +20) and initializes header/command, but not inner response status/priority/value. DXE typed wrapper calls Communicate at E78; failure logs at 239C and falls through to the response status at E8A. Diagnostic logging can itself be conditional on flag D074. Therefore a failed transport can be mistaken for successful read if the buffer contains zero or a retained previous response. Actual heap provider reuse/clearing behavior not fully recovered. The mock demonstrated both scenarios, not actual stale live hardware data. Do not use range check or repeated matching reads as proof of freshness.

PiSmmIpl 1384 uses supplied CommSize; direct branch 145F subtracts 0x18 header; external path passes address and total size to SMM core. PiSmmCore 20CF subtracts 0x18 and dispatches at 2107. This explains why the AMD wrapper's total size in MessageLength does not by itself prove a runtime error; no actual SMI executed.

## Native original-code tests

Private Linux x86-64 executable mappings of reviewed DXE and SMM images. Original typed DXE wrapper and SMM handler/wrapper/type search executed. Replaced only transport, heap provider, buffer validation, logging, shadow provider and scratch setup by local mocks; no original entrypoints, real SMM, hardware or firmware services. Repeated 8 cases for each factory BL2 bank (16 total):
- unrestricted and allowed: success, priority6, value1, 6 shadow visits;
- permission denied: EFI_ACCESS_DENIED, untouched CC output, zero shadows;
- invalid buffer / transport error with zero response: false EFI_SUCCESS, p0/value0, no shadow reads;
- successful read followed by transport failure retaining response: false EFI_SUCCESS, p6/value1, no shadow reads, debug error observed;
- absent 60/1 descriptor: factory result unchanged p6/value1.

### Correction to earlier shadow assumption

Both directory resolver implementations DXE 8B30 (fallback 8CE9..8D1F) and 89C0 (8A7D..8AB2) decode type low byte, binary instance bits20..23, socket bits24..26. Both factory BL2 directories contain 00000068 (type68 instance0), 20000060 (type60 instance0), 00800068 (type68 instance8), all socket0. No type60 instance1 in these two directories. Earlier mock routing 60/1 -> third block was only a synthetic mapping and must not be interpreted as actual. New null-descriptor case yields identical factory result. Actual active directory selection and descriptor state remain unproven; don't infer absence of instance1 from only the two static candidates.

## Passive EFI diagnostic

apcb_inventory.c implements a deliberately passive alternative. Enumerates handles by APCB GUID; requires unique provider. Enumerates LoadedImage handles, matches interface address at image base+A160, bounds image size DD00..E000, CRC32 720886D8 of immutable code RVA280 length9D62 (no text relocations), GUID, revision and all 27 relocated method pointers. Only after exact match reads flags CFA8 (SMM mode) and D074 (diagnostic flag). No addresses or private raw settings printed. Reads gate and CBS using GetVariable before/after; verifies gate1/attrs26 and full CBS equality, CBS expected attrs7, length6D5 and header. No APCB methods, SMM communication, HII or writes called by application; firmware-owned Boot Services/GetVariable behavior not under app control. CRC diagnostic, not cryptographic attestation. Requires actual stock driver, not arbitrary versions.

Native mock tests 12 cases: positive SMM/local, no provider, ambiguous provider, shifted interface, code CRC mismatch, truncated image, ambiguous image, invalid dispatch flag, changed CBS, changed table, invalid debug flag. All passed, only two expected successes. Actual QEMU 10.0.13/OVMF 2025.02-8+deb13u1: production binary clean OVMF negative PASS (not found, no effective query); VM-only positive fixture registers synthetic LoadedImage and APCB table from reviewed PE bytes without starting original driver, real Boot Services enumeration and match succeeded, both synthetic protocols removed successfully. No physical testing.

Research bundle drfxi-apcb-inventory-research.zip SHA256 8e7506410c887975a29cbec08456a2fa7a9181ae64e1be61f1ed53a06b0b83ae (12428 bytes), delivered in conversation, contains sources, tests, sanitized logs and passive production EFI (SHA256 c597be6a5b7864d0e552d3254ab89d21d66642e14c9d73fdde608f933f7304c1). No AMD PE, raw dump, generated VM fixture or stock APCB bytes included. Original source Git blob hashes:
- apcb_inventory.c f72f88f916ca15c4fe0f00e02901477cee808573
- inventory_test.c 318b3a4eac84966da7d588493814bd325dc30188
- smm_getter_test.c 6e35f33c912147a5a1a028e02f44f39e273a9745
- inventory_ovmf_fixture.c 64e630fc808ca4bbb6fdbef335a582e638da6859

Decision: do NOT deliver a live getter app, call SMM, open browser, or write settings to resolve the defect. Passive inventory is an optional next hardware observation; it can establish which implementation/dispatch mode is active, not actual effective MCR. To prove policy, prefer independent read-only evidence from owner AFU or a reviewed existing platform diagnostic with status provenance. Further confirmation requires physical runtime evidence or a better documented read interface; factory static and mocked code tests cannot prove actual hardware SMM permissions, transport reliability, or memory restore behavior.

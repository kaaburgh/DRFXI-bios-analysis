# DRFXI 1.15: APCB Boolean MCR getter precedence

2026-11-26. Bounded offline follow-up to MCR direct SendForm/RouteConfig OVMF checkpoint. No board actions.

## Exact stock evidence
Re-extracted official 1.15 from acquisition ZIP, SHA256 3afaba6d916b3897d1d98bd5913008b38e89b6c51b2c6963c7109793541d8d88. Outer LZMA DXE FV as in existing extractor. UEFIExtract A75 identifies AmdApcbDxeV3 FFS 4D3708A0-6D9B-47D3-AD87-E80C781BC0A7. Extracted PE32 from section type 0x10, 56576 bytes, SHA256 7d42c7eefdb02ce232e686fa0f692200e8192b36ab98b0d2ac58b5e3db651515. RVAs equal file offsets for reviewed code/data sections. GNU objdump -d -M intel.

- Legacy parameter 0x20 at RVA BDB8 maps to Boolean token FEDB01F8 (table BD70, 39 eight-byte records). Legacy search 5708, local wrapper call B74 converts false to EFI_NOT_FOUND. Typed getter wrapper DEC, local path EA1..ED7, also iterates 1..6, can report successful priority via 3D84. Both wrappers have a separate communication path controlled by global CFA8, not executed/audited here.
- 3C88 loads current priority, BIOS directory entry and binary instance into A305/A306/A304 from table A260. Exact bytes: 01 68 00 02 60 00 03 60 00 04 60 01 05 60 00 06 68 00. Priority mapping at A2F8 is identity for 1..6. Getter starts at 1 and stops at first successful token search; mask = 1 << (priority-1) at 4CAE..4CC3.
- Boolean getter 4C90 calls shadow provider 3DC4 then coreApcbGetBool 5F7C. At 600B..602B uses type 3000, type instance 0, current board mask global D04C, current priority mask. Binary instance and type instance are different fields. coreApcbGetType 7124 walks groups/type headers; tests exact type and type instance at 7179..7184, priority intersection at 7186, board intersection OR stored board mask FFFF at 718C..719A. It takes first matching type, then 604D..6072 scans its eight-byte tokens for exact ID and returns byte at +4. A missing token causes next priority, not continued scan through other same-level type records in this function.
- Board mask initialization includes external protocol call 43B2..43C2 and debug label B6C8. Actual live mask not known. FFFF matches even current mask zero.
- 3DC4 is not a purely passive buffer getter: selects shadow descriptor by directory-entry/binary-instance pair; calls descriptor getter, checks APCB signature; reads 0x80-byte header via 7B78 at 3EE3, compares unique ID at +0xC, on mismatch reads declared size into the shadow at 3F00. 7B78 clears destination then calls SPI-read implementation 9E94. This changes RAM on mismatch, not evidence of SPI writes. Transport, mutex, and firmware phase branches not yet exhaustively audited. Do not recommend live getter yet.

## Stock candidates
Both BL2 directories at 51D000 and 8E5000, 18 entries of 24 bytes starting +10. Entry types 00000068 at relative 400 (capacity 4000), 20000060 at 5000 (capacity 3000), 00800068 at 8000 (capacity 3000), all relative flags bit63 set. First APCB declared size 10528, other two 296 each. Walked groups from header+80, type records and eight-byte Boolean tokens. Each main block has one MCR token, mask20, boardFFFF, type instance0, value1. Neither secondary candidate contains MCR. This does NOT establish which actual shadow address is selected for every encoded directory instance; the 60/1 descriptor specifically needs further tracing. Main stock MCR is level6; CBS explicit setter uses level3 (mask04), which precedes it.

## Native execution experiment
Executed reviewed original machine code at 5708, 3C88, 4C90, 5F7C, 7124 in a private Linux x86-64 process mapping of exact PE. Entry point not invoked, no original DXE initialization. Replaced private copy's 24F4 logging with ret and 3DC4 shadow-provider function with a jump to a mock returning local buffers according to A306/A304. Stock mock routing: 68/0 -> main candidate, 60/0 -> first secondary candidate, 60/1 -> third candidate. Last association is synthetic, NOT recovered actual platform mapping; the third raw entry is 00800068, not evidence of 60/1. This choice cannot change the stock MCR result because neither secondary contains MCR. Synthetic 168-byte APCB blocks test precedence with no checksum or real storage claim. Board mask explicitly supplied to D04C. Native ABI test, not QEMU/OVMF or hardware, no SPI or real SMM.

Repeated same seven cases against both stock candidate sets:
- stock, board mask1: success width1 value01 visits123456
- stock, board mask0: success width1 value01 visits123456
- synthetic priority3 Disabled, priority4 Enabled, priority6 Enabled: success value00 visits123
- priority3 board mask2 and current mask1: success value01 visits1234
- priority3 type instance1, instance0 required: success value01 visits1234
- priority3 and 4 type instance1: success value01 visits123456
- no eligible MCR token: false, untouched output CC, visits123456; width still1, do not interpret width alone as success.

## Consequence
The owner AFU report in previous checkpoint (not raw dump available here) found saved CBS Auto and only main APCB MCR Enabled, no other MCR token. Combined with proven DXE precedence this is strong evidence for Enabled in the observed persisted candidates, not proof of live effective policy or actual ABL restore execution. Do not use this to infer successful retraining. Next bounded step: recover descriptor initialization and protocol/SMM getter ABI, determine whether a live call is safe and returns selected priority; do not invoke real board getter or direct SendForm without reviewing side effects and obtaining any required approval. No actual BIOS or private dumps committed.

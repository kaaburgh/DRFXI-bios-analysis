# Passive DRFXI 1.15 HII probe

See [checkpoint](../../docs/checkpoints/2026-11-26-drfxi-115-mcr-hii-runtime.md). No browser launch, configuration writes, gate-opening call, package modification or raw variable export. Only use on known DRFXI 1.15; not tested in OVMF or on physical hardware. ExportPackageLists may invoke firmware-owned notifications, so monitor gate and complete CBS equality before/after. If gate absent or unexpected baseline, no export; stop. If export changes observed state, stop and reboot; do not use the old protection probe or open the browser.

Build on x64 Linux with clang/lld-link 17, cc, Python 3: ./build.sh /absolute/path/to/extracted/CbsSetupDxeRPL/PE32/body.bin . Omit PE path to build without fixture tests. Exact stock PE SHA-256 0aafafee9e5f51d72b978a8268499c6aacbc9e3a612d22e3b4943c0021212084. Local build twice produced EFI SHA-256 aaf1a1002924407e957bb3fa912af74ff5b13f82c3ae21e4d2b9c0d24765c8b2. Native test harness is not firmware emulation.

Copy only HiiProbe.efi to FAT32 USB. Fresh Shell session, before UiApp or prepare-setup.nsh; run HiiProbe.efi, photograph output. Expected gate 1 attrs26, one owner/ConfigAccess, forms mask F, refs7, MCR1, forms length 0x75C1 CRC7897C39A, gate expected and full CBS unchanged. Any mismatch is diagnostic, not authorization to bypass it. Reboot after collecting evidence. No direct SendForm tool yet.

# DRFXI 1.15 HiiProbe: QEMU / OVMF validation

2026-11-26, follow-up to [runtime checkpoint](2026-11-26-drfxi-115-mcr-hii-runtime.md). The previously missing QEMU/OVMF toolchain is now available as a project source. No physical board changes.

## Toolchain

Owner built portable Debian 13 amd64 QEMU 10.0.13 on MacBook using collect-qemu-linux-amd64.sh. Archive qemu-linux-amd64-20261126T205128Z.tar.gz SHA256 037b64ab4e77e5779dc5d6cfdafa4a09babab0a39cfd10bb14d3d6e3eddc9d9c, size 35968426 bytes. Source added to project, also conversation attachment. Verified archive hash and all 191 SHA256SUMS entries. Executed bundled smoke-test.sh in current Linux container: PASS QEMU TCG, OVMF pflash, qemu-img initialization. OVMF is Debian EDK II 2025.02-8+deb13u1. Use bundle wrappers, no KVM, separate writable VARS file for every run. QEMU not committed.

## Negative case: actual production EFI

The original HiiProbe.efi (SHA256 aaf1a1002924407e957bb3fa912af74ff5b13f82c3ae21e4d2b9c0d24765c8b2) copied as EFI/BOOT/BOOTX64.EFI onto a disposable FAT virtual disk; booted OVMF with fresh VARS. Serial output:

    DRFXI HII PROBE v1 (no browser, no direct writes)
    HII database status: 0x0000000000000000
    FormBrowser2 status: 0x0000000000000000
    Baseline (passive GetVariable)
      protection gate GetVariable status: 0x800000000000000E
      CBS GetVariable status: 0x800000000000000E
      CBS size: 0x00000000000006D5
    Unexpected baseline; no HII exports attempted. Stop.
    BdsDxe: failed to start Boot0001 ...: Not Found

EFI_NOT_FOUND expected, no export attempted; returned to firmware, which booted internal shell. This validates actual PE execution, ABI, console, LocateProtocol, GetVariable, early refusal on OVMF. Not hardware verification.

## Positive case: actual OVMF HII database and stock package

Independently extracted official 1.15 from acquisition archive with libarchive, outer LZMA section, CBS PE32. Verified image SHA256 3afaba6d916b3897d1d98bd5913008b38e89b6c51b2c6963c7109793541d8d88, PE SHA256 0aafafee9e5f51d72b978a8268499c6aacbc9e3a612d22e3b4943c0021212084, complete 137097-byte package SHA256 58d1d2dfaf5920edcf0e77225b62307b80edc28c739a77a398cda6300489f92a.

Compiled VM-only ovmf_fixture.c under tools/drfxi-hii-probe/ (same original hii_probe.c included, entry renamed). Installs exact stock vendor device path and stub ConfigAccess on a new handle, registers original package using real OVMF NewPackageList. Calls probe with real BootServices and console, but local synthetic RuntimeServices GetVariable (not global runtime table, not real protected variables). Synthetic CBS header/size, Combo 43, MCR FF, gate 1 attrs26. No firmware SetVariable call. Stub ConfigAccess never invoked by probe. Removes fixture package and protocols after test. This is NOT an EFI binary for real hardware.

Serial observation:
    Fixture install: 0
    Fixture NewPackageList: 0
    HII database status: 0
    FormBrowser2 status: 0
    List size status: 0x8000000000000005
    All package-list handles: D
    CBS owner path match on handle index: C
    owner ConfigAccess status: 0
    exported list GUID match: 1
    valid package list: 1
    target formsets: 1
    forms mask: F
    refs mask: 7
    MCR question count: 1
    forms package bytes: 75C1
    forms CRC32: 7897C39A
    exact stock CRC+length: 1
    CBS owner path matches: 1
    ConfigAccess present: 1
    CBS formsets total: 1
    Stock matches in valid lists: 1
    Export/parse failures: 0
    Protection gate still in expected state: 1 (synthetic)
    CBS full payload unchanged: 1 (synthetic)
    Fixture probe result: 0
    Fixture remove: 0
    Fixture uninstall: 0
    OVMF FIXTURE PASS

The VM proceeded to normal OVMF UI. Both runs terminated by host timeout after the app returned, not a guest failure. This demonstrates the actual UEFI ABI and HII enumeration/export logic for the original stock package, including unchanged Forms bytes after registration. It does NOT establish actual AMD gate or CBS behavior, nor that physical BIOS publishes the package, nor SendForm navigation or writeback. Direct opening of 701B remains a separate next VM experiment. Hardware instructions unchanged: run only original passive HiiProbe on fresh Shell, not the synthetic fixture.

## Reproduction

Use extracted exact stock CBS PE32 (hash above). From tools/drfxi-hii-probe, copy hii_probe.c and ovmf_fixture.c to temporary working directory, then generate stock.inc from PE:

```python
import hashlib
from pathlib import Path
p = Path("CbsSetupDxeRPL.pe").read_bytes()
assert hashlib.sha256(p).hexdigest() == "0aafafee9e5f51d72b978a8268499c6aacbc9e3a612d22e3b4943c0021212084"
b = p[0x8760:0x8760+0x21789]
assert hashlib.sha256(b).hexdigest() == "58d1d2dfaf5920edcf0e77225b62307b80edc28c739a77a398cda6300489f92a"
Path("stock.inc").write_text(",\n".join(",".join(str(x) for x in b[i:i+32]) for i in range(0,len(b),32)))
```

```sh
clang -target x86_64-pc-windows-msvc -ffreestanding -fno-builtin -fno-stack-protector -fshort-wchar -mno-red-zone -Oz -Wall -Wextra -Werror -c ovmf_fixture.c -o fixture.obj
lld-link /subsystem:efi_application /entry:efi_main /nodefaultlib /machine:x64 /dynamicbase /timestamp:0 /out:fixture.efi fixture.obj
# q is absolute path to unpacked qemu-linux-amd64; w is fresh absolute work dir
mkdir -p "$w/esp/EFI/BOOT"
cp fixture.efi "$w/esp/EFI/BOOT/BOOTX64.EFI"
cp "$q/share/OVMF/OVMF_VARS_4M.fd" "$w/vars.fd"
timeout 20s "$q/bin/qemu-system-x86_64" -machine q35,accel=tcg -m 256 -smp 1 -display none -serial stdio -monitor none -nic none -drive if=pflash,format=raw,readonly=on,file="$q/share/OVMF/OVMF_CODE_4M.fd" -drive if=pflash,format=raw,file="$w/vars.fd" -drive format=raw,file=fat:rw:"$w/esp" -no-reboot >"$w/serial.log" 2>&1
# expected timeout after guest returns; inspect serial log for OVMF FIXTURE PASS
```

Use disposable FAT:rw folder (fat:ro attempt failed at QEMU startup with Block node is read-only; no EFI code ran then). Do not commit stock.inc, fixture EFI, proprietary firmware or raw owner dumps.

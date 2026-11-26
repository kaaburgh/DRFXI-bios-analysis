# DRFXI 1.15 APCB inventory

See [research checkpoint](../../docs/checkpoints/2026-11-26-drfxi-mcr-apcb-smm-inventory.md) for the reviewed implementation, results and limitations. No physical-board test in this pass. The diagnostic does not call APCB methods or request SMI, open the browser, or write NVRAM.

## Verified input extraction and Linux native tests

Only the exact factory 1.15 ROM is accepted. Never run test fixtures on hardware. The extracted modules are not committed.

```sh
python3 extract_apcb_stock.py /path/to/stock/DRFXI.BIN verified-inputs
cc -O2 -Wall -Wextra -Wno-misleading-indentation inventory_test.c -o inventory_test
./inventory_test verified-inputs/AmdApcbDxeV3.pe
cc -O2 -Wall -Wextra smm_getter_test.c -o smm_getter_test
for bank in 51d000 8e5000; do
    ./smm_getter_test verified-inputs/AmdApcbDxeV3.pe verified-inputs/AmdApcbSmmV3.pe \
        "verified-inputs/block-400-$bank.bin" "verified-inputs/block-5000-$bank.bin" "verified-inputs/block-8000-$bank.bin"
done
```

The extractor produced exactly the eight previously tested input files; single-byte modified and truncated factory images were rejected. The native harness only checks the PE sizes itself, so use verified inputs, not arbitrary binaries.

## Passive EFI build

```sh
clang --target=x86_64-pc-win32-coff -ffreestanding -fno-stack-protector -fshort-wchar -mno-red-zone -Wall -Wextra -Werror -O2 -c apcb_inventory.c -o apcb_inventory.obj
lld-link /subsystem:efi_application /entry:efi_main /nodefaultlib /out:apcb_inventory.efi apcb_inventory.obj
```

The VM-only positive fixture needs apcb_stock.inc generated locally from the verified DXE PE as comma-separated byte literals. Compile inventory_ovmf_fixture.c with the same flags and run only on a disposable QEMU/OVMF VM. The actual production EFI on ordinary OVMF should report NOT_FOUND; the synthetic fixture should report INVENTORY POSITIVE VM PASS. The positive fixture uses real UEFI services but synthetic loaded-image/APCB protocol, never executes AMD firmware. Do not confuse it with the passive production app.

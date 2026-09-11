#!/bin/sh
set -eu
CC=${CC:-clang}
LINK=${LINK:-lld-link}
"$CC" --target=x86_64-pc-win32-coff -ffreestanding -fshort-wchar -mno-red-zone -fno-stack-protector -fno-builtin -Wall -Wextra -Werror -O2 -c AmdVariableProtectionProbe.c -o AmdVariableProtectionProbe.obj
"$LINK" /subsystem:efi_application /entry:efi_main /machine:x64 /nodefaultlib /dynamicbase /nxcompat /timestamp:0 /out:AmdVariableProtectionProbe.efi AmdVariableProtectionProbe.obj
sha256sum AmdVariableProtectionProbe.efi

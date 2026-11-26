#!/bin/sh
set -eu
cd "$(dirname "$0")"
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT HUP INT TERM
clang -target x86_64-pc-windows-msvc -ffreestanding -fno-builtin -fno-stack-protector -fshort-wchar -mno-red-zone -Oz -Wall -Wextra -Werror -c hii_probe.c -o "$tmp/probe.obj"
lld-link /subsystem:efi_application /entry:efi_main /nodefaultlib /machine:x64 /dynamicbase /timestamp:0 /out:HiiProbe.efi "$tmp/probe.obj"
cc -DHOST_TEST -Wall -Wextra -Wno-misleading-indentation -O2 hii_probe.c -o "$tmp/host_probe"
if [ "$#" -eq 1 ]; then
  python3 test_probe.py "$tmp/host_probe" "$1"
  python3 - "$1" "$tmp/stock.list" <<'PY2'
from pathlib import Path
import sys
b=Path(sys.argv[1]).read_bytes()
Path(sys.argv[2]).write_bytes(b[0x8760:0x8760+0x21789])
PY2
  cc -Wall -Wextra -Wno-misleading-indentation -O2 mock_probe.c -o "$tmp/mock_probe"
  "$tmp/mock_probe" "$tmp/stock.list"
fi

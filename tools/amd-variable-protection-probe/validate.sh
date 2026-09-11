#!/bin/sh
set -eu
BIN=${1:-AmdVariableProtectionProbe.efi}
SRC=${2:-AmdVariableProtectionProbe.c}
EXPECTED_SHA256=${EXPECTED_SHA256:-8991966a546960265287ab1e4804658d4e879680ce47c50f29350d0ab4016431}

actual=$(sha256sum "$BIN" | awk '{print $1}')
printf 'SHA-256: %s\n' "$actual"
[ "$actual" = "$EXPECTED_SHA256" ] || {
  echo "ERROR: SHA-256 mismatch (expected $EXPECTED_SHA256)" >&2
  exit 1
}

file "$BIN" | grep -q 'PE32+ executable for EFI (application), x86-64'
objdump -x "$BIN" > "$BIN.objdump-x.txt"
objdump -d "$BIN" > "$BIN.disasm.txt"

grep -q 'Magic[[:space:]]*020b' "$BIN.objdump-x.txt"
grep -q 'architecture: i386:x86-64' "$BIN.objdump-x.txt"
grep -q 'Subsystem[[:space:]]*0000000a[[:space:]]*(EFI application)' "$BIN.objdump-x.txt"
grep -q 'Base Relocation Directory \[.reloc\]' "$BIN.objdump-x.txt"
grep 'Base Relocation Directory' "$BIN.objdump-x.txt" | grep -vq '0000000000000000 00000000'
grep 'Import Directory' "$BIN.objdump-x.txt" | grep -q '0000000000000000 00000000'

if grep -En -- '->(SetVariable|ResetSystem|RouteConfig)[[:space:]]*\(' "$SRC"; then
  echo 'ERROR: forbidden service invocation found in source' >&2
  exit 1
fi

# RuntimeServices SetVariable=0x58, ResetSystem=0x68; HII RouteConfig=0x10.
if grep -E 'call.*\*0x(10|58|68)\(' "$BIN.disasm.txt"; then
  echo 'ERROR: suspicious forbidden service-table call offset found in binary' >&2
  exit 1
fi

if strings -a "$BIN" | grep -E 'SetVariable|ResetSystem|RouteConfig'; then
  echo 'ERROR: forbidden API name present in binary strings' >&2
  exit 1
fi

printf '%s\n' 'validation: PASS'

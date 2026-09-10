; Focused objdump excerpt / annotations for the new DRFXI 1.17 OemDxe logic.
; Source firmware: DRFXI 1.17
; DRFXI.BIN SHA-256:
;   99f3bab5ea491202bf365c23e6416f9d1e8a649ad00f90c1f3e21f1a61e35c51
;
; This is intentionally a narrow excerpt rather than the complete proprietary
; module disassembly. Addresses are module-relative objdump addresses.

; Construct GUID 3A997502-647A-4C82-998E-52EF9486A247 (`AmdSetupRPL`).
987:  c7 44 24 30 02 75 99 3a    mov DWORD PTR [rsp+0x30],0x3a997502
98f:  c7 44 24 34 7a 64 82 4c    mov DWORD PTR [rsp+0x34],0x4c82647a
99e:  c7 44 24 38 99 8e 52 ef    mov DWORD PTR [rsp+0x38],0xef528e99
9a6:  c7 44 24 3c 94 86 a2 47    mov DWORD PTR [rsp+0x3c],0x47a28694

; Variable size passed to GetVariable path: 0x6D5, matching the IFR VarStore.
9bc:  48 c7 85 58 06 00 00 d5 06 00 00  mov QWORD PTR [rbp+0x658],0x6d5

; Representative state updates inside the loaded AmdSetupRPL buffer.
; Stack-layout analysis maps [rbp-0x7c] to VarOffset 0x44, which IFR names
; `iGPU Configuration`.
a7b:  80 7d 84 00                 cmp BYTE PTR [rbp-0x7c],0x0
a85:  c6 45 84 00                 mov BYTE PTR [rbp-0x7c],0x0   ; Disabled
...
ad3:  80 7d 84 00                 cmp BYTE PTR [rbp-0x7c],0x0
add:  c6 45 84 01                 mov BYTE PTR [rbp-0x7c],0x1   ; UMA_SPECIFIED

; Later path writes the changed variable and requests a hard reset.
b05:  41 b8 07 00 00 00           mov r8d,0x7
b0b:  ff 50 58                    call QWORD PTR [rax+0x58]
...
ba3:  ba f9 0c 00 00              mov edx,0xcf9
ba8:  b0 06                       mov al,0x6
baa:  ee                          out dx,al

; Cross-reference from IFR for AmdSetupRPL offset 0x44:
;   Auto               0x0F
;   iGPU Disabled      0x00
;   UMA_SPECIFIED      0x01 [default]
;   UMA_GAME_OPTIMIZED 0x03
;
; Combined with the surrounding PCI display-class scan, this is code-level
; evidence for the 1.17 dGPU/iGPU auto-detection changelog item.

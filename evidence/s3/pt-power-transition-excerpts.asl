// Focused ACPICA-disassembled excerpts from the new DRFXI 1.17 `PT` SSDT.
// Source firmware: DRFXI 1.17
// DRFXI.BIN SHA-256:
//   99f3bab5ea491202bf365c23e6416f9d1e8a649ad00f90c1f3e21f1a61e35c51
// Source module: AmdCpmOemAcpi.efi
// FFS GUID: 3821290E-B8DD-4821-8182-0361DE51609D
// ACPI OEM table id: PT
// Tool: ACPICA iasl 20260408
//
// This is intentionally NOT the complete vendor-derived SSDT. Only the small
// control-flow excerpts needed to support the S3/PCIe-resume analysis are kept.

// D0 / resume path. Independent analysis:
//   * DPSA == 0x43 is set by the matching D3 path below.
//   * M403 resolves to the firmware helper whose debug string calls it
//     CpmWakeLink.
//   * byte @ DADR+0x6B is polled for (value & 0x28) == 0x20.
//   * 0x13BB * 0x63 us ~= 500 ms maximum wait.
//   * firmware debug text explicitly says "Check DL_ACTIVE".
Method (_PS0, 0, Serialized)
{
    If (((DBUS == Zero) && ((_ADR == 0x00020001) && (DPSA == 0x43))))
    {
        DPSA = 0xEE
        Local3 = ((_ADR >> 0x10) & 0x1F)
        Local4 = (_ADR & 0x07)
        M403 (DBUS, Local3, Local4, One)

        Local1 = Zero
        Local2 = 0x13BB
        While ((((Local1 & 0x28) != 0x20) && (Local2 > Zero)))
        {
            Local1 = RPRM ((DADR + 0x6B), One)
            Local2 = (Local2 - One)
            Stall (0x63)
        }

        M403 (DBUS, Local3, Local4, Zero)
    }
}

// D3 path. Independent analysis:
//   * M402 resolves to a CPM helper labelled CpmSendPmeTurnOff by debug text.
//   * it is only invoked when an AMD per-port state field is 0x1B;
//   * DPSA = 0x43 is recorded for the corresponding resume path.
Method (_PS3, 0, Serialized)
{
    If (((DBUS == Zero) && (_ADR == 0x00020001)))
    {
        Local3 = ((_ADR >> 0x10) & 0x1F)
        Local4 = (_ADR & 0x07)
        Local0 = M401 (Zero, Local3, Local4)
        Local1 = (M471 (Zero, Local0, 0x04) + 0x0294)
        Local2 = (M249 (Zero, Zero, Zero, Local1) & 0x3F)
        If ((Local2 == 0x1B))
        {
            DPSA = 0x43
            M402 (Zero, Local3, Local4)
        }
    }
}

// Cross-reference excerpt from pre-existing CPMCMN SSDT.
// M403 sets/clears bit 22 of a platform-derived per-port register at +0x280.
Method (M403, 4, Serialized)
{
    Local4 = M401 (Arg0, Arg1, Arg2)
    If ((Local4 != 0xFF))
    {
        Local2 = (M471 (Arg0, Local4, 0x04) + 0x0280)
        Local0 = M249 (Zero, Zero, Zero, Local2)
        Local0 &= 0xFFBFFFFF
        Local1 = Arg3
        Local0 |= (Local1 << 0x16)
        M250 (Zero, Zero, Zero, Local2, Local0)
    }
}

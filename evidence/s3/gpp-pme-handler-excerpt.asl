// Focused ACPICA-disassembled excerpt from the new DRFXI 1.17 `GPP_PME_` SSDT.
// Source firmware: DRFXI 1.17
// DRFXI.BIN SHA-256:
//   99f3bab5ea491202bf365c23e6416f9d1e8a649ad00f90c1f3e21f1a61e35c51
// Source module: AmdCpmOemAcpi.efi
// FFS GUID: 3821290E-B8DD-4821-8182-0361DE51609D
// ACPI OEM table id: GPP_PME_
// Tool: ACPICA iasl 20260408
//
// The raw `_E10` and GPP0... names are template placeholders. The enclosing
// DXE module patches the edge-GPE method name and PCIe NameSegs before table
// installation according to platform data.
//
// This file keeps only the first representative port branch; the complete
// table repeats the same pattern for 21 logical PCIe ports.

Method (_E10, 0, NotSerialized)
{
    If ((\_GPE.ETP0 != 0xFF))
    {
        \_GPE.ETP0 = (M017 (Zero, One, One, 0x78, Zero, 0x18) >> 0x10)
        If (((\_GPE.ETP0 == One) || (\_GPE.ETP0 == 0x03)))
        {
            If (CondRefOf (\_SB.PCI0.GPP0))
            {
                // A platform-specific condition may issue Bus Check first.
                If ((M620 != Zero))
                {
                    If ((M049 (M620, 0x10) == One))
                    {
                        If (((M049 (M620, 0x52) & 0x02) == Zero))
                        {
                            Notify (\_SB.PCI0.GPP0, Zero) // Bus Check
                        }
                    }
                }

                Notify (\_SB.PCI0.GPP0, 0x02) // Device Wake
                Sleep (0x64)

                Local0 = M017 (Zero, One, One, 0x78, Zero, 0x20)
                If (((Local0 & 0x00030000) != Zero))
                {
                    M018 (Zero, One, One, 0x78, Zero, 0x20, Local0)
                    Local0 = M017 (Zero, One, One, 0x78, Zero, 0x20)
                    If (((Local0 & 0x00030000) != Zero))
                    {
                        M018 (Zero, One, One, 0x78, Zero, 0x20, Local0)
                        Local0 = M017 (Zero, One, One, 0x78, Zero, 0x20)
                    }
                }
            }
        }
    }
}

// Resolved helper from CPMCMN: construct a normal PCI ECAM address.
Method (M645, 3, Serialized)
{
    Local0 = M083
    Local0 += (Arg0 << 0x14) // bus
    Local0 += (Arg1 << 0x0F) // device
    Local0 += (Arg2 << 0x0C) // function
    Return (Local0)
}

// Independent analysis notes:
// - the handler checks PCI config register 0x78 status/event fields;
// - Notify(..., 0x02) is Device Wake in ACPI semantics;
// - the status bits are acknowledged/cleared by write-back and reread;
// - the real method name is patched from `_E10` to `_Exx` using a GPE value
//   derived by AmdCpmOemAcpi from MMIO 0xFED8025C.

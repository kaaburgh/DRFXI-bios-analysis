# DMI / SMBIOS changes

Last updated: 2026-09-10

A raw SMBIOS/DMI data FFS was identified at GUID:

```text
DAF4BF89-CE71-4917-B522-C89D32FBC59F
```

The following strings are present in official DRFXI 1.12:

```text
1.12
02/13/2025
Micro Computer (HK) Tech Limited
MotherBoard Series
MGDRDXA
MotherBoard
Shenzhen Meigao Electronic Equipment Co.,Ltd
DRFXI
```

By 1.15 they become:

```text
1.15
01/05/2026
Micro Computer (HK) Tech Limited
DeskMini Series
MGDRDXA
MINISFORUM
Meigao Innovation Technology (Shen Zhen) Co., Ltd
DRFXI
```

1.17 retains the newer product/manufacturer strings and updates the BIOS version/date to `1.17` / `08/28/2026`.

## Changelog attribution

The manufacturer-name change directly matches the 1.14 changelog item updating the DMI Base Board Manufacturer.

The neighboring changes:

```text
MotherBoard Series → DeskMini Series
MotherBoard        → MINISFORUM
```

could belong to the same 1.14 update or to 1.15's more general `Update DMI` item. Without 1.14, their exact landing release cannot be distinguished.

## Confidence

The underlying DMI data changes are confirmed. Only their exact split between 1.14 and 1.15 remains uncertain.

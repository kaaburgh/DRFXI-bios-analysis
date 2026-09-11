// SPDX-License-Identifier: MIT
// Minimal standalone UEFI x86_64 application for observing the
// AmdVariableProtection gate around the installed HII Config Routing hook.
//
// Intentionally contains no SetVariable(), RouteConfig(), ResetSystem(),
// filesystem access, or BIOS-setting modification code.

#include <stdint.h>
#include <stddef.h>

typedef uint8_t  UINT8;
typedef uint16_t UINT16;
typedef uint32_t UINT32;
typedef uint64_t UINT64;
typedef uint64_t UINTN;
typedef uint64_t EFI_STATUS;
typedef void     VOID;
typedef UINT16   CHAR16;
typedef VOID    *EFI_HANDLE;
typedef VOID    *EFI_EVENT;

typedef struct {
  UINT32 Data1;
  UINT16 Data2;
  UINT16 Data3;
  UINT8  Data4[8];
} EFI_GUID;

typedef struct {
  UINT64 Signature;
  UINT32 Revision;
  UINT32 HeaderSize;
  UINT32 CRC32;
  UINT32 Reserved;
} EFI_TABLE_HEADER;

struct _EFI_SIMPLE_TEXT_OUTPUT_PROTOCOL;
typedef EFI_STATUS (*EFI_TEXT_RESET)(struct _EFI_SIMPLE_TEXT_OUTPUT_PROTOCOL *, UINT8);
typedef EFI_STATUS (*EFI_TEXT_STRING)(struct _EFI_SIMPLE_TEXT_OUTPUT_PROTOCOL *, const CHAR16 *);
typedef struct _EFI_SIMPLE_TEXT_OUTPUT_PROTOCOL {
  EFI_TEXT_RESET Reset;
  EFI_TEXT_STRING OutputString;
  VOID *TestString;
  VOID *QueryMode;
  VOID *SetMode;
  VOID *SetAttribute;
  VOID *ClearScreen;
  VOID *SetCursorPosition;
  VOID *EnableCursor;
  VOID *Mode;
} EFI_SIMPLE_TEXT_OUTPUT_PROTOCOL;

typedef EFI_STATUS (*EFI_GET_VARIABLE)(
    const CHAR16 *VariableName,
    const EFI_GUID *VendorGuid,
    UINT32 *Attributes,
    UINTN *DataSize,
    VOID *Data);

typedef struct {
  EFI_TABLE_HEADER Hdr;
  VOID *GetTime;
  VOID *SetTime;
  VOID *GetWakeupTime;
  VOID *SetWakeupTime;
  VOID *SetVirtualAddressMap;
  VOID *ConvertPointer;
  EFI_GET_VARIABLE GetVariable;
  VOID *GetNextVariableName;
  VOID *SetVariable; // Present in the ABI layout only. Never called by this app.
  VOID *GetNextHighMonotonicCount;
  VOID *ResetSystem; // Present in the ABI layout only. Never called by this app.
  VOID *UpdateCapsule;
  VOID *QueryCapsuleCapabilities;
  VOID *QueryVariableInfo;
} EFI_RUNTIME_SERVICES;

typedef EFI_STATUS (*EFI_ALLOCATE_POOL)(UINT32 PoolType, UINTN Size, VOID **Buffer);
typedef EFI_STATUS (*EFI_FREE_POOL)(VOID *Buffer);
typedef EFI_STATUS (*EFI_LOCATE_PROTOCOL)(const EFI_GUID *Protocol, VOID *Registration, VOID **Interface);

typedef struct {
  EFI_TABLE_HEADER Hdr;
  VOID *RaiseTPL;
  VOID *RestoreTPL;
  VOID *AllocatePages;
  VOID *FreePages;
  VOID *GetMemoryMap;
  EFI_ALLOCATE_POOL AllocatePool;
  EFI_FREE_POOL FreePool;
  VOID *CreateEvent;
  VOID *SetTimer;
  VOID *WaitForEvent;
  VOID *SignalEvent;
  VOID *CloseEvent;
  VOID *CheckEvent;
  VOID *InstallProtocolInterface;
  VOID *ReinstallProtocolInterface;
  VOID *UninstallProtocolInterface;
  VOID *HandleProtocol;
  VOID *Reserved;
  VOID *RegisterProtocolNotify;
  VOID *LocateHandle;
  VOID *LocateDevicePath;
  VOID *InstallConfigurationTable;
  VOID *LoadImage;
  VOID *StartImage;
  VOID *Exit;
  VOID *UnloadImage;
  VOID *ExitBootServices;
  VOID *GetNextMonotonicCount;
  VOID *Stall;
  VOID *SetWatchdogTimer;
  VOID *ConnectController;
  VOID *DisconnectController;
  VOID *OpenProtocol;
  VOID *CloseProtocol;
  VOID *OpenProtocolInformation;
  VOID *ProtocolsPerHandle;
  VOID *LocateHandleBuffer;
  EFI_LOCATE_PROTOCOL LocateProtocol;
  VOID *InstallMultipleProtocolInterfaces;
  VOID *UninstallMultipleProtocolInterfaces;
  VOID *CalculateCrc32;
  VOID *CopyMem;
  VOID *SetMem;
  VOID *CreateEventEx;
} EFI_BOOT_SERVICES;

typedef struct {
  EFI_TABLE_HEADER Hdr;
  CHAR16 *FirmwareVendor;
  UINT32 FirmwareRevision;
  UINT32 _Pad;
  EFI_HANDLE ConsoleInHandle;
  VOID *ConIn;
  EFI_HANDLE ConsoleOutHandle;
  EFI_SIMPLE_TEXT_OUTPUT_PROTOCOL *ConOut;
  EFI_HANDLE StandardErrorHandle;
  EFI_SIMPLE_TEXT_OUTPUT_PROTOCOL *StdErr;
  EFI_RUNTIME_SERVICES *RuntimeServices;
  EFI_BOOT_SERVICES *BootServices;
  UINTN NumberOfTableEntries;
  VOID *ConfigurationTable;
} EFI_SYSTEM_TABLE;

struct _EFI_HII_CONFIG_ROUTING_PROTOCOL;
typedef EFI_STATUS (*EFI_HII_EXTRACT_CONFIG)(
    const struct _EFI_HII_CONFIG_ROUTING_PROTOCOL *This,
    const CHAR16 *Request,
    CHAR16 **Progress,
    CHAR16 **Results);

typedef struct _EFI_HII_CONFIG_ROUTING_PROTOCOL {
  EFI_HII_EXTRACT_CONFIG ExtractConfig;
  VOID *ExportConfig;
  VOID *RouteConfig; // ABI layout only. Never called.
  VOID *BlockToConfig;
  VOID *ConfigToBlock;
  VOID *GetAltConfig;
} EFI_HII_CONFIG_ROUTING_PROTOCOL;

#define EFI_SUCCESS              ((EFI_STATUS)0)
#define EFI_INVALID_PARAMETER    ((EFI_STATUS)0x8000000000000002ULL)
#define EFI_BUFFER_TOO_SMALL     ((EFI_STATUS)0x8000000000000005ULL)
#define EFI_NOT_FOUND            ((EFI_STATUS)0x800000000000000EULL)
#define EFI_OUT_OF_RESOURCES     ((EFI_STATUS)0x8000000000000009ULL)
#define EFI_LOADER_DATA          ((UINT32)2)
#define MAX_VAR_READ             ((UINTN)(64 * 1024))

_Static_assert(sizeof(EFI_GUID) == 16, "EFI_GUID size");
_Static_assert(offsetof(EFI_SYSTEM_TABLE, ConOut) == 0x40, "EFI_SYSTEM_TABLE.ConOut offset");
_Static_assert(offsetof(EFI_SYSTEM_TABLE, RuntimeServices) == 0x58, "EFI_SYSTEM_TABLE.RuntimeServices offset");
_Static_assert(offsetof(EFI_SYSTEM_TABLE, BootServices) == 0x60, "EFI_SYSTEM_TABLE.BootServices offset");
_Static_assert(offsetof(EFI_RUNTIME_SERVICES, GetVariable) == 0x48, "EFI_RUNTIME_SERVICES.GetVariable offset");
_Static_assert(offsetof(EFI_BOOT_SERVICES, AllocatePool) == 0x40, "EFI_BOOT_SERVICES.AllocatePool offset");
_Static_assert(offsetof(EFI_BOOT_SERVICES, FreePool) == 0x48, "EFI_BOOT_SERVICES.FreePool offset");
_Static_assert(offsetof(EFI_BOOT_SERVICES, LocateProtocol) == 0x140, "EFI_BOOT_SERVICES.LocateProtocol offset");

static EFI_SYSTEM_TABLE *gST;
static EFI_RUNTIME_SERVICES *gRT;
static EFI_BOOT_SERVICES *gBS;

static const EFI_GUID kGateGuid = {
  0x408F573D, 0x65EE, 0x49ED, {0x8B,0xC5,0x5A,0x32,0xBB,0xEA,0xE7,0x45}
};
// Force one ordinary PE/COFF DIR64 relocation so the image remains relocatable
// even though most generated code uses RIP-relative references.
__attribute__((used)) static volatile const VOID *gRelocAnchor = &kGateGuid;

static const EFI_GUID kHiiConfigRoutingGuid = {
  0x587E72D7, 0xCC50, 0x4F79, {0x82,0x09,0xCA,0x29,0x1F,0xC1,0xA1,0x0F}
};
static const CHAR16 kGateName[] = {
  'A','m','d','V','a','r','i','a','b','l','e','P','r','o','t','e','c','t','i','o','n',0
};

static void out(const CHAR16 *s) {
  if (gST && gST->ConOut && gST->ConOut->OutputString) {
    gST->ConOut->OutputString(gST->ConOut, s);
  }
}

static void out_ascii(const char *s) {
  CHAR16 buf[96];
  UINTN i = 0;
  while (*s) {
    if (i + 1 >= (sizeof(buf) / sizeof(buf[0]))) {
      buf[i] = 0;
      out(buf);
      i = 0;
    }
    buf[i++] = (UINT8)*s++;
  }
  if (i) {
    buf[i] = 0;
    out(buf);
  }
}

static void out_hex64(UINT64 v) {
  static const char h[] = "0123456789ABCDEF";
  char b[19];
  b[0] = '0'; b[1] = 'x';
  for (int i = 0; i < 16; ++i) {
    b[2+i] = h[(v >> ((15-i)*4)) & 0xF];
  }
  b[18] = 0;
  out_ascii(b);
}

static void out_hex32(UINT32 v) {
  static const char h[] = "0123456789ABCDEF";
  char b[11];
  b[0] = '0'; b[1] = 'x';
  for (int i = 0; i < 8; ++i) {
    b[2+i] = h[(v >> ((7-i)*4)) & 0xF];
  }
  b[10] = 0;
  out_ascii(b);
}

static void out_dec(UINTN v) {
  char b[24];
  int n = 0;
  if (v == 0) { out_ascii("0"); return; }
  while (v && n < (int)sizeof(b)-1) { b[n++] = '0' + (char)(v % 10); v /= 10; }
  for (int i = 0; i < n/2; ++i) { char t=b[i]; b[i]=b[n-1-i]; b[n-1-i]=t; }
  b[n]=0; out_ascii(b);
}

static void out_bytes(const UINT8 *p, UINTN n) {
  static const char h[] = "0123456789ABCDEF";
  char b[4];
  for (UINTN i = 0; i < n; ++i) {
    if (i) out_ascii(" ");
    b[0] = h[(p[i] >> 4) & 0xF];
    b[1] = h[p[i] & 0xF];
    b[2] = 0;
    out_ascii(b);
  }
}

static void newline(void) { out_ascii("\r\n"); }

static void print_status(EFI_STATUS s) {
  out_hex64(s);
  if (s == EFI_SUCCESS) out_ascii(" (EFI_SUCCESS)");
  else if (s == EFI_INVALID_PARAMETER) out_ascii(" (EFI_INVALID_PARAMETER)");
  else if (s == EFI_BUFFER_TOO_SMALL) out_ascii(" (EFI_BUFFER_TOO_SMALL)");
  else if (s == EFI_NOT_FOUND) out_ascii(" (EFI_NOT_FOUND)");
  else if (s == EFI_OUT_OF_RESOURCES) out_ascii(" (EFI_OUT_OF_RESOURCES)");
}

static EFI_STATUS inspect_gate(const char *label) {
  EFI_STATUS st;
  UINTN size = 0;
  UINT32 attrs = 0;
  VOID *data = NULL;

  out_ascii(label); newline();
  st = gRT->GetVariable(kGateName, &kGateGuid, &attrs, &size, NULL);
  out_ascii("  initial GetVariable: "); print_status(st); newline();

  if (st == EFI_NOT_FOUND) {
    out_ascii("  exists: no\r\n");
    return st;
  }

  if (st != EFI_BUFFER_TOO_SMALL && st != EFI_SUCCESS) {
    out_ascii("  exists: unknown (GetVariable error)\r\n");
    out_ascii("  reported DataSize: "); out_dec(size); newline();
    out_ascii("  attributes: "); out_hex32(attrs); newline();
    return st;
  }

  out_ascii("  exists: yes\r\n");
  out_ascii("  attributes: "); out_hex32(attrs); newline();
  out_ascii("  DataSize: "); out_dec(size); newline();

  if (size == 0) {
    out_ascii("  value: <zero length>\r\n");
    return st;
  }
  if (size > MAX_VAR_READ) {
    out_ascii("  value: <not read; exceeds 64 KiB safety cap>\r\n");
    return st;
  }

  st = gBS->AllocatePool(EFI_LOADER_DATA, size, &data);
  if (st != EFI_SUCCESS || data == NULL) {
    out_ascii("  AllocatePool: "); print_status(st); newline();
    return st;
  }

  UINTN read_size = size;
  UINT32 read_attrs = 0;
  st = gRT->GetVariable(kGateName, &kGateGuid, &read_attrs, &read_size, data);
  out_ascii("  value GetVariable: "); print_status(st); newline();
  if (st == EFI_SUCCESS) {
    out_ascii("  attributes (read): "); out_hex32(read_attrs); newline();
    out_ascii("  DataSize (read): "); out_dec(read_size); newline();
    out_ascii("  value hex: "); out_bytes((const UINT8 *)data, read_size); newline();
  }

  gBS->FreePool(data);
  return st;
}

__attribute__((ms_abi))
EFI_STATUS efi_main(EFI_HANDLE ImageHandle, EFI_SYSTEM_TABLE *SystemTable) {
  (void)ImageHandle;
  (void)gRelocAnchor;
  gST = SystemTable;
  gRT = SystemTable->RuntimeServices;
  gBS = SystemTable->BootServices;

  out_ascii("AmdVariableProtectionProbe v1\r\n");
  out_ascii("READ-ONLY application; firmware variables are only queried.\r\n\r\n");

  out_ascii("[Phase 1] baseline gate\r\n");
  inspect_gate("AmdVariableProtection before ExtractConfig:");

  out_ascii("\r\n[Phase 2] HII Config Routing discovery\r\n");
  EFI_HII_CONFIG_ROUTING_PROTOCOL *routing = NULL;
  EFI_STATUS st = gBS->LocateProtocol(&kHiiConfigRoutingGuid, NULL, (VOID **)&routing);
  out_ascii("  LocateProtocol: "); print_status(st); newline();
  out_ascii("  protocol instance: "); out_hex64((UINT64)(UINTN)routing); newline();
  if (st != EFI_SUCCESS || routing == NULL) {
    out_ascii("  ExtractConfig: <not available>\r\n");
    out_ascii("\r\n[Phase 4] post-trigger gate (trigger skipped)\r\n");
    inspect_gate("AmdVariableProtection after skipped ExtractConfig:");
    return EFI_SUCCESS;
  }
  out_ascii("  ExtractConfig pointer: "); out_hex64((UINT64)(UINTN)routing->ExtractConfig); newline();

  out_ascii("\r\n[Phase 3] trigger installed ExtractConfig\r\n");
  out_ascii("  Request: NULL (intentional defined EFI_INVALID_PARAMETER path in original router)\r\n");
  CHAR16 *progress = (CHAR16 *)(UINTN)0x1111111111111111ULL;
  CHAR16 *results = NULL;
  st = routing->ExtractConfig(routing, NULL, &progress, &results);
  out_ascii("  ExtractConfig status: "); print_status(st); newline();
  out_ascii("  Progress pointer: "); out_hex64((UINT64)(UINTN)progress); newline();
  out_ascii("  Results pointer: "); out_hex64((UINT64)(UINTN)results); newline();
  if (results != NULL) {
    out_ascii("  NOTE: non-NULL Results returned; freeing pool.\r\n");
    gBS->FreePool(results);
  }

  out_ascii("\r\n[Phase 4] post-trigger gate\r\n");
  inspect_gate("AmdVariableProtection after ExtractConfig:");

  out_ascii("\r\nDone. Reboot/power-cycle before any further experiment.\r\n");
  return EFI_SUCCESS;
}

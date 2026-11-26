/* Passive DRFXI 1.15 APCB inventory. Never calls APCB or SMM methods.
 * Build only for x64 UEFI. A stock CRC match is identification, not authentication. */
#include <stdint.h>
#include <stddef.h>
typedef uint8_t U8; typedef uint16_t U16; typedef uint32_t U32; typedef uint64_t U64;
typedef uintptr_t N; typedef N STATUS; typedef void *HANDLE;
#define API __attribute__((ms_abi))
#define ERR(x) (UINT64_C(0x8000000000000000)|(x))
#define MAX_HANDLES 4096u
typedef struct {U32 a;U16 b,c;U8 d[8];} GUID;
typedef struct {U64 sig;U32 rev,size,crc,res;} HEADER;
typedef STATUS(API *OUT)(void*,const U16*);
typedef struct {void*reset;OUT output;} CONOUT;
typedef STATUS(API *FREE)(void*);
typedef STATUS(API *HANDLE_PROTO)(HANDLE,const GUID*,void**);
typedef STATUS(API *LOCATE_HANDLES)(U32,const GUID*,void*,N*,HANDLE**);
typedef struct {HEADER h;void*pre[6];FREE free;void*mid[9];HANDLE_PROTO handle;void*more[19];LOCATE_HANDLES list;} BS;
typedef STATUS(API *GETVAR)(const U16*,const GUID*,U32*,N*,void*);
typedef struct {HEADER h;void*pre[6];GETVAR get;} RT;
typedef struct {HEADER h;void*vendor;U32 rev;HANDLE in_h;void*in;HANDLE out_h;CONOUT*out;HANDLE err_h;void*err;RT*rt;BS*bs;} ST;
typedef struct {U32 revision;HANDLE parent;ST*system;HANDLE device;void*path;void*reserved;U32 options_size;void*options;void*base;U64 size;} IMAGE;
_Static_assert(sizeof(void*)==8,"x64 only");
_Static_assert(offsetof(BS,free)==0x48&&offsetof(BS,handle)==0x98&&offsetof(BS,list)==0x138,"BS ABI");
_Static_assert(offsetof(IMAGE,base)==0x40&&offsetof(IMAGE,size)==0x48,"image ABI");
_Static_assert(offsetof(ST,bs)==0x60&&offsetof(RT,get)==0x48,"ST/RT ABI");
static const GUID apcb_guid={0x7189e04e,0x6284,0x4953,{0xa5,0x43,0xa3,0x1f,0x89,0xa1,0xa7,0xbf}};
static const GUID image_guid={0x5b1b31a1,0x9562,0x11d2,{0x8e,0x3f,0,0xa0,0xc9,0x69,0x72,0x3b}};
static const GUID gate_guid={0x408f573d,0x65ee,0x49ed,{0x8b,0xc5,0x5a,0x32,0xbb,0xea,0xe7,0x45}};
static const GUID cbs_guid={0x3a997502,0x647a,0x4c82,{0x99,0x8e,0x52,0xef,0x94,0x86,0xa2,0x47}};
static const U16 gate_name[]={65,109,100,86,97,114,105,97,98,108,101,80,114,111,116,101,99,116,105,111,110,0};
static const U16 cbs_name[]={65,109,100,83,101,116,117,112,82,80,76,0};
static const U16 methods[]={0xa00,0x1a9c,0x1d7c,0x1ea0,0x1fd4,0x99c,0xaa8,0xba4,0x99c,0x99c,0x99c,0xc8c,0xd34,0xdec,0xef0,0xfdc,0x10e0,0x11cc,0x12d0,0x13bc,0x14c0,0x15a8,0x16f4,0x191c,0x19dc,0x1834,0x2108};
static CONOUT*con;
static U32 u32(const U8*p){return (U32)p[0]|(U32)p[1]<<8|(U32)p[2]<<16|(U32)p[3]<<24;}
static U64 u64(const U8*p){return (U64)u32(p)|((U64)u32(p+4)<<32);}
static int eq(const void*a,const void*b,N n){const U8*x=a,*y=b;for(N i=0;i<n;i++)if(x[i]!=y[i])return 0;return 1;}
static U32 crc32(const U8*p,N n){U32 c=~0u;for(N i=0;i<n;i++){c^=p[i];for(int j=0;j<8;j++)c=(c>>1)^((0u-(c&1))&0xedb88320u);}return ~c;}
static void say(const char*s){U16 b[120];N n=0;while(*s){b[n++]=(U8)*s++;if(n==119){b[n]=0;con->output(con,b);n=0;}}b[n]=0;con->output(con,b);}
static void field(const char*s,U64 n){char b[19]="0x0000000000000000";for(int i=17;i>=2;i--){b[i]="0123456789ABCDEF"[n&15];n>>=4;}say(s);say(b);say("\r\n");}
typedef struct {U8 cbs[0x6d5],gate;U32 gate_attr,cbs_attr;int valid;} SNAP;
static SNAP before,after;
static void snapshot(RT*rt,SNAP*s){N n=1;STATUS a=rt->get(gate_name,&gate_guid,&s->gate_attr,&n,&s->gate);int g=!a&&n==1&&s->gate==1&&s->gate_attr==0x26;field("Gate read status: ",a);if(!a&&n==1)field("Gate: ",s->gate);n=sizeof s->cbs;STATUS b=rt->get(cbs_name,&cbs_guid,&s->cbs_attr,&n,s->cbs);field("CBS read status: ",b);s->valid=g&&!b&&n==sizeof s->cbs&&s->cbs_attr==7&&u32(s->cbs)==0xfc4053aa&&u32(s->cbs+4)==0x2d8;if(s->valid){field("Saved MCR: ",s->cbs[0x263]);}}
/* No provider pointer dereference before proving it lies at the expected offset
 * inside a firmware-reported loaded image of the expected size. */
static int match(const IMAGE*im,const void*iface){if(!im||!im->base||im->size<0xdd00||im->size>0xe000)return 0;N base=(N)im->base;if(base>UINTPTR_MAX-im->size||(N)iface!=base+0xa160)return 0;const U8*b=im->base;
 if(crc32(b+0x280,0x9d62)!=0x720886d8||!eq(b+0xa050,&apcb_guid,16)||u64(b+0xa160)!=3)return 0;
 for(N i=0;i<sizeof methods/sizeof methods[0];i++)if(u64(b+0xa168+8*i)!=base+methods[i])return 0;return 1;}
static STATUS inventory(BS*bs){N n=0;HANDLE*h=0;void*iface=0;STATUS s=bs->list(2,&apcb_guid,0,&n,&h);field("APCB protocol enumeration: ",s);if(s)return s;if(!h)return ERR(2);field("APCB provider count: ",n);if(n!=1){bs->free(h);return ERR(2);}s=bs->handle(h[0],&apcb_guid,&iface);bs->free(h);if(s||!iface)return ERR(14);
 n=0;h=0;s=bs->list(2,&image_guid,0,&n,&h);if(s)return s;if(!h)return ERR(2);if(!n||n>MAX_HANDLES){bs->free(h);return ERR(2);}N hits=0;const U8*b=0;for(N i=0;i<n;i++){IMAGE*im=0;if(!bs->handle(h[i],&image_guid,(void**)&im)&&match(im,iface)){hits++;b=im->base;}}bs->free(h);field("Stock code + relocated table matches: ",hits);if(hits!=1)return ERR(14);
 U8 mode=b[0xcfa8],debug=b[0xd074];field("DXE-to-SMM dispatch flag: ",mode);field("Diagnostic flag: ",debug);if(mode>1||debug>1)return ERR(2);say(mode?"SMM routing selected.\r\n":"Local DXE routing selected.\r\n");return 0;}
STATUS API efi_main(HANDLE self,ST*st){(void)self;con=st->out;say("DRFXI APCB INVENTORY v1 (no APCB calls / no SMI requests)\r\n");snapshot(st->rt,&before);STATUS s=inventory(st->bs);snapshot(st->rt,&after);field("Gate and CBS baseline valid: ",before.valid&&after.valid);int same=before.valid&&after.valid&&eq(before.cbs,after.cbs,sizeof before.cbs);field("Gate and full CBS unchanged: ",same);field("Inventory status: ",s);say("Effective MCR NOT queried. End inventory.\r\n");return s?s:same?0:ERR(14);}

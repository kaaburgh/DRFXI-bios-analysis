/* DRFXI 1.15 HII diagnostic. No browser, config callbacks, NVRAM writes or HII updates.
 * Freestanding x64 UEFI application, using only public UEFI ABI slots.
 * ExportPackageLists can invoke firmware-owned EXPORT_PACK notifications.
 */
#include <stdint.h>
#include <stddef.h>
typedef uint8_t U8; typedef uint16_t U16; typedef uint32_t U32; typedef uint64_t U64;
typedef uintptr_t N; typedef N STATUS; typedef void *HANDLE;
#define ERR(x) ((STATUS)(UINT64_C(0x8000000000000000)|(x)))
#define TOO_SMALL ERR(5)
#define MAX_LIST (16u*1024*1024)
#define MAX_HANDLES 4096u
static const U8 package_guid[16]={0x25,0xff,0xa0,0x38,0x7b,0xef,0xe7,0x47,0xab,0x63,0xe5,0x6d,0x9a,0x67,0x36,0x1b};
static const U8 cbs_guid[16]={0xed,9,0x32,0xc0,0x4b,0x5f,0x31,0x46,0xbd,3,0x8e,0xd6,0x27,0xcd,0x9d,0xaf};
static U16 u16(const U8*p){return (U16)(p[0]|p[1]<<8);}
static U32 u32(const U8*p){return (U32)p[0]|(U32)p[1]<<8|(U32)p[2]<<16|(U32)p[3]<<24;}
static int eq(const U8*a,const U8*b,N n){for(N i=0;i<n;i++)if(a[i]!=b[i])return 0;return 1;}
static U32 crc32(const U8*p,N n){U32 c=~0u;for(N i=0;i<n;i++){c^=p[i];for(int j=0;j<8;j++)c=(c>>1)^((0u-(c&1))&0xedb88320u);}return ~c;}
typedef struct {U32 sets,forms,refs,mcr,stock,malformed; U32 len,crc; } REPORT;
/* Walk opcode boundaries; count only target formset and intended parent.
 * Exact stock CRC is a diagnostic comparison, not authentication. */
static int inspect_form(const U8*p,N n,REPORT*r){
 if(n<4 || (u32(p)&0xffffffu)!=n || p[3]!=2)return 0;
 U16 form=0; N depth=0,fsdepth=0,formdepth=0; int target=0;
 for(N i=4;i<n;){
  if(n-i<2)return 0; U8 op=p[i],len=p[i+1]&127,scope=p[i+1]>>7;
  if(len<2 || len>n-i)return 0;
  if(op==0x29){if(len!=2||scope||!depth)return 0;
   if(formdepth==depth){form=0;formdepth=0;} if(fsdepth==depth){target=0;fsdepth=0;} depth--;}
  else{
   if(op==0x0e){if(len<23||!scope||depth)return 0;target=eq(p+i+2,cbs_guid,16);fsdepth=depth+1;
    if(target){r->sets++;r->len=(U32)n;r->crc=crc32(p,n);if(n==30145&&r->crc==0x7897c39a)r->stock++;}}
   if(target && op==1){if(len<6||!scope||formdepth)return 0;form=u16(p+i+2);formdepth=depth+1;
    if(form==0x7000)r->forms|=1;else if(form==0x7003)r->forms|=2;else if(form==0x7012)r->forms|=4;else if(form==0x701b)r->forms|=8;}
   if(target&&op==0x0f&&len>=15){U16 q=u16(p+i+6),dst=u16(p+i+13);
    if(form==0x7000&&q==3&&dst==0x7003)r->refs|=1;
    if(form==0x7003&&q==0x37&&dst==0x7012)r->refs|=2;
    if(form==0x7012&&q==0x40&&dst==0x701b)r->refs|=4;}
   if(target&&form==0x701b&&op==5&&len>=17&&u16(p+i+6)==0x9b&&u16(p+i+8)==0x5000&&u16(p+i+10)==0x263)r->mcr++;
   if(scope)depth++;
  }i+=len;
 }return depth==0;
}
static int inspect_list(const U8*p,N n,REPORT*r){
 if(n<24||u32(p+16)!=n||!eq(p,package_guid,16))return 0;
 for(N i=20;i<n;){if(n-i<4)return 0;U32 s=u32(p+i)&0xffffffu;U8 type=p[i+3];if(s<4||s>n-i)return 0;
  if(type==0xdf)return s==4&&i+s==n;
  if(type==2&&!inspect_form(p+i,s,r))return 0;
  i+=s;
 }return 0;
}
#ifdef HOST_TEST
#include <stdio.h>
#include <stdlib.h>
int main(int argc,char**argv){if(argc!=2)return 2;FILE*f=fopen(argv[1],"rb");if(!f)return 2;U8*b=malloc(MAX_LIST);size_t n=fread(b,1,MAX_LIST,f);int extra=fgetc(f);fclose(f);REPORT r={0};int ok=extra==EOF&&inspect_list(b,n,&r);free(b);printf("ok=%d sets=%u forms=%X refs=%X mcr=%u stock=%u len=%u crc=%08X\n",ok,r.sets,r.forms,r.refs,r.mcr,r.stock,r.len,r.crc);return ok?0:1;}
#else
/* No external runtime or UEFI SDK necessary. x64 only. */
#define API __attribute__((ms_abi))
typedef struct {U32 a;U16 b,c;U8 d[8];} GUID;
typedef struct {U64 sig;U32 rev,size,crc,res;} HEADER;
typedef STATUS(API *OUT)(void*,const U16*);
typedef struct {void*reset;OUT output;} CONOUT;
typedef STATUS(API *ALLOC)(U32,N,void**);
typedef STATUS(API *FREE)(void*);
typedef STATUS(API *LOCATE)(const GUID*,void*,void**);
typedef STATUS(API *HANDLE_PROTO)(HANDLE,const GUID*,void**);
typedef struct {HEADER h;void*pre[5];ALLOC alloc;FREE free;void*mid[9];HANDLE_PROTO handle;void*more[20];LOCATE locate;} BS;
typedef STATUS(API *GETVAR)(const U16*,const GUID*,U32*,N*,void*);
typedef struct {HEADER h;void*pre[6];GETVAR get;} RT;
typedef struct {HEADER h;void*vendor;U32 rev;HANDLE in_h;void*in;HANDLE out_h;CONOUT*out;HANDLE err_h;void*err;RT*rt;BS*bs;} ST;
typedef struct DB DB;
typedef STATUS(API *LIST)(const DB*,U8,const GUID*,N*,HANDLE*);
typedef STATUS(API *EXPORT)(const DB*,HANDLE,N*,void*);
typedef STATUS(API *OWNER)(const DB*,HANDLE,HANDLE*);
struct DB {void*unused[3];LIST list;EXPORT export;void*other[5];OWNER owner;};
_Static_assert(sizeof(void*)==8,"x64 only");_Static_assert(offsetof(BS,alloc)==0x40,"alloc");_Static_assert(offsetof(BS,free)==0x48,"free");_Static_assert(offsetof(BS,handle)==0x98,"handle");
_Static_assert(offsetof(RT,get)==0x48,"getvar");_Static_assert(offsetof(ST,rt)==0x58,"rt");_Static_assert(offsetof(BS,locate)==0x140,"locate");_Static_assert(offsetof(ST,out)==0x40,"out");_Static_assert(offsetof(ST,bs)==0x60,"bs");_Static_assert(offsetof(DB,owner)==80,"owner");
static const GUID db_guid={0xef9fc172,0xa1b2,0x4693,{0xb3,0x27,0x6d,0x32,0xfc,0x41,0x60,0x42}};
static const GUID dp_guid={0x09576e91,0x6d3f,0x11d2,{0x8e,0x39,0x00,0xa0,0xc9,0x69,0x72,0x3b}};
static const U8 owner_path[24]={1,4,20,0,2,0x75,0x99,0x3a,0x7a,0x64,0x82,0x4c,0x99,0x8e,0x52,0xef,0x94,0x86,0xa2,0x47,0x7f,0xff,4,0};
static const GUID access_guid={0x330d4706,0xf2a0,0x4e4f,{0xa3,0x69,0xb6,0x6f,0xa8,0xd5,0x43,0x85}};
static const GUID *volatile database_guid_ptr=&db_guid;
static const GUID browser_guid={0xb9d4c360,0xbcfb,0x4f9b,{0x92,0x98,0x53,0xc1,0x36,0x98,0x22,0x58}};
static const GUID gate_guid={0x408f573d,0x65ee,0x49ed,{0x8b,0xc5,0x5a,0x32,0xbb,0xea,0xe7,0x45}};
static const GUID variable_guid={0x3a997502,0x647a,0x4c82,{0x99,0x8e,0x52,0xef,0x94,0x86,0xa2,0x47}};
static const U16 gate_name[]={65,109,100,86,97,114,105,97,98,108,101,80,114,111,116,101,99,116,105,111,110,0};
static const U16 cbs_name[]={65,109,100,83,101,116,117,112,82,80,76,0};
static U8 cbs_before[0x6d5],cbs_after[0x6d5];
static CONOUT*con;
static void say(const char*s){U16 b[120];N n=0;while(*s){b[n++]=(U8)*s++;if(n==119){b[n]=0;con->output(con,b);n=0;}}b[n]=0;con->output(con,b);}
static void hex(U64 v){char b[19]="0x0000000000000000";for(int i=17;i>=2;i--){b[i]="0123456789ABCDEF"[v&15];v>>=4;}say(b);}
static void field(const char*s,U64 n){say(s);hex(n);say("\r\n");}
static int read_state(RT*rt,U8*cbs,const char*label,int*locked){
 *locked=0;
 say(label);say("\r\n");
 U8 gate=0;N n=1;U32 attrs=0;STATUS s=rt->get(gate_name,&gate_guid,&attrs,&n,&gate);
 field("  protection gate GetVariable status: ",s);
 if(!s){field("  gate bytes: ",n);field("  gate attributes: ",attrs);if(n==1&&gate<=1)field("  gate value: ",gate);}
 *locked=!s&&n==1&&gate==1&&attrs==0x26;
 n=0x6d5;attrs=0;s=rt->get(cbs_name,&variable_guid,&attrs,&n,cbs);
 field("  CBS GetVariable status: ",s);field("  CBS size: ",n);
 if(s||n!=0x6d5||u32(cbs)!=0xfc4053aau||u32(cbs+4)!=0x2d8u)return 0;
 field("  saved Combo CBS: ",cbs[0x20]);field("  saved MCR: ",cbs[0x263]);
 return 1;
}
STATUS API efi_main(HANDLE image,ST*st){(void)image;con=st->out;BS*bs=st->bs;DB*db=0;void*browser=0;
 say("DRFXI HII PROBE v1 (no browser, no direct writes)\r\n");
 STATUS s=bs->locate(database_guid_ptr,0,(void**)&db);field("HII database status: ",s);if(s||!db)return ERR(14);
 s=bs->locate(&browser_guid,0,&browser);field("FormBrowser2 status: ",s);
 int locked_before=0,locked_after=0;
 int before=read_state(st->rt,cbs_before,"Baseline (passive GetVariable)",&locked_before);
 if(!before||!locked_before){say("Unexpected baseline; no HII exports attempted. Stop.\r\n");return ERR(14);}
 N bytes=0;s=db->list(db,0,0,&bytes,0);field("List size status: ",s);
 if(s!=TOO_SMALL||!bytes||bytes>MAX_HANDLES*sizeof(HANDLE)||bytes%sizeof(HANDLE))return ERR(2);
 HANDLE*handles=0;N cap=bytes;s=bs->alloc(4,cap,(void**)&handles);if(s||!handles)return ERR(9);
 s=db->list(db,0,0,&bytes,handles);if(s||bytes>cap||bytes%sizeof(HANDLE)){bs->free(handles);return ERR(2);}
 field("All package-list handles: ",bytes/sizeof(HANDLE));U32 matches=0,stock=0,failures=0,owners=0,config_access=0;
 for(N i=0;i<bytes/sizeof(HANDLE);i++){
  /* The stock driver installs this exact vendor device path on the HII owner.
   * Avoid exporting unrelated package lists (and invoking their notifiers).
   * If the vendor path differs, stop instead of guessing an owner. */
  HANDLE owner=0;void*path=0;void*access=0;
  s=db->owner(db,handles[i],&owner);if(s||!owner)continue;
  s=bs->handle(owner,&dp_guid,&path);if(s||!path||!eq(path,owner_path,4)||!eq((const U8*)path+4,owner_path+4,16)||!eq((const U8*)path+20,owner_path+20,4))continue;
  owners++;field("CBS owner path match on handle index: ",i);
  s=bs->handle(owner,&access_guid,&access);field("  owner ConfigAccess status: ",s);if(!s&&access)config_access++;
  N n=0;void*buf=0;s=db->export(db,handles[i],&n,0);
  if((s!=TOO_SMALL&&s!=ERR(9))||n<24||n>MAX_LIST){failures++;continue;}
  N alloc=n;s=bs->alloc(4,n,&buf);if(s||!buf){failures++;continue;}
  s=db->export(db,handles[i],&n,buf);REPORT r={0};int valid=!s&&n<=alloc&&inspect_list(buf,n,&r);
  if(!valid)failures++;
  field("  exported list GUID match: ",!s&&n>=24&&n<=alloc&&eq(buf,package_guid,16));field("  valid package list: ",valid);
  if(r.sets){matches+=r.sets;stock+=valid?r.stock:0;field("CBS formset match on handle index: ",i);field("  target formsets: ",r.sets);field("  forms mask (7000/7003/7012/701B = 0xF): ",r.forms);field("  refs mask (expected 0x7): ",r.refs);field("  MCR question count: ",r.mcr);field("  forms package bytes: ",r.len);field("  forms CRC32 (stock 0x7897C39A): ",r.crc);field("  exact stock CRC+length: ",r.stock);
  }
  bs->free(buf);
 }
 bs->free(handles);field("CBS owner path matches: ",owners);field("ConfigAccess present: ",config_access);field("CBS formsets total: ",matches);field("Stock matches in valid lists: ",stock);field("Export/parse failures: ",failures);
 int after=read_state(st->rt,cbs_after,"After export (passive GetVariable)",&locked_after);
 field("Protection gate still in expected state: ",locked_after);
 if(before&&after)field("CBS full payload unchanged: ",eq(cbs_before,cbs_after,sizeof cbs_before));
 else say("CBS equality unavailable.\r\n");
 say("End probe. No SendForm, ExtractConfig, RouteConfig, Callback, UpdatePackageList or SetVariable invoked by app.\r\n");
 return owners==1&&config_access==1&&matches==1&&stock==1&&!failures&&before&&after&&locked_before&&locked_after&&eq(cbs_before,cbs_after,sizeof cbs_before)?0:ERR(14);
}
#endif

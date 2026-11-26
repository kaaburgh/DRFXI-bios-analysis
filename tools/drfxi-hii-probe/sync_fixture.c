/* OVMF ONLY: execute three reviewed, position-independent slices of the exact
 * stock CBS PE against local buffers and a mock APCB vtable. No actual AMD
 * drivers, variable services, SPI, or real APCB protocol calls. */
#define efi_main probe_entry
#include "hii_probe.c"
#undef efi_main
extern void API stock_defaults(U8*);
extern U32 API stock_hash(U8*);
extern STATUS API stock_sync(U8*,void*);
#define MCR 0xfedb01f8u
#define FP 0xb331378eu
#define MAX_RECORDS 128u
struct record {U32 token,value;U8 width,priority;};
struct trace {struct record rec[MAX_RECORDS];U32 n,acquire,clear,flush,release,bad;};
static struct trace tr,base;
static U8 block[0x6d5],initial[0x6d5],before[0x6d5];
static void *apcb[25];
static U32 fault;
static STATUS API acquire(void*p){if(p!=apcb)tr.bad++;tr.acquire++;return fault==1?ERR(7):0;}
static STATUS API clear(void*p,U8 priority){if(p!=apcb||priority!=3)tr.bad++;tr.clear++;return fault==2?ERR(7):0;}
static STATUS API flush(void*p){if(p!=apcb)tr.bad++;tr.flush++;return fault==4?ERR(7):0;}
static STATUS API release(void*p){if(p!=apcb)tr.bad++;tr.release++;return fault==5?ERR(7):0;}
static STATUS put(void*p,U8 priority,U32 token,U32 value,U8 width){if(p!=apcb||priority!=3||tr.n>=MAX_RECORDS){tr.bad++;return ERR(2);}tr.rec[tr.n++]=(struct record){token,value,width,priority};return fault==3&&token==MCR?ERR(7):0;}
static STATUS API setbool(void*p,U8 priority,U32 token,U8 value){return put(p,priority,token,value,1);}
static STATUS API set8(void*p,U8 priority,U32 token,U8 value){return put(p,priority,token,value,1);}
static STATUS API set16(void*p,U8 priority,U32 token,U16 value){return put(p,priority,token,value,2);}
static STATUS API set32(void*p,U8 priority,U32 token,U32 value){return put(p,priority,token,value,4);}
static void copy(void*d,const void*s,N n){for(N i=0;i<n;i++)((U8*)d)[i]=((const U8*)s)[i];}
static void zero(void*d,N n){for(N i=0;i<n;i++)((U8*)d)[i]=0;}
static int check(U8 mcr,U32 fail,int compare){fault=fail;zero(&tr,sizeof tr);copy(block,initial,sizeof block);block[0x263]=mcr;copy(before,block,sizeof block);
 STATUS s=stock_sync(block,apcb);field("MCR input: ",mcr);field("Injected failure: ",fail);field("Sync status: ",s);field("  acquire: ",tr.acquire);field("  clear: ",tr.clear);field("  token calls: ",tr.n);field("  flush: ",tr.flush);field("  release: ",tr.release);
 U32 m=0,fp=0,k=0;int same=1;for(U32 i=0;i<tr.n;i++){struct record*r=&tr.rec[i];if(r->token==MCR){m++;field("  MCR token value: ",r->value);if(r->value!=mcr||r->width!=1)same=0;continue;}if(r->token==FP){fp++;if(r->value!=u32(block+8))same=0;}if(compare){if(k>=base.n||r->token!=base.rec[k].token||r->value!=base.rec[k].value||r->width!=base.rec[k].width||r->priority!=base.rec[k].priority)same=0;k++;}}
 if(compare&&k!=base.n)same=0;
 field("  MCR token count: ",m);field("  fingerprint token count: ",fp);field("  same non-MCR records: ",same);field("  input unchanged: ",eq(block,before,sizeof block));
 if(fail==1)return s==ERR(7)&&tr.acquire==1&&!tr.clear&&!tr.n&&!tr.flush&&!tr.release&&!tr.bad;
 return s==0&&tr.acquire==1&&tr.clear==1&&tr.flush==1&&tr.release==1&&!tr.bad&&m==(mcr==255?0:1)&&fp==1&&same&&eq(block,before,sizeof block);}
STATUS API efi_main(HANDLE image,ST*st){(void)image;con=st->out;say("OVMF STOCK CBS SYNC SLICES FIXTURE ONLY\r\n");
 apcb[0x60/8]=(void*)acquire;apcb[0xc0/8]=(void*)clear;apcb[0x08/8]=(void*)flush;apcb[0x68/8]=(void*)release;apcb[0x78/8]=(void*)setbool;apcb[0x88/8]=(void*)set8;apcb[0x98/8]=(void*)set16;apcb[0xa8/8]=(void*)set32;
 stock_defaults(initial);field("Default MCR: ",initial[0x263]);if(initial[0x263]!=255||u32(initial)!=0xfc4053aa||u32(initial+4)!=0x2d8)return ERR(2);initial[0x20]=0x43;
 /* Synthetic timing override; this is NOT the owner's configuration. */
 initial[0x116]=1;initial[0x119]=1;initial[0x11a]=36;initial[0x11b]=0;
 U32 oldhash=stock_hash(initial);for(int i=0;i<4;i++)initial[8+i]=(U8)(oldhash>>(8*i));field("Auto fingerprint: ",oldhash);
 copy(block,initial,sizeof block);block[0x263]=0;U32 offhash=stock_hash(block);field("Disabled fingerprint: ",offhash);block[0x263]=1;U32 onhash=stock_hash(block);field("Enabled fingerprint: ",onhash);if(oldhash==offhash||oldhash==onhash||offhash==onhash)return ERR(2);
 if(!check(255,0,0))return ERR(2);copy(&base,&tr,sizeof base);
 if(!check(0,0,1)||!check(1,0,1)||!check(1,1,0)||!check(1,2,1)||!check(1,3,1)||!check(1,4,1)||!check(1,5,1))return ERR(2);
 say("STOCK CBS SYNC FIXTURE PASS\r\n");return 0;}

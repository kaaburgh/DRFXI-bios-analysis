/* OVMF ONLY: exact stock PE code, private RAM context, mock AMD protocols.
 * The original DXE entry point is NEVER invoked; only audited functions.
 * No global firmware service pointer is modified. */
#define efi_main probe_entry
#include "hii_probe.c"
#undef efi_main
extern const U8 stock_pe[],stock_pe_end[];
#define MCR 0xfedb01f8u
#define FP 0xb331378eu
static BS *real_bs;static void *real_routing;static U8 *pe;
static U8 initial[0x6d5],cache[0x6d5],saved[0x6d5],before[0x6d5];
static void *fake_bs[48],*fake_rt[16],*apcb[25],*router[6];
static U32 stored_fp,fp_attempt,mcr_attempt,token_calls,writes,reads,locates,acquires,clears,flushes,releases,mcr_calls,bad;
static U32 fault;
static const GUID apcb_guid={0x7189e04e,0x6284,0x4953,{0xa5,0x43,0xa3,0x1f,0x89,0xa1,0xa7,0xbf}};
static const GUID routing_guid={0x587e72d7,0xcc50,0x4f79,{0x82,9,0xca,0x29,0x1f,0xc1,0xa1,0x0f}};
static const U16 resp[]=L"GUID=0275993a7a64824c998e52ef9486a247&NAME=0041006d00640053006500740075007000520050004c&PATH=010414000275993a7a64824c998e52ef9486a2477fff0400&OFFSET=263&WIDTH=1&VALUE=00";
static const U16 bad_resp[]=L"GUID=00000000000000000000000000000000&NAME=0041006d00640053006500740075007000520050004c&PATH=010414000275993a7a64824c998e52ef9486a2477fff0400&OFFSET=263&WIDTH=1&VALUE=00";
static void copy(void*d,const void*s,N n){for(N i=0;i<n;i++)((U8*)d)[i]=((const U8*)s)[i];}
static void zero(void*d,N n){for(N i=0;i<n;i++)((U8*)d)[i]=0;}
static void put32(U8*p,U32 x){for(int i=0;i<4;i++)p[i]=(U8)(x>>(i*8));}
static STATUS API pool(U32 t,N n,void**p){return real_bs->alloc(t,n,p);}
static STATUS API freep(void*p){return real_bs->free(p);}
static STATUS API locate(const GUID*g,void*k,void**out){(void)k;locates++;if(!eq((const U8*)g,(const U8*)&apcb_guid,16)){bad++;return ERR(14);}*out=0;if(fault==2)return ERR(14);*out=apcb;return 0;}
static STATUS API setvar(const U16*name,const GUID*g,U32 attrs,N n,const void*p){writes++;if(!eq((const U8*)name,(const U8*)cbs_name,sizeof cbs_name)||!eq((const U8*)g,(const U8*)&variable_guid,16)||attrs!=7||n!=sizeof saved||p!=cache){bad++;return ERR(2);}if(fault==1)return ERR(8);copy(saved,p,n);return 0;}
static STATUS API getvar(const U16*name,const GUID*g,U32*a,N*n,void*p){(void)name;(void)g;(void)a;(void)n;(void)p;reads++;return ERR(14);}
static STATUS API acquire(void*p){if(p!=apcb)bad++;acquires++;return fault==3?ERR(7):0;}
static STATUS API clear(void*p,U8 pr){if(p!=apcb||pr!=3)bad++;clears++;return 0;}
static STATUS API flush(void*p){if(p!=apcb)bad++;flushes++;if(fault==4)return ERR(7);stored_fp=fp_attempt;return 0;}
static STATUS API release(void*p){if(p!=apcb)bad++;releases++;return 0;}
static STATUS put(void*p,U8 pr,U32 token,U32 val){if(p!=apcb||pr!=3)bad++;token_calls++;if(token==MCR){mcr_calls++;mcr_attempt=val;if(fault==5)return ERR(7);}if(token==FP)fp_attempt=val;return 0;}
static STATUS API set8(void*p,U8 pr,U32 token,U8 val){return put(p,pr,token,val);}
static STATUS API set16(void*p,U8 pr,U32 token,U16 val){return put(p,pr,token,val);}
static STATUS API set32(void*p,U8 pr,U32 token,U32 val){return put(p,pr,token,val);}
static STATUS API get32(void*p,U8*pr,U32 token,U32*val){if(p!=apcb||token!=FP||!pr||!val){bad++;return ERR(2);}*pr=3;*val=stored_fp;return 0;}
typedef STATUS(API *CBLOCK)(void*,const U16*,U8*,N*,const U16**);
static STATUS API cblock(void*p,const U16*r,U8*b,N*n,const U16**progress){if(p!=router||b!=cache||*n!=sizeof cache){bad++;return ERR(2);}return (*(CBLOCK*)((U8*)real_routing+0x20))(real_routing,r,b,n,progress);}
typedef STATUS(API *PAGEALLOC)(U32,U32,N,U64*);
typedef STATUS(API *PAGEFREE)(U64,N);
typedef STATUS(API *ROUTE_FN)(void*,const U16*,const U16**);
typedef void(API *DEFAULTS_FN)(U8*);
typedef U32(API *HASH_FN)(U8*);
typedef void(API *STARTUP_FN)(U8*);
static void reset_counts(void){fp_attempt=mcr_attempt=token_calls=writes=reads=locates=acquires=clears=flushes=releases=mcr_calls=bad=0;}
static int test(U32 f,int stale,int invalid){fault=f;reset_counts();copy(cache,initial,sizeof cache);copy(saved,initial,sizeof saved);stored_fp=u32(initial+8);if(stale)saved[0x11a]^=1;copy(before,saved,sizeof before);
 void *priv[8]={0};priv[0]=cache;priv[3]=router;const U16 *progress=0;
 STATUS s=((ROUTE_FN)(pe+0xb58))(&priv[4],invalid?bad_resp:resp,&progress);
 field("Fault: ",f);field("Stale: ",stale);field("Invalid header: ",invalid);field("Route status: ",s);field("  SetVariable calls: ",writes);field("  GetVariable calls: ",reads);field("  Locate APCB: ",locates);field("  Acquire: ",acquires);field("  Tokens: ",token_calls);field("  MCR token calls: ",mcr_calls);field("  Writeback: ",flushes);field("  release: ",releases);field("  saved MCR: ",saved[0x263]);N diff=0;for(N i=0;i<sizeof saved;i++)if(before[i]!=saved[i]){diff++;field("  changed saved offset: ",i);}field("  changed bytes: ",diff);field("  fingerprint stored unchanged: ",u32(saved+8)==u32(initial+8));field("  mock unexpected: ",bad);
 if(invalid)return s==ERR(14)&&!writes&&!reads&&!locates&&!diff&&!bad;
 if(f==1)return s==ERR(8)&&writes==1&&!reads&&!locates&&!diff&&!bad;
 if(s||writes!=1||reads||locates!=1||diff!=(N)(1+stale)||saved[0x263]!=0||bad)return 0;
 if(f==2)return !acquires&&!token_calls&&!flushes;
 if(f==3)return acquires==1&&!token_calls&&!flushes;
 return acquires==1&&clears==1&&flushes==1&&releases==1&&mcr_calls==1&&mcr_attempt==0&&fp_attempt==u32(initial+8);
}
static STATUS init_model(ST*st,U64*address,N*pages){con=st->out;real_bs=st->bs;
 if((N)(stock_pe_end-stock_pe)!=171808)return ERR(2);STATUS s=real_bs->locate(&routing_guid,0,&real_routing);if(s)return s;
 *pages=(0x29f20+4095)/4096;*address=0;s=(*(PAGEALLOC*)((U8*)real_bs+0x28))(0,1,*pages,address);field("Allocate LoaderCode: ",s);if(s)return s;pe=(U8*)(N)*address;zero(pe,*pages*4096);copy(pe,stock_pe,171808);*(U64*)(pe+0x7108)+=*address;
 fake_bs[0x40/8]=(void*)pool;fake_bs[0x48/8]=(void*)freep;fake_bs[0x140/8]=(void*)locate;fake_rt[0x48/8]=(void*)getvar;fake_rt[0x58/8]=(void*)setvar;*(void**)(pe+0x7f70)=fake_bs;*(void**)(pe+0x7f78)=fake_rt;
 apcb[0x60/8]=(void*)acquire;apcb[0xc0/8]=(void*)clear;apcb[0x08/8]=(void*)flush;apcb[0x68/8]=(void*)release;apcb[0x78/8]=(void*)set8;apcb[0x88/8]=(void*)set8;apcb[0x98/8]=(void*)set16;apcb[0xa8/8]=(void*)set32;apcb[0xa0/8]=(void*)get32;router[4]=(void*)cblock;
 ((DEFAULTS_FN)(pe+0x3e58))(initial);if(initial[0x263]!=255||u32(initial)!=0xfc4053aa||u32(initial+4)!=0x2d8)return ERR(2);initial[0x20]=0x43;initial[0x116]=1;initial[0x119]=1;initial[0x11a]=36;initial[0x11b]=0;put32(initial+8,((HASH_FN)(pe+0x5134))(initial));
 return 0;}
#ifndef INTEGRATED_FIXTURE
STATUS API efi_main(HANDLE image,ST*st){(void)image;U64 address;N pages;con=st->out;say("OVMF ORIGINAL ROUTE AND STARTUP FIXTURE ONLY\r\n");
 STATUS s=init_model(st,&address,&pages);if(s)return s;
 if(!test(0,0,0))return ERR(2);
 /* Normal route wrote old fingerprint into both stores. Simulate fresh boot
  * using that saved CBS payload and stored fingerprint, no other init path. */
 copy(cache,saved,sizeof cache);U32 newhash=((HASH_FN)(pe+0x5134))(cache);field("Fresh hash differs from saved: ",newhash!=u32(cache+8));if(newhash==u32(cache+8))return ERR(2);
 reset_counts();((STARTUP_FN)(pe+0x3c3c))(cache);field("Matching fingerprint startup token calls: ",token_calls);field("Matching fingerprint startup cache unchanged: ",eq(cache,saved,sizeof cache));if(token_calls||flushes||!eq(cache,saved,sizeof cache)||bad)return ERR(2);
 stored_fp^=1;reset_counts();((STARTUP_FN)(pe+0x3c3c))(cache);field("Mismatched fingerprint startup token calls: ",token_calls);field("Mismatched fingerprint startup updated: ",u32(cache+8)==newhash&&fp_attempt==newhash);if(!token_calls||flushes!=1||u32(cache+8)!=newhash||fp_attempt!=newhash||bad)return ERR(2);
 if(!test(0,1,0)||!test(1,0,0)||!test(2,0,0)||!test(3,0,0)||!test(4,0,0)||!test(5,0,0)||!test(0,0,1))return ERR(2);
 s=(*(PAGEFREE*)((U8*)real_bs+0x30))(address,pages);if(s)return s;say("ORIGINAL ROUTE AND STARTUP FIXTURE PASS\r\n");return 0;}
#endif

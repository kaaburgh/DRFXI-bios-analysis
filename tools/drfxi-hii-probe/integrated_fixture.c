/* OVMF ONLY: real HII Browser + original RouteConfig, synthetic ExtractConfig,
 * fully mocked AMD services. No real NVRAM writes or APCB access. */
#define INTEGRATED_FIXTURE
#include "route_fixture.c"
#ifndef FAULT
#define FAULT 0
#endif
static const U8 stock_package[]={
#include "stock.inc"
};
static const U8 *volatile keep_reloc=stock_package;
typedef STATUS(API *INSTALL)(HANDLE*, ...);
typedef STATUS(API *UNINSTALL)(HANDLE, ...);
typedef STATUS(API *NEW)(const DB*,const void*,HANDLE,HANDLE*);
typedef STATUS(API *REMOVE)(const DB*,HANDLE);
typedef STATUS(API *BLOCK)(void*,const U16*,const U8*,N,U16**,const U16**);
typedef STATUS(API *SEND)(void*,HANDLE*,N,const GUID*,U16,const void*,U32*);
typedef STATUS(API *AMD_CALLBACK)(void*,N,U16,U8,void*,U32*);
static void *priv[8];static U32 extracts,routes,callbacks,unexpected_actions,mcr_callbacks;
static const U16 hdr[]=L"GUID=0275993a7a64824c998e52ef9486a247&NAME=0041006d00640053006500740075007000520050004c&PATH=010414000275993a7a64824c998e52ef9486a2477fff0400";
static const U16 suffix[]=L"&OFFSET=0&WIDTH=6d5";
static N slen(const U16*s){N n=0;while(s[n])n++;return n;}
static int has(const U16*s,const U16*t){N n=slen(t);for(;*s;s++){N i=0;while(i<n&&s[i]&&s[i]==t[i])i++;if(i==n)return 1;}return 0;}
static STATUS API extract(void*p,const U16*request,const U16**progress,U16**results){
 extracts++;if(p!=&priv[4]||!progress||!results)return ERR(2);*progress=request;*results=0;
 copy(cache,saved,sizeof cache);
 const U16 *use=request?request:hdr;U16 *tmpbuf=0;N n=slen(use);
 if(!has(use,L"&OFFSET=")){N k=slen(suffix);STATUS s=real_bs->alloc(4,(n+k+1)*2,(void**)&tmpbuf);if(s)return s;for(N i=0;i<n;i++)tmpbuf[i]=use[i];for(N i=0;i<=k;i++)tmpbuf[n+i]=suffix[i];use=tmpbuf;}
 const U16 *tmp=0;STATUS s=(*(BLOCK*)((U8*)real_routing+0x18))(real_routing,use,cache,sizeof cache,results,&tmp);
 if(!s)*progress=request?request+slen(request):0;else if(!tmpbuf)*progress=tmp;
 if(tmpbuf)real_bs->free(tmpbuf);return s;
}
static STATUS API route(void*p,const U16*r,const U16**progress){routes++;if(p!=&priv[4]||!r||!progress)return ERR(2);
 field("Integrated response chars: ",slen(r));N n=slen(r),ranges=0;for(N i=0;i+8<=n;i++)if(r[i]=='&'&&r[i+1]=='O'&&r[i+2]=='F'&&r[i+3]=='F'&&r[i+4]=='S'&&r[i+5]=='E'&&r[i+6]=='T'&&r[i+7]=='=')ranges++;field("Integrated offset ranges: ",ranges);
 STATUS s=((ROUTE_FN)(pe+0xb58))(p,r,progress);field("Original route status: ",s);return s;
}
static STATUS API callback(void*p,N action,U16 q,U8 type,void*v,U32*req){callbacks++;
 if(q==0x9b)mcr_callbacks++;
 if(p!=&priv[4]||action!=5){unexpected_actions++;return ERR(3);}
 /* Reviewed original callback RVA 0xc60 returns EFI_SUCCESS immediately for
  * SUBMITTED (5); only invoke that branch. Other actions are rejected. */
 return ((AMD_CALLBACK)(pe+0xc60))(p,action,q,type,v,req);
}
STATUS API efi_main(HANDLE image,ST*st){(void)image;con=st->out;U64 address;N pages;say("OVMF INTEGRATED ORIGINAL ROUTE FIXTURE ONLY\r\n");field("Injected fault: ",FAULT);
 STATUS s=init_model(st,&address,&pages);if(s)return s;copy(cache,initial,sizeof cache);copy(saved,initial,sizeof saved);copy(before,saved,sizeof before);stored_fp=u32(initial+8);fault=FAULT;reset_counts();
 DB*db=0;void*browser=0;s=real_bs->locate(&db_guid,0,(void**)&db);if(s||!db)return ERR(14);s=real_bs->locate(&browser_guid,0,&browser);if(s||!browser)return ERR(14);
 priv[0]=cache;priv[3]=router;priv[4]=(void*)extract;priv[5]=(void*)route;priv[6]=(void*)callback;
 INSTALL install=*(INSTALL*)((U8*)real_bs+0x148);UNINSTALL uninstall=*(UNINSTALL*)((U8*)real_bs+0x150);HANDLE owner=0,hii=0;
 s=install(&owner,&dp_guid,owner_path,&access_guid,&priv[4],(void*)0);if(s)return s;s=((NEW)db->unused[0])(db,(const void*)keep_reloc,owner,&hii);if(s)return s;
 GUID target={0xc03209ed,0x5f4b,0x4631,{0xbd,3,0x8e,0xd6,0x27,0xcd,0x9d,0xaf}};U32 action=0;say("Entering SendForm\r\n");s=(*(SEND*)browser)(browser,&hii,1,&target,0x701b,0,&action);
 field("SendForm status: ",s);field("Action: ",action);field("Extract calls: ",extracts);field("Route calls: ",routes);field("Callback calls: ",callbacks);field("Unexpected callback actions: ",unexpected_actions);field("MCR callback calls: ",mcr_callbacks);
 field("Mock SetVariable calls: ",writes);field("Mock GetVariable calls: ",reads);field("Mock APCB MCR token calls: ",mcr_calls);field("Mock APCB MCR requested value: ",mcr_attempt);field("Mock APCB Writeback calls: ",flushes);field("Mock unexpected: ",bad);field("Saved MCR: ",saved[0x263]);N diff=0;for(N i=0;i<sizeof saved;i++)if(before[i]!=saved[i]){diff++;field("Changed offset: ",i);}field("Changed bytes: ",diff);field("Fingerprint unchanged: ",u32(saved+8)==u32(before+8));
 STATUS t=((REMOVE)db->unused[1])(db,hii);field("Remove package: ",t);if(t)return t;void *found=0;STATUS dp=real_bs->handle(owner,&dp_guid,&found);field("DP after remove status: ",dp);field("DP pointer match: ",found==owner_path);found=0;STATUS ac=real_bs->handle(owner,&access_guid,&found);field("Access after remove status: ",ac);field("Access pointer match: ",found==&priv[4]);
 t=uninstall(owner,&access_guid,&priv[4],(void*)0);field("Uninstall access: ",t);if(t)return t;t=uninstall(owner,&dp_guid,owner_path,(void*)0);field("Uninstall DP: ",t);if(t)return t;t=(*(PAGEFREE*)((U8*)real_bs+0x30))(address,pages);field("Free pages: ",t);if(t)return t;
 if(!s&&action==1&&extracts==1&&routes==1&&callbacks==21&&!unexpected_actions&&!mcr_callbacks&&writes==1&&!reads&&mcr_calls==1&&mcr_attempt==0&&flushes==1&&!bad&&saved[0x263]==0&&diff==1&&u32(saved+8)==u32(before+8)){say("INTEGRATED FIXTURE PASS\r\n");return 0;}
 say("INTEGRATED FIXTURE FAIL\r\n");return ERR(2);
}

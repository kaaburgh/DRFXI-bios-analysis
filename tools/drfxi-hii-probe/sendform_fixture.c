/* OVMF ONLY: stock HII package, synthetic ConfigAccess; no variable writes. */
#define efi_main probe_entry
#include "hii_probe.c"
#undef efi_main
#ifndef SELECTOR
#define SELECTOR 0x43
#endif
#ifndef FORM_ID
#define FORM_ID 0x701b
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
typedef STATUS(API *EXTRACT)(void*,const U16*,const U16**,U16**);
typedef STATUS(API *CONFIGBLOCK)(void*,const U16*,U8*,N*,const U16**);
typedef STATUS(API *ROUTE)(void*,const U16*,const U16**);
typedef STATUS(API *CALLBACK)(void*,N,U16,U8,void*,U32*);
static const GUID routing_guid={0x587e72d7,0xcc50,0x4f79,{0x82,9,0xca,0x29,0x1f,0xc1,0xa1,0x0f}};
static void *routing;static BS*boot;static U8 config[0x6d5];static U32 extracts,routes,callbacks;static U8 candidate[sizeof config];static const U16 hdr[] = L"GUID=0275993a7a64824c998e52ef9486a247&NAME=0041006d00640053006500740075007000520050004c&PATH=010414000275993a7a64824c998e52ef9486a2477fff0400";
static const U16 suffix[]=L"&OFFSET=0&WIDTH=6d5";
static N slen(const U16*s){N n=0;while(s[n])n++;return n;}
static int has(const U16*s,const U16*t){N n=slen(t);for(;*s;s++){N i=0;while(i<n&&s[i]&&s[i]==t[i])i++;if(i==n)return 1;}return 0;}
static STATUS API extract(void *p,const U16*request,const U16**progress,U16**results){(void)p;extracts++;if(!progress||!results)return ERR(2);*progress=request;*results=0;
 const U16 *use=request?request:hdr;U16 *copy=0;N n=slen(use);if(!has(use,L"&OFFSET=")){N k=slen(suffix);STATUS s=boot->alloc(4,(n+k+1)*2,(void**)&copy);if(s)return s;for(N i=0;i<n;i++)copy[i]=use[i];for(N i=0;i<=k;i++)copy[n+i]=suffix[i];use=copy;}
 const U16 *tmp=0;STATUS s=(*(BLOCK*)((U8*)routing+3*sizeof(void*)))(routing,use,config,sizeof config,results,&tmp);
 if(!s)*progress=request?request+slen(request):0;else if(!copy)*progress=tmp;
 if(copy)boot->free(copy);return s;}
static STATUS API route(void*p,const U16*r,const U16**progress){(void)p;routes++;if(!progress||!r)return ERR(2);*progress=r;
 say("Fixture RouteConfig request\r\n");field("  response chars: ",slen(r));N n=slen(r),ranges=0;for(N i=0;i+8<=n;i++)if(r[i]=='&'&&r[i+1]=='O'&&r[i+2]=='F'&&r[i+3]=='F'&&r[i+4]=='S'&&r[i+5]=='E'&&r[i+6]=='T'&&r[i+7]=='=')ranges++;field("  offset ranges: ",ranges);
 for(N i=0;i<sizeof config;i++)candidate[i]=config[i];N size=sizeof candidate;
 STATUS s=(*(CONFIGBLOCK*)((U8*)routing+4*sizeof(void*)))(routing,r,candidate,&size,progress);field("  ConfigToBlock status: ",s);field("  output size: ",size);if(s)return s;
 N changed=0;for(N i=0;i<sizeof config;i++)if(config[i]!=candidate[i]){changed++;if(changed<=16){field("  changed offset: ",i);field("  old: ",config[i]);field("  new: ",candidate[i]);}}field("  changed bytes: ",changed);
 #ifdef ACCEPT_ROUTE
 if(changed==1&&config[0x263]!=candidate[0x263]&&(candidate[0x263]==0||candidate[0x263]==1||candidate[0x263]==0xff)){config[0x263]=candidate[0x263];say("  synthetic RAM buffer committed\r\n");return 0;}
 #endif
 say("  rejected (no hardware writes)\r\n");return ERR(8);
}
static STATUS API callback(void*p,N action,U16 q,U8 type,void*v,U32*req){(void)p;(void)action;(void)q;(void)type;(void)v;callbacks++;if(req)*req=0;return ERR(3);}
static struct {EXTRACT extract;ROUTE route;CALLBACK callback;} access={extract,route,callback};
STATUS API efi_main(HANDLE image,ST*st){(void)image;con=st->out;boot=st->bs;
 say("OVMF SEND FORM FIXTURE ONLY\r\n");field("Selector: ",SELECTOR);field("Requested form: ",FORM_ID);
 DB*db=0;void*browser=0;STATUS s=boot->locate(&db_guid,0,(void**)&db);if(s||!db)return ERR(14);
 s=boot->locate(&browser_guid,0,&browser);if(s||!browser)return ERR(14);
 s=boot->locate(&routing_guid,0,&routing);if(s||!routing)return ERR(14);
 config[0]=0xaa;config[1]=0x53;config[2]=0x40;config[3]=0xfc;config[4]=0xd8;config[5]=2;config[0x20]=SELECTOR;config[0x263]=0xff;
 INSTALL install=*(INSTALL*)((U8*)boot+0x148);UNINSTALL uninstall=*(UNINSTALL*)((U8*)boot+0x150);
 HANDLE owner=0,hii=0;s=install(&owner,&dp_guid,owner_path,&access_guid,&access,(void*)0);field("Fixture install: ",s);if(s)return s;
 s=((NEW)db->unused[0])(db,(const void*)keep_reloc,owner,&hii);field("Fixture NewPackageList: ",s);if(s){uninstall(owner,&dp_guid,owner_path,&access_guid,&access,(void*)0);return s;}
 GUID target={0xc03209ed,0x5f4b,0x4631,{0xbd,3,0x8e,0xd6,0x27,0xcd,0x9d,0xaf}};U32 action=0;
 say("Entering SendForm\r\n");s=(*(SEND*)browser)(browser,&hii,1,&target,FORM_ID,0,&action);field("SendForm status: ",s);field("Action: ",action);field("Extract calls: ",extracts);field("Route calls: ",routes);field("Callback calls: ",callbacks);field("CBS MCR still: ",config[0x263]);
 STATUS t=((REMOVE)db->unused[1])(db,hii);field("Remove: ",t);if(t)return t;t=uninstall(owner,&dp_guid,owner_path,&access_guid,&access,(void*)0);field("Uninstall: ",t);say("FIXTURE END\r\n");return s?s:t;}

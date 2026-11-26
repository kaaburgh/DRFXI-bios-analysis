/* Native mock of protocol calls and EFI entry; NOT an OVMF/hardware test. */
#include "hii_probe.c"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static U8 *payload;static N payload_size;static int mode,read_count,exports,unexpected;
static int owner1,owner2,h1,h2,access,br;static DB db;
static STATUS API out(void *p,const U16*s){(void)p;while(*s)putchar(*s++);return 0;}
static STATUS API alloc(U32 type,N n,void**p){if(type!=4)unexpected++;*p=malloc(n);return *p?0:ERR(9);}
static STATUS API fr(void*p){free(p);return 0;}
static STATUS API locate(const GUID*g,void*k,void**p){(void)k;if(!memcmp(g,&db_guid,16))*p=&db;else if(!memcmp(g,&browser_guid,16))*p=&br;else{unexpected++;return ERR(14);}return 0;}
static STATUS API handle(HANDLE h,const GUID*g,void**p){if(!memcmp(g,&dp_guid,16)){if(h==&owner1&&mode!=2)*p=(void*)owner_path;else return ERR(14);}else if(!memcmp(g,&access_guid,16)&&h==&owner1)*p=&access;else return ERR(14);return 0;}
static STATUS API list(const DB*d,U8 type,const GUID*g,N*n,HANDLE*h){if(d!=&db||type||g)unexpected++;if(!h){*n=16;return TOO_SMALL;}if(*n<16)return TOO_SMALL;h[0]=&h1;h[1]=&h2;*n=16;return 0;}
static STATUS API owner(const DB*d,HANDLE h,HANDLE*o){if(d!=&db)unexpected++;*o=h==&h1?&owner1:&owner2;return 0;}
static STATUS API export(const DB*d,HANDLE h,N*n,void*b){if(d!=&db||h!=&h1)unexpected++;exports++;if(!b){*n=payload_size;return TOO_SMALL;}if(*n<payload_size)return TOO_SMALL;memcpy(b,payload,payload_size);*n=payload_size;if(mode==1)((U8*)b)[20+0xdc]^=1;return 0;}
static STATUS API get(const U16*name,const GUID*g,U32*a,N*n,void*b){(void)name;read_count++;if(!memcmp(g,&gate_guid,16)){if(*n!=1)unexpected++;if(mode==4||(mode==5&&read_count==3))return ERR(14);*(U8*)b=1;*a=0x26;return 0;}if(!memcmp(g,&variable_guid,16)){if(*n!=0x6d5)unexpected++;memset(b,0,*n);U8*q=b;q[0]=0xaa;q[1]=0x53;q[2]=0x40;q[3]=0xfc;q[4]=0xd8;q[5]=2;q[0x20]=0x43;q[0x263]=0xff;if(mode==3&&read_count==4)q[0x263]=1;*a=7;return 0;}unexpected++;return ERR(14);}
int main(int argc,char**argv){if(argc!=2)return 2;FILE*f=fopen(argv[1],"rb");if(!f)return 2;payload=malloc(MAX_LIST);payload_size=fread(payload,1,MAX_LIST,f);fclose(f);db.list=list;db.export=export;db.owner=owner;BS bs={0};bs.alloc=alloc;bs.free=fr;bs.locate=locate;bs.handle=handle;CONOUT c={0};c.output=out;RT rt={0};rt.get=get;ST st={0};st.out=&c;st.bs=&bs;st.rt=&rt;for(mode=0;mode<6;mode++){read_count=exports=unexpected=0;STATUS s=efi_main(0,&st);printf("mock mode %d status %llx exports %d reads %d unexpected %d\n",mode,(unsigned long long)s,exports,read_count,unexpected);if((s==0)!=(mode==0)||exports!=((mode==2||mode==4)?0:2)||read_count!=(mode==4?2:4)||unexpected)return 1;}free(payload);return 0;}

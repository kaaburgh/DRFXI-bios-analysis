#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "apcb_inventory.c"
static U8 image[0xe000], original[0xe000];static IMAGE im;static int scenario;static unsigned read_count;
static int apcb_handle, image_handle, image_handle2;
static void put64(U8*p,U64 v){memcpy(p,&v,8);}
static STATUS API output(void*c,const U16*s){(void)c;while(*s)putchar((char)*s++);return 0;}
static STATUS API freepool(void*p){free(p);return 0;}
static STATUS API list(U32 type,const GUID*g,void*k,N*n,HANDLE**h){assert(type==2&&!k);if(eq(g,&apcb_guid,16)){if(scenario==1)return ERR(14);*n=scenario==2?2:1;*h=calloc(*n,sizeof(HANDLE));(*h)[0]=&apcb_handle;return 0;}assert(eq(g,&image_guid,16));*n=scenario==6?2:1;*h=calloc(*n,sizeof(HANDLE));(*h)[0]=&image_handle;if(*n==2)(*h)[1]=&image_handle2;return 0;}
static STATUS API handle(HANDLE h,const GUID*g,void**p){if(h==&apcb_handle){assert(eq(g,&apcb_guid,16));*p=image+0xa160+(scenario==3?8:0);return 0;}assert(h==&image_handle||h==&image_handle2);assert(eq(g,&image_guid,16));*p=&im;return 0;}
static STATUS API getvar(const U16*name,const GUID*g,U32*a,N*n,void*p){read_count++;if(eq(g,&gate_guid,16)){assert(*n==1&&eq(name,gate_name,sizeof gate_name));*(U8*)p=1;*a=0x26;return 0;}assert(eq(g,&cbs_guid,16)&&*n==0x6d5&&eq(name,cbs_name,sizeof cbs_name));memset(p,0,*n);put64(p,0x000002d8fc4053aaULL);((U8*)p)[0x263]=scenario==9&&read_count==4?1:0xff;*a=7;return 0;}
int main(int argc,char**argv){assert(argc==2);FILE*f=fopen(argv[1],"rb");assert(f&&fread(original,1,56576,f)==56576);fclose(f);im.base=image;im.size=0xdd00;CONOUT out={0,output};BS bs={0};bs.free=freepool;bs.handle=handle;bs.list=list;RT rt={0};rt.get=getvar;ST st={0};st.out=&out;st.bs=&bs;st.rt=&rt;for(scenario=0;scenario<12;scenario++){memcpy(image,original,sizeof image);for(N i=0;i<27;i++)put64(image+0xa168+8*i,(N)image+methods[i]);image[0xcfa8]=scenario==7?0:scenario==8?2:1;image[0xd074]=0;im.size=scenario==5?0x100:0xdd00;if(scenario==4)image[0x280]^=1;if(scenario==10)image[0xa168]^=1;if(scenario==11)image[0xd074]=2;read_count=0;printf("CASE %d\n",scenario);STATUS s=efi_main(0,&st);assert(read_count==4);assert((s==0)==(scenario==0||scenario==7));printf("PASS %d\n",scenario);}return 0;}

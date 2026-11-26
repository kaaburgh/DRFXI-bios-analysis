/* VM ONLY: real OVMF HII protocols, synthetic local runtime-service input.
 * Does not replace global RuntimeServices or call SetVariable. */
#define efi_main probe_entry
#include "hii_probe.c"
#undef efi_main
static const U8 stock_package[]={
#include "stock.inc"
};
static const U8 *volatile keep_reloc=stock_package;
typedef STATUS(API *INSTALL)(HANDLE*, ...);
typedef STATUS(API *UNINSTALL)(HANDLE, ...);
typedef STATUS(API *NEW)(const DB*,const void*,HANDLE,HANDLE*);
typedef STATUS(API *REMOVE)(const DB*,HANDLE);
static STATUS API unsupported(void *p, ...){(void)p;return ERR(3);}
static void *access[3]={(void*)unsupported,(void*)unsupported,(void*)unsupported};
static RT rt_fake; static ST st_local;
static STATUS API fixture_get(const U16*name,const GUID*g,U32*a,N*n,void*b){
 if(eq((const U8*)g,(const U8*)&gate_guid,16)&&eq((const U8*)name,(const U8*)gate_name,sizeof gate_name)){
  if(*n<1)return TOO_SMALL;*(U8*)b=1;*a=0x26;*n=1;return 0;
 }
 if(eq((const U8*)g,(const U8*)&variable_guid,16)&&eq((const U8*)name,(const U8*)cbs_name,sizeof cbs_name)){
  if(*n<0x6d5)return TOO_SMALL;U8*q=b;for(N i=0;i<0x6d5;i++)q[i]=0;
  q[0]=0xaa;q[1]=0x53;q[2]=0x40;q[3]=0xfc;q[4]=0xd8;q[5]=2;q[0x20]=0x43;q[0x263]=0xff;*a=7;*n=0x6d5;return 0;
 }return ERR(14);
}
STATUS API efi_main(HANDLE image,ST*st){
 con=st->out;say("OVMF FIXTURE ONLY: real HII, simulated variable reads\r\n");
 DB *db=0;STATUS s=st->bs->locate(&db_guid,0,(void**)&db);if(s||!db)return ERR(14);
 INSTALL install=*(INSTALL*)((U8*)st->bs+0x148);UNINSTALL uninstall=*(UNINSTALL*)((U8*)st->bs+0x150);
 HANDLE owner=0,hii=0;s=install(&owner,&dp_guid,owner_path,&access_guid,access,(void*)0);field("Fixture install: ",s);if(s)return s;
 s=((NEW)db->unused[0])(db,(const void*)keep_reloc,owner,&hii);field("Fixture NewPackageList: ",s);if(s){uninstall(owner,&dp_guid,owner_path,&access_guid,access,(void*)0);return s;}
 st_local.out=st->out;st_local.bs=st->bs;st_local.rt=&rt_fake;rt_fake.get=fixture_get;
 STATUS test=probe_entry(image,&st_local);field("Fixture probe result: ",test);
 s=((REMOVE)db->unused[1])(db,hii);field("Fixture remove: ",s);if(s)return s;
 s=uninstall(owner,&dp_guid,owner_path,&access_guid,access,(void*)0);field("Fixture uninstall: ",s);
 if(!test&&!s)say("OVMF FIXTURE PASS\r\n");return test?test:s;
}

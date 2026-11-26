/* VM ONLY. Installs synthetic protocols; never starts original AMD code. */
#define efi_main production_main
#include "apcb_inventory.c"
#undef efi_main
static U8 fake_image[0xe000]={
#include "apcb_stock.inc"
};
static IMAGE desc;
typedef STATUS(API *INSTALL)(HANDLE*,const GUID*,U32,void*);
typedef STATUS(API *UNINSTALL)(HANDLE,const GUID*,void*);
static void put64(U8*p,U64 n){for(int i=0;i<8;i++)p[i]=(U8)(n>>(i*8));}
STATUS API efi_main(HANDLE self,ST*st){(void)self;con=st->out;say("INVENTORY VM FIXTURE ONLY\r\n");BS*bs=st->bs;INSTALL install=(INSTALL)bs->mid[6];UNINSTALL uninstall=(UNINSTALL)bs->mid[8];HANDLE h=0;desc.revision=0x1000;desc.base=fake_image;desc.size=0xdd00;desc.system=st;for(N i=0;i<27;i++)put64(fake_image+0xa168+8*i,(N)fake_image+methods[i]);fake_image[0xcfa8]=1;fake_image[0xd074]=0;
 STATUS s=install(&h,&image_guid,0,&desc);field("Install synthetic image: ",s);if(s)return s;s=install(&h,&apcb_guid,0,fake_image+0xa160);field("Install synthetic APCB: ",s);if(s){uninstall(h,&image_guid,&desc);return s;}
 s=inventory(bs);field("Fixture inventory result: ",s);STATUS a=uninstall(h,&apcb_guid,fake_image+0xa160);STATUS b=uninstall(h,&image_guid,&desc);field("Cleanup APCB: ",a);field("Cleanup image: ",b);if(s||a||b)return ERR(2);say("INVENTORY POSITIVE VM PASS\r\n");return 0;}

#define _GNU_SOURCE
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#define ABI __attribute__((ms_abi))
#define ERR(n) (0x8000000000000000ULL|(n))
static uint8_t *dxe,*smm,*blocks[3];
static unsigned shadows, transports, validations, debug_errors, mode, no_instance1;
static uint8_t msg[56], scratch[0x1400], permission[5];
static uint8_t fake_bs[0x148], pcd[0x28], comm[8], validator[8];
static uint8_t *readfile(const char *p,size_t *n){FILE*f=fopen(p,"rb");assert(f);assert(!fseek(f,0,SEEK_END));*n=ftell(f);rewind(f);uint8_t*b=malloc(*n);assert(b&&fread(b,1,*n,f)==*n);fclose(f);return b;}
static void put16(void*p,uint16_t x){memcpy(p,&x,2);}static void put32(void*p,uint32_t x){memcpy(p,&x,4);}static void put64(void*p,uint64_t x){memcpy(p,&x,8);}static uint32_t get32(void*p){uint32_t x;memcpy(&x,p,4);return x;}static uint64_t get64(void*p){uint64_t x;memcpy(&x,p,8);return x;}
static void ptr(void*p,const void*x){put64(p,(uintptr_t)x);}static void jump(uint8_t*p,const void*x){p[0]=0x48;p[1]=0xb8;ptr(p+2,x);p[10]=0xff;p[11]=0xe0;}
static uint8_t *ABI shadow(uint32_t *capacity){uint8_t p=smm[0xb335];assert(p>=1&&p<=6);shadows++;*capacity=0x4000;if(no_instance1&&smm[0xb336]==0x60&&smm[0xb334]==1)return NULL;return smm[0xb336]==0x68?blocks[0]:smm[0xb334]==0?blocks[1]:blocks[2];}
static uint64_t ABI validate(void*p,uint64_t n){assert(p==msg+24&&n==32);validations++;return mode==1?ERR(15):0;}
static uint64_t ABI transport(void*self,void*p,uint64_t*n){assert(self==comm&&p==msg&&*n==56);transports++;assert(get64(msg+16)==56);assert(get32(msg+24)==0xa1cb0005);assert(get32(msg+44)==0xfedb01f8);if(mode==2||mode==3)return ERR(7);uint64_t len=32;typedef uint64_t(ABI *handler)(void*,void*,void*,uint64_t*);return ((handler)(smm+0x2d3c))(0,0,msg+24,&len);}
static uint64_t ABI get64_pcd(const void*g,uintptr_t id){assert(!memcmp(g,dxe+0xa0e0,16)&&id==0x27001);return (uintptr_t)msg;}
static uint64_t ABI locate(const void*g,void*k,void**out){(void)k;assert(!memcmp(g,dxe+0xa000,16));*out=comm;return 0;}
static void ABI debug(uint32_t code){(void)code;debug_errors++;}
static void run(const char*name,unsigned gate,unsigned locked,unsigned perm,unsigned testmode,uint64_t expected,unsigned p,unsigned v,unsigned count,unsigned dbg){smm[0xe069]=gate;smm[0xe068]=locked;put32(permission,0xfedb01f8);permission[4]=perm;ptr(smm+0xe060,permission);put32(smm+0xe06c,1);mode=testmode;if(testmode!=3)memset(msg,0,sizeof msg);shadows=transports=validations=debug_errors=0;uint8_t priority=0xcc,value=0xcc;typedef uint64_t(ABI *getbool)(void*,uint8_t*,uint32_t,uint8_t*);uint64_t s=((getbool)(dxe+0xdec))(dxe+0xa160,&priority,0xfedb01f8,&value);printf("%s: status=%016lx priority=%02x value=%02x shadows=%u transport=%u validate=%u debug=%u\n",name,s,priority,value,shadows,transports,validations,debug_errors);assert(s==expected&&priority==p&&value==v&&shadows==count&&transports==1&&validations==(testmode>=2?0:1)&&debug_errors==dbg);}
int main(int argc,char**argv){assert(argc==6);size_t n;uint8_t *b=readfile(argv[1],&n);assert(n==56576);dxe=mmap(0,0xe000,7,MAP_PRIVATE|MAP_ANONYMOUS,-1,0);assert(dxe!=MAP_FAILED);memcpy(dxe,b,n);free(b);b=readfile(argv[2],&n);assert(n==0xd800);smm=mmap(0,0x12000,7,MAP_PRIVATE|MAP_ANONYMOUS,-1,0);assert(smm!=MAP_FAILED);memcpy(smm,b,0x400);memcpy(smm+0x1000,b+0x400,0x9200);memcpy(smm+0xb000,b+0x9600,0x3400);memcpy(smm+0xf000,b+0xca00,0x600);free(b);for(int i=0;i<3;i++)blocks[i]=readfile(argv[3+i],&n);
 /* All replacements are in private Linux mappings. No firmware services called. */
 dxe[0xcfa8]=1;ptr(dxe+0xcfb8,fake_bs);ptr(dxe+0xcfd0,pcd);ptr(fake_bs+0x140,locate);ptr(pcd+0x20,get64_pcd);ptr(comm,transport);jump(dxe+0x239c,debug);
 smm[0x3598]=0xc3;jump(smm+0x4e20,shadow);ptr(smm+0xe148,scratch);ptr(smm+0xe0f8,validator);ptr(validator,validate);put16(smm+0xe13c,1);
 run("stock unrestricted",0,1,0,0,0,6,1,6,0);
 run("permission read",1,1,1,0,0,6,1,6,0);
 run("permission denied",1,1,2,0,ERR(15),0xcc,0xcc,0,0);
 run("invalid communication buffer",0,1,0,1,0,0,0,0,1);
 run("transport failure",0,1,0,2,0,0,0,0,1);
 run("successful read before stale failure",0,1,0,0,0,6,1,6,0);
 run("transport failure with retained response",0,1,0,3,0,6,1,0,1);
 no_instance1=1;
 run("stock with absent 60/1 descriptor",0,1,0,0,0,6,1,6,0);
 return 0;}

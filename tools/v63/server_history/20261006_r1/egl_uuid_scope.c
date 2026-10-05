/* Process-local EGL selection. No system driver or other process is modified.
 * NV_device_cuda maps EGL devices to CUDA handles; verify the exact UUID before
 * returning a platform-device display. Failure exits, never picks default GPU.
 * No system headers needed: these declarations use the Linux x86-64 ABI.
 */
typedef void *Ptr;
typedef unsigned int Bool;
typedef long Attr;
extern Ptr dlvsym(Ptr, const char *, const char *);
extern Ptr dlopen(const char *, int);
extern char *getenv(const char *);
extern int strcmp(const char *, const char *);
extern unsigned long strlen(const char *);
extern long write(int, const void *, unsigned long);
extern void _exit(int);
typedef Ptr (*Dlsym)(Ptr, const char *);
static Dlsym real_sym(void) {
  return (Dlsym)dlvsym((Ptr)-1L, "dlsym", "GLIBC_2.2.5");
}
static void fail(const char *message) {
  write(2, message, strlen(message));
  _exit(87);
}
static int hex(char c) {
  if (c >= '0' && c <= '9') return c-'0';
  if (c >= 'a' && c <= 'f') return c-'a'+10;
  if (c >= 'A' && c <= 'F') return c-'A'+10;
  return -1;
}
static Ptr scoped_display(Ptr native_display) {
  static Ptr display = 0;
  if (display) return display;
  if (native_display) fail("V63_EGL_REFUSE_NATIVE_DISPLAY\n");
  const char *expected = getenv("V63_GPU_UUID");
  if (!expected || strlen(expected) != 40) fail("V63_EGL_UUID_MISSING\n");
  unsigned char wanted[16]; int j=0, half=-1;
  for (int i=4; expected[i]; ++i) {
    if (expected[i]=='-') continue;
    int h=hex(expected[i]);
    if (h<0) fail("V63_EGL_BAD_UUID\n");
    if (half<0) half=h;
    else { if(j>=16) fail("V63_EGL_BAD_UUID\n"); wanted[j++]=half*16+h; half=-1; }
  }
  if(j!=16 || half>=0) fail("V63_EGL_BAD_UUID\n");
  Dlsym sym=real_sym();
  Ptr egl=dlopen("libEGL.so.1", 2);
  Ptr cuda=dlopen("libcuda.so.1", 2);
  if(!egl || !cuda) fail("V63_EGL_DRIVER_LOAD_FAIL\n");
  Ptr (*getproc)(const char *)=(Ptr (*)(const char *))sym(egl,"eglGetProcAddress");
  int (*init)(unsigned int)=(int (*)(unsigned int))sym(cuda,"cuInit");
  int (*uuid)(Ptr,int)=(int (*)(Ptr,int))sym(cuda,"cuDeviceGetUuid_v2");
  if(!uuid) uuid=(int (*)(Ptr,int))sym(cuda,"cuDeviceGetUuid");
  if(!getproc || !init || !uuid || init(0)) fail("V63_EGL_CUDA_QUERY_FAIL\n");
  Bool (*query)(int,Ptr*,int*)=(Bool (*)(int,Ptr*,int*))getproc("eglQueryDevicesEXT");
  Bool (*attribute)(Ptr,int,Attr*)=(Bool (*)(Ptr,int,Attr*))getproc("eglQueryDeviceAttribEXT");
  Ptr (*platform)(unsigned int,Ptr,const int*)=(Ptr (*)(unsigned int,Ptr,const int*))getproc("eglGetPlatformDisplayEXT");
  if(!query || !attribute || !platform) fail("V63_EGL_EXTENSIONS_MISSING\n");
  Ptr devices[32]; int count=0;
  if(!query(32,devices,&count)) fail("V63_EGL_ENUMERATION_FAIL\n");
  Ptr chosen=0;
  for(int i=0;i<count;++i) {
    Attr device=-1; unsigned char actual[16];
    if(!attribute(devices[i],0x323A,&device) || uuid(actual,(int)device)) continue;
    int equal=1;
    for(int k=0;k<16;++k) if(actual[k]!=wanted[k]) equal=0;
    if(equal) { if(chosen) fail("V63_EGL_AMBIGUOUS_UUID\n"); chosen=devices[i]; }
  }
  if(!chosen) fail("V63_EGL_UUID_NOT_FOUND\n");
  display=platform(0x313F,chosen,0);
  if(!display) fail("V63_EGL_DISPLAY_FAIL\n");
  write(2,"V63_EGL_SELECTED_VERIFIED_UUID ",31);
  write(2,expected,strlen(expected)); write(2,"\n",1);
  return display;
}
Ptr eglGetDisplay(Ptr native_display) { return scoped_display(native_display); }
/* libepoxy resolves EGL using handle-specific dlsym; intercept only this one
 * entry point. Every other symbol uses the original glibc resolver. */
Ptr dlsym(Ptr handle,const char *name) {
  if(name && !strcmp(name,"eglGetDisplay")) return (Ptr)&eglGetDisplay;
  return real_sym()(handle,name);
}

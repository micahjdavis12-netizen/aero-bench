/* Native ARM64 launcher: reuse the runtime in the already-installed full app. */
extern int _NSGetExecutablePath(char *, unsigned int *);
extern int execv(const char *, char *const []);
extern int setenv(const char *, const char *, int);
extern int unsetenv(const char *);
extern int access(const char *, int);
extern char *getenv(const char *);
extern int system(const char *);
static int cat(char *d,unsigned int cap,const char *s){unsigned int n=0,i=0;while(n<cap&&d[n])n++;while(s[i]){if(n+1>=cap)return -1;d[n++]=s[i++];}d[n]=0;return 0;}
int main(void){
 char base[8192]={0},script[8192]={0},python[8192]={0};unsigned int size=sizeof(base),i=0;
 if(_NSGetExecutablePath(base,&size))return 1;
 while(base[i])i++;while(i&&base[i-1]!='/')i--;if(!i)return 1;base[i]=0;
 if(cat(script,sizeof(script),base)||cat(script,sizeof(script),"../Resources/bootstrap.py"))return 1;
 cat(python,sizeof(python),"/Applications/AeroBench.app/Contents/Resources/runtime/bin/python3.12");
 if(access(python,1)){
  python[0]=0;char *home=getenv("HOME");if(!home||cat(python,sizeof(python),home)||cat(python,sizeof(python),"/Applications/AeroBench.app/Contents/Resources/runtime/bin/python3.12"))return 1;
  if(access(python,1)){system("/usr/bin/osascript -e 'display dialog \"Keep the full AeroBench.app in Applications. Connect reuses its installed engine; no separate Python installation is needed.\" buttons {\"OK\"}'");return 1;}
 }
 unsetenv("PYTHONHOME");unsetenv("PYTHONPATH");setenv("PYTHONNOUSERSITE","1",1);setenv("PYTHONDONTWRITEBYTECODE","1",1);
 char *args[]={python,script,0};execv(python,args);return 1;
}

"""Small, fixed GitHub update bootstrap using the runtime already installed with AeroBench.

Updates are trusted code from one fixed user-owned repository over verified HTTPS.
Payloads are pinned to an immutable commit and individually SHA-256 checked.
No source URL from the manifest is ever followed. Private data is not an update target.
"""
from pathlib import Path,PurePosixPath
import concurrent.futures,contextlib,fcntl,hashlib,importlib.util,json,os,re,shutil,ssl,sys,tempfile,time,urllib.request
REPO='micahjdavis12-netizen/aero-bench'
MANIFEST_URL='https://raw.githubusercontent.com/'+REPO+'/main/updates/stable.json'
HERE=Path(__file__).resolve().parent
HOME=Path.home()/'Library/AeroBench'
ALLOWED={'auth.py','bootstrap_assets.py','cfd.py','mesh_exports.py','models.py','postprocess.py','runner.py','server.py','verify_results.py','project.json','desktop/mac_main.py','web/app.js','web/connection-ui.js','web/transport.js','web/index.html','web/style.css','web/favicon.svg'}
LIMIT=2*1024*1024

def message(text):
 import subprocess
 subprocess.run(['/usr/bin/osascript','-e','display dialog '+json.dumps(text)+' with title "Aero Bench Connect" buttons {"OK"} default button "OK"'],capture_output=True)

def validate_manifest(manifest):
 if manifest.get('format')!=1:raise ValueError('Unsupported update format.')
 if not re.fullmatch(r'\d+\.\d+\.\d+',manifest.get('version','')):raise ValueError('Invalid update version.')
 if not re.fullmatch(r'[0-9a-f]{40}',manifest.get('commit','')):raise ValueError('Update is not pinned to a commit.')
 files=manifest.get('files',{})
 if set(files)!=ALLOWED:raise ValueError('Update must contain exactly the allowed app-code files.')
 total=0
 for name,item in files.items():
  path=PurePosixPath(name)
  if path.is_absolute() or '..' in path.parts:raise ValueError('Unsafe update path.')
  if not re.fullmatch(r'[0-9a-f]{64}',item.get('sha256','')):raise ValueError('Invalid file checksum.')
  size=item.get('bytes')
  if not isinstance(size,int) or not 0<size<=LIMIT:raise ValueError('Invalid update size.')
  total+=size
 if total>LIMIT:raise ValueError('The code update exceeds its size limit.')
 return manifest

def fetch(url,limit,context):
 req=urllib.request.Request(url,headers={'User-Agent':'AeroBench-Connect/0.3'})
 with urllib.request.urlopen(req,timeout=30,context=context) as response:
  final=response.geturl()
  if not final.startswith('https://raw.githubusercontent.com/'+REPO+'/'):raise ValueError('Unexpected update redirect.')
  data=response.read(limit+1)
 if len(data)>limit:raise ValueError('Update download is too large.')
 return data

def verify_release(path,manifest):
 for name,item in manifest['files'].items():
  data=(path/name).read_bytes()
  if len(data)!=item['bytes'] or hashlib.sha256(data).hexdigest()!=item['sha256']:raise ValueError('Update checksum mismatch: '+name)
 return path

def obtain_release(home,context,fetcher=fetch):
 home.mkdir(parents=True,exist_ok=True);releases=home/'releases';releases.mkdir(exist_ok=True)
 current=home/'current-update.json'
 try:
  manifest=validate_manifest(json.loads(fetcher(MANIFEST_URL,65536,context)))
  destination=releases/(manifest['version']+'-'+manifest['commit'][:12])
  if destination.exists():verify_release(destination,manifest)
  else:
   with tempfile.TemporaryDirectory(prefix='.download-',dir=releases) as tmp:
    stage=Path(tmp)
    def download(entry):
     name,item=entry;url='https://raw.githubusercontent.com/'+REPO+'/'+manifest['commit']+'/'+name
     data=fetcher(url,item['bytes'],context)
     if len(data)!=item['bytes'] or hashlib.sha256(data).hexdigest()!=item['sha256']:raise ValueError('Update checksum mismatch: '+name)
     target=stage/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:list(pool.map(download,manifest['files'].items()))
    verify_release(stage,manifest);stage.rename(destination)
  temp=current.with_suffix('.tmp');temp.write_text(json.dumps(manifest));temp.chmod(0o600);temp.replace(current)
  return destination,manifest,None
 except Exception as error:
  if not current.exists():raise RuntimeError('The first update could not be downloaded. Check your internet connection and reopen Connect.\n\n'+str(error)) from error
  manifest=validate_manifest(json.loads(current.read_text()))
  destination=releases/(manifest['version']+'-'+manifest['commit'][:12]);verify_release(destination,manifest)
  return destination,manifest,str(error)

def installed_resources():
 candidates=[Path('/Applications/AeroBench.app/Contents/Resources'),Path.home()/'Applications/AeroBench.app/Contents/Resources']
 for path in candidates:
  if (path/'runtime/bin/python3.12').exists() and (path/'engine/OpenFOAM-v2412.app').exists():return path
 raise RuntimeError('Keep the full AeroBench.app in Applications. Connect reuses its installed solver and runtime.')

def main():
 HOME.mkdir(parents=True,exist_ok=True)
 lock=open(HOME/'update.lock','a')
 try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 except BlockingIOError:message('Aero Bench Connect is already checking updates or starting. Please wait for its browser window.');return
 resources=installed_resources()
 ca=HERE/'cacert.pem';os.environ['SSL_CERT_FILE']=str(ca)
 context=ssl.create_default_context(cafile=str(ca))
 release,manifest,error=obtain_release(HOME,context)
 if error:message('Updates are unavailable right now. Opening the previously verified code already on your Mac.\n\n'+error[:250])
 os.environ.update(AERO_RESOURCES=str(resources),AERO_SOURCE_ROOT=str(release),AERO_UPDATE_BUILD=manifest['version']+'+'+manifest['commit'][:12],AERO_HOSTED_UI='1',PYTHONNOUSERSITE='1')
 sys.path.insert(0,str(release))
 spec=importlib.util.spec_from_file_location('aero_desktop',release/'desktop/mac_main.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
 module.main()

if __name__=='__main__':
 try:main()
 except Exception as error:
  logs=Path.home()/'Library/Logs/AeroBench';logs.mkdir(parents=True,exist_ok=True)
  with open(logs/'updates.log','a') as f:f.write(time.strftime('%Y-%m-%d %H:%M:%S')+' '+repr(error)+'\n')
  message(str(error)+'\n\nDetails: ~/Library/Logs/AeroBench/updates.log')

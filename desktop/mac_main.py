"""Aero Bench's bundled Mac app controller; no global installs or shell setup."""
from pathlib import Path
from urllib.parse import urlencode
import contextlib,json,os,platform,re,shutil,socket,subprocess,sys,time,urllib.request
RES=Path(os.environ.get('AERO_RESOURCES',str(Path(__file__).resolve().parent)))
SOURCE=Path(os.environ.get('AERO_SOURCE_ROOT',str(RES/'project')))
HOME=Path.home()/'Library/AeroBench'
APP=HOME/'app'
LOGS=Path.home()/'Library/Logs/AeroBench'
VERSION=os.environ.get("AERO_UPDATE_BUILD","0.3.0")
PORT=8765
BASE=f'http://127.0.0.1:{PORT}'
PYTHON=RES/'runtime/bin/python3'


def dialog(message,buttons=('OK',),title='Aero Bench'):
    script='display dialog '+json.dumps(message)+' with title '+json.dumps(title)+' buttons {'+','.join(json.dumps(b) for b in buttons)+'} default button '+json.dumps(buttons[-1])
    r=subprocess.run(['/usr/bin/osascript','-e',script],capture_output=True,text=True)
    if r.returncode:return None
    return r.stdout.strip().split('button returned:')[-1].strip()


def open_url(url):subprocess.Popen(['/usr/bin/open',url])


def health():
    try:
        with urllib.request.urlopen(BASE+'/api/health',timeout=1) as r:return json.load(r).get('app')=='Aero Bench'
    except (OSError,ValueError):return False


def settings():
    sys.path.insert(0,str(APP))
    from auth import access_key
    return access_key()


def link(address,key):return address+'/#'+urlencode({'backend':address,'key':key})


def copy_project():
    APP.mkdir(parents=True,exist_ok=True)
    for name in ['baseline-assets.zip','assets-manifest.json','BASELINE-RESULTS.md']:
        original=RES/'project'/name;dest=APP/name
        if not dest.exists() and original.exists():shutil.copy2(original,dest)
    for source in SOURCE.rglob('*'):
        rel=source.relative_to(SOURCE);dest=APP/rel
        if source.is_dir():dest.mkdir(parents=True,exist_ok=True)
        elif not dest.exists() or source.stat().st_size!=dest.stat().st_size or source.read_bytes()!=dest.read_bytes():
            dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,dest)
    sys.path.insert(0,str(APP))
    from bootstrap_assets import ensure_assets
    ensure_assets(APP)


def engine_environment():
    env=os.environ.copy();env['AERO_ENGINE_BUILD']='Native OpenFOAM2412.app 2.1.2';env['AERO_NATIVE_MAC']='1';env['AERO_WORKERS']='4';env['AERO_PORT']=str(PORT)
    env['PYTHONNOUSERSITE']='1';env['OMP_NUM_THREADS']='1';env['MPLCONFIGDIR']=str(HOME/'cache/matplotlib')
    wrapper=RES/'engine/OpenFOAM-v2412.app/Contents/Resources/etc/openfoam'
    # OpenFOAM.app mounts its included, case-sensitive disk and sources its own environment.
    check=subprocess.run([str(wrapper),str(PYTHON),'-c','import json,os;print("AERO_ENV="+json.dumps(dict(os.environ)))'],capture_output=True,text=True,timeout=90,env=env)
    if check.returncode:raise RuntimeError('The bundled OpenFOAM environment did not start. '+check.stderr[-1200:])
    lines=[line[9:] for line in check.stdout.splitlines() if line.startswith('AERO_ENV=')]
    if not lines:raise RuntimeError('The bundled solver did not return its environment.')
    env.update(json.loads(lines[-1]));env['AERO_NATIVE_READY']='1'
    # Native binaries and the Python scientific modules must load before runs are enabled.
    for tool in ['blockMesh','snappyHexMesh','checkMesh','decomposePar','simpleFoam','reconstructPar']:
        executable=shutil.which(tool,path=env.get('PATH',''))
        if not executable:raise RuntimeError('Bundled solver command missing: '+tool)
        probe=subprocess.run([executable,'-help'],capture_output=True,text=True,env=env,timeout=30)
        if probe.returncode:raise RuntimeError(tool+' could not load. '+probe.stderr[-500:])
    modules=subprocess.run([str(PYTHON),'-c','import numpy,scipy,vtk;from vtk.util.numpy_support import vtk_to_numpy'],capture_output=True,text=True,env=env,timeout=45)
    if modules.returncode:raise RuntimeError('A bundled model-processing library could not load. '+modules.stderr[-700:])
    if not (shutil.which('mpirun',path=env['PATH']) or shutil.which('mpiexec',path=env['PATH'])):raise RuntimeError('Bundled MPI launcher missing.')
    return env


def start_backend():
    copy_project();LOGS.mkdir(parents=True,exist_ok=True)
    diagnostics={'architecture':platform.machine(),'macos':platform.mac_ver()[0],'native_engine':'OpenFOAM2412.app 2.1.2','baseline_engine':'Linux OpenFOAM2412 patch260127','native_solve_verified_on_this_mac':False}
    try:
        env=engine_environment();diagnostics['runtime_checks']='passed'
    except Exception as error:
        env=os.environ.copy();env.update(AERO_NATIVE_MAC='1',AERO_NATIVE_READY='0',AERO_ENGINE_ERROR=str(error),PYTHONNOUSERSITE='1')
        diagnostics.update(runtime_checks='failed',error=str(error))
    env['AERO_CLOUDFLARED']=str(RES/'bin/cloudflared')
    env['AERO_DESKTOP_BUILD']=VERSION
    private=APP/'data/private';private.mkdir(parents=True,exist_ok=True)
    diagnostic=private/'mac-diagnostics.json';diagnostic.write_text(json.dumps(diagnostics,indent=2));diagnostic.chmod(0o600)
    with open(LOGS/'backend.log','ab') as log:
        p=subprocess.Popen([str(PYTHON),str(APP/'server.py'),'--host','127.0.0.1','--port',str(PORT),'--recover'],cwd=APP,env=env,stdout=log,stderr=log,start_new_session=True)
    (HOME/'backend-pid.json').write_text(json.dumps({'pid':p.pid,'port':PORT}))
    for _ in range(100):
        if health():
            if diagnostics['runtime_checks']=='failed':dialog('The saved wind tunnel can open, but the native simulation engine needs attention. Details are in ~/Library/Logs/AeroBench/backend.log and the Mac diagnostics report.\n\n'+diagnostics['error'][:600])
            return
        if p.poll() is not None:break
        time.sleep(.2)
    raise RuntimeError('Aero Bench could not start. Open ~/Library/Logs/AeroBench/backend.log for details.')


def phone_address(key):
    request=urllib.request.Request(BASE+'/api/mac/phone',data=b'{}',headers={'Authorization':'Bearer '+key,'Content-Type':'application/json'},method='POST')
    with urllib.request.urlopen(request,timeout=90) as r:address=json.load(r)['url']
    if not re.fullmatch(r'https://[a-z0-9-]+\.trycloudflare\.com',address):raise RuntimeError('The phone connection returned an unexpected address.')
    path=APP/'data/private/connection.json';config=json.loads(path.read_text())
    config['allowed_origins']=list(dict.fromkeys(config.get('allowed_origins',[])+[address]))[-8:]
    temp=path.with_suffix('.tmp');temp.write_text(json.dumps(config));temp.chmod(0o600);temp.replace(path)
    return address


def open_wind_tunnel(key):
    if os.environ.get('AERO_HOSTED_UI')=='1':
        try:
            address=phone_address(key)
            site=json.loads((APP/'project.json').read_text())['site_url']
            open_url(site+'#'+urlencode({'backend':address,'key':key}));return
        except Exception as e:
            dialog('The online connection is unavailable. Opening the local interface instead.\n\n'+str(e)[:300])
    open_url(link(BASE,key))


def phone(key):
    address=phone_address(key)
    open_url(link(address,key))
    dialog('Choose Computer settings > Pair phone with QR in the browser, then scan with your phone camera. Keep the private QR/link private and keep your Mac awake.')


def stop_backend(notify=True):
    # Ask the authenticated API to stop its own process; never signal an arbitrary saved PID.
    key=settings()
    request=urllib.request.Request(BASE+'/api/mac/stop',data=b'{}',headers={'Authorization':'Bearer '+key,'Content-Type':'application/json'},method='POST')
    with urllib.request.urlopen(request,timeout=5) as r:json.load(r)
    for _ in range(50):
        if not health():break
        time.sleep(.1)
    if notify:dialog('Aero Bench stopped. Your models and results remain saved.\n\nAny active simulation was interrupted; reopen the app to start another run.')


def main():
    if platform.system()!='Darwin' or platform.machine()!='arm64':raise RuntimeError('This app requires an Apple Silicon Mac (M1 or newer).')
    version=platform.mac_ver()[0]
    if not version or int(version.split('.')[0])<14:raise RuntimeError('This build requires macOS 14 Sonoma or newer.')
    LOGS.mkdir(parents=True,exist_ok=True)
    if health():
        with urllib.request.urlopen(BASE+'/api/health',timeout=2) as r:build=json.load(r).get('desktop_build')
        if build!=VERSION:
            key=settings()
            request=urllib.request.Request(BASE+'/api/state',headers={'Authorization':'Bearer '+key})
            with urllib.request.urlopen(request,timeout=5) as r:state=json.load(r)
            if state.get('busy'):
                choice=dialog('A simulation is running with an older app version. Applying this update will interrupt that run. You can cancel and update after it finishes.',('Cancel','Restart engine'))
                if choice!='Restart engine':return
            stop_backend(notify=False)
            if health():raise RuntimeError('The older engine did not stop. Close it before starting the updated app.')
            start_backend();open_wind_tunnel(settings());return
    if not health():
        choice=dialog('Open the saved GTV6 wind tunnel and prepare the bundled native solver. No Python, Docker or Homebrew installation is needed. First launch can take a minute.\n\nThe engine will check its bundled libraries before enabling new runs. Your car scans and results stay on this Mac.',('Cancel','Open wind tunnel'))
        if choice!='Open wind tunnel':return
        start_backend();open_wind_tunnel(settings());return
    choice=dialog('Aero Bench is running. Small code updates are checked on every Connect launch. What would you like to do?',('Stop engine','Connect phone','Open wind tunnel'))
    if choice=='Stop engine':stop_backend()
    elif choice=='Connect phone':phone(settings())
    elif choice=='Open wind tunnel':open_wind_tunnel(settings())

if __name__=='__main__':
    try:main()
    except Exception as error:
        LOGS.mkdir(parents=True,exist_ok=True)
        with open(LOGS/'launcher.log','a') as f:f.write(time.strftime('%Y-%m-%d %H:%M:%S')+' '+repr(error)+'\n')
        dialog(str(error)+'\n\nLog: ~/Library/Logs/AeroBench/launcher.log')

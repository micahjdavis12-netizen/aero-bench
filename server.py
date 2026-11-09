"""Local-only, same-network web UI and serial CFD job queue."""
from http.server import ThreadingHTTPServer,SimpleHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse,unquote
import json,threading,time,uuid,os,re,traceback,shutil,socket,signal,subprocess,posixpath
from cfd import ROOT,foam_env
from runner import solve
from models import model_list,import_model
from auth import authorized,origin_allowed,access_key

DATA=ROOT/'data';RUNS=DATA/'runs';STATIC=ROOT/'web';LOCK=threading.Lock()
PHONE_LOCK=threading.Lock();PHONE_PROCESS=None;PHONE_URL=None

def safe_run(run_id):
    if not re.fullmatch(r'[a-zA-Z0-9_-]{1,80}',run_id):raise ValueError('Invalid run identifier.')
    path=RUNS/run_id
    if not path.is_dir():raise ValueError('Run not found.')
    return path

def read_json(path,default=None):
    try:return json.loads(path.read_text())
    except (OSError,ValueError):return default

def list_runs():
    result=[]
    for path in sorted(RUNS.glob('*'),key=lambda p:p.stat().st_mtime,reverse=True):
        if not path.is_dir():continue
        config=read_json(path/'run_config.json',{})
        state=read_json(path/'status.json',{'status':'prepared','stage':'prepared','progress':0})
        summary=read_json(path/'viewer/summary.json')
        entry={'id':path.name,'config':config,**state}
        if summary:
            entry['summary']={k:v for k,v in summary.items() if k!='history'}
            if state.get('status')!='running':entry.update(status='complete',progress=100)
        if state.get('stage')=='solving' and (path/'log.simpleFoam').exists():
            logpath=max(path.glob('log.simpleFoam*'),key=lambda p:p.stat().st_mtime)
            text=logpath.read_text()[-25000:];times=re.findall(r'^Time = ([\d.]+)',text,re.M)
            if times:entry['iteration']=float(times[-1]);entry['progress']=min(84,40+44*float(times[-1])/max(1,config.get('iterations',1200)))
        result.append(entry)
    return result

def job(case,config):
    try:solve(case,config)
    except Exception:traceback.print_exc()
    finally:LOCK.release()

def start_phone():
    global PHONE_PROCESS,PHONE_URL
    with PHONE_LOCK:
        if PHONE_PROCESS is not None and PHONE_PROCESS.poll() is None and PHONE_URL:return PHONE_URL
        path=DATA/'private/phone-tunnel.log'
        with open(path,'wb') as log:
            PHONE_PROCESS=subprocess.Popen([os.environ['AERO_CLOUDFLARED'],'tunnel','--no-autoupdate','--protocol','http2','--url','http://127.0.0.1:'+os.environ.get('AERO_PORT','8765')],stdout=log,stderr=log)
        for _ in range(120):
            addresses=re.findall(r'https://[a-z0-9-]+\.trycloudflare\.com',path.read_text(errors='replace'))
            if addresses:PHONE_URL=addresses[-1];return PHONE_URL
            if PHONE_PROCESS.poll() is not None:break
            time.sleep(.5)
        raise ValueError('Phone connection could not start. See data/private/phone-tunnel.log.')

class Handler(SimpleHTTPRequestHandler):
    def __init__(self,*args,**kwargs):super().__init__(*args,directory=str(STATIC),**kwargs)
    def log_message(self,fmt,*args):
        if not (args and isinstance(args[0],str) and '/api/state' in args[0]):super().log_message(fmt,*args)
    def end_headers(self):
        origin=self.headers.get('Origin')
        if origin and origin_allowed(origin,self.headers.get('Host','')):
            self.send_header('Access-Control-Allow-Origin',origin)
            self.send_header('Vary','Origin')
            self.send_header('Access-Control-Expose-Headers','Content-Disposition')
        self.send_header('Referrer-Policy','no-referrer')
        self.send_header('X-Content-Type-Options','nosniff')
        super().end_headers()
    def do_OPTIONS(self):
        if not origin_allowed(self.headers.get('Origin'),self.headers.get('Host','')):return self.json_response({'error':'Origin not allowed'},403)
        self.send_response(204);self.send_header('Access-Control-Allow-Methods','GET,POST,OPTIONS');self.send_header('Access-Control-Allow-Headers','Authorization,Content-Type,X-File-Name,X-Model-Units,X-Up-Axis');self.send_header('Access-Control-Max-Age','600');self.end_headers()
    def require_auth(self):
        if not origin_allowed(self.headers.get('Origin'),self.headers.get('Host','')):
            self.json_response({'error':'Origin not allowed'},403);return False
        if not authorized(self.headers.get('Authorization')):
            self.json_response({'error':'Pair this browser with your computer using its private connection link.'},401);return False
        return True
    def json_response(self,value,code=200):
        raw=json.dumps(value,allow_nan=False).encode();self.send_response(code);self.send_header('Content-Type','application/json');self.send_header('Cache-Control','no-store');self.send_header('Content-Length',str(len(raw)));self.end_headers();
        if self.command!='HEAD':self.wfile.write(raw)
    def file_response(self,path,ctype=None,download=False):
        if not path.is_file():return self.json_response({'error':'File not found'},404)
        self.send_response(200);self.send_header('Content-Type',ctype or self.guess_type(str(path)));self.send_header('Content-Length',str(path.stat().st_size))
        if download:self.send_header('Content-Disposition','attachment; filename="'+path.name+'"')
        self.end_headers()
        with open(path,'rb') as f:shutil.copyfileobj(f,self.wfile)
    def do_HEAD(self):
        path=posixpath.normpath('/'+unquote(urlparse(self.path).path).lstrip('/'))
        if (path.startswith('/api/') or path.startswith('/data/') or path.startswith('/baseline/')) and not self.require_auth():return
        return super().do_HEAD()
    def do_GET(self):
        path=posixpath.normpath('/'+unquote(urlparse(self.path).path).lstrip('/'))
        try:
            if path=='/api/health':return self.json_response({'app':'Aero Bench','version':2,'authentication_required':True,'desktop_build':os.environ.get('AERO_DESKTOP_BUILD','unknown')})
            if (path.startswith('/api/') or path.startswith('/data/') or path.startswith('/baseline/')) and not self.require_auth():return
            if path=='/api/state':
                env=foam_env();available=bool(shutil.which('simpleFoam',path=env['PATH'])) and (os.environ.get('AERO_NATIVE_MAC')!='1' or os.environ.get('AERO_NATIVE_READY')=='1')
                return self.json_response({'runs':list_runs(),'models':model_list(),'busy':LOCK.locked(),'solver_available':available,'engine_error':os.environ.get('AERO_ENGINE_ERROR',''),'local_domain':'aero-bench.local:8080','model_url':'/data/geometry/gtv6_closed_baseline.glb'})
            if path=='/api/mac/diagnostics' and os.environ.get('AERO_NATIVE_MAC')=='1':return self.file_response(DATA/'private/mac-diagnostics.json','application/json',True)
            modelmatch=re.fullmatch(r'/api/models/(model-[a-f0-9]{12})/model.glb',path)
            if modelmatch:return self.file_response(DATA/'models'/modelmatch[1]/'model.glb','model/gltf-binary')
            if path=='/data/geometry/gtv6_closed_baseline.glb':return self.file_response(DATA/'geometry/gtv6_closed_baseline.glb','model/gltf-binary')
            m=re.fullmatch(r'/api/runs/([\w-]+)/(summary.json|surface.json|slice.json|streamlines.json|log|mesh-log|forces.csv|config.json)',path)
            if m:
                case=safe_run(m[1]);name=m[2]
                if name=='log':
                    logs=list(case.glob('log.*'))
                    if not logs:return self.json_response({'status':'Preparing calculation'})
                    return self.file_response(max(logs,key=lambda p:p.stat().st_mtime),'text/plain')
                if name=='mesh-log':return self.file_response(case/'log.checkMesh.extended','text/plain')
                if name=='config.json':return self.file_response(case/'run_config.json','application/json',True)
                if name=='forces.csv':
                    s=read_json(case/'viewer/summary.json')
                    if not s:return self.json_response({'error':'Results not available'},404)
                    keys=['iteration','drag_n','downforce_n','side_force_n','pitch_moment_nm'];raw=(','.join(keys)+'\n'+'\n'.join(','.join(str(x[k]) for k in keys) for x in s['history'])).encode()
                    self.send_response(200);self.send_header('Content-Type','text/csv');self.send_header('Content-Disposition','attachment; filename="'+case.name+'-forces.csv"');self.send_header('Content-Length',str(len(raw)));self.end_headers();return self.wfile.write(raw)
                return self.file_response(case/'viewer'/name,'application/json')
            if path.startswith('/data/') or path.startswith('/api/'):return self.json_response({'error':'Not found'},404)
            return super().do_GET()
        except (ValueError,OSError) as e:return self.json_response({'error':str(e)},400)
    def do_POST(self):
        path=urlparse(self.path).path
        if not self.require_auth():return
        try:
            length=int(self.headers.get('Content-Length','0'))
            if length<0:raise ValueError('Invalid request size.')
            if path=='/api/models/upload':
                if length>60*1024*1024:return self.json_response({'error':'Maximum model size is 60 MiB.'},413)
                try:return self.json_response(import_model(self.rfile.read(length),unquote(self.headers.get('X-File-Name','model.stl')),self.headers.get('X-Model-Units','m'),self.headers.get('X-Up-Axis','z')),201)
                except ImportError:return self.json_response({'error':'Model import needs NumPy and VTK. Start the Docker edition.'},503)
            if length>20000:return self.json_response({'error':'Request too large'},413)
            if path=='/api/mac/phone' and os.environ.get('AERO_NATIVE_MAC')=='1':return self.json_response({'url':start_phone()})
            if path=='/api/mac/stop' and os.environ.get('AERO_NATIVE_MAC')=='1':
                self.json_response({'status':'stopping'})
                threading.Timer(1,lambda:os.killpg(os.getpgrp(),signal.SIGTERM)).start()
                return
            config=json.loads(self.rfile.read(length))
            if not isinstance(config,dict):raise ValueError('Expected a JSON object.')
            if path!='/api/run':return self.json_response({'error':'Not found'},404)
            clean={'speed_mph':float(config.get('speed_mph',80)),'iterations':int(config.get('iterations',2400)),'splitter':bool(config.get('splitter',False)),'wing':bool(config.get('wing',False)),'title':str(config.get('title','GTV6 variant'))[:70],'created_at':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())}
            clean['model_id']=config.get('model_id','baseline')
            clean['numerics']=config.get('numerics','exploratory')
            if clean['numerics'] not in ['exploratory','higher_order']:raise ValueError('Choose a supported numerical mode.')
            clean['mesh_resolution']=config.get('mesh_resolution','exploratory')
            if clean['mesh_resolution'] not in ['exploratory','refined']:raise ValueError('Choose a supported mesh detail.')
            if clean['model_id'] not in [m['id'] for m in model_list()]:raise ValueError('Choose an imported model or the GTV6 baseline.')
            limits={'speed_mph':(20,140),'iterations':(300,5000),'splitter_projection_in':(2,20),'wing_angle_deg':(-5,20),'wing_chord_in':(6,20),'wing_span_in':(36,72)}
            for key,(lo,hi) in limits.items():
                value=clean.get(key,float(config.get(key,{'splitter_projection_in':10,'wing_angle_deg':8,'wing_chord_in':12,'wing_span_in':60}.get(key,80))))
                if not lo<=value<=hi:raise ValueError(f'{key} must be between {lo} and {hi}.')
                clean[key]=value
            if (os.environ.get('AERO_NATIVE_MAC')=='1' and os.environ.get('AERO_NATIVE_READY')!='1') or not shutil.which('simpleFoam',path=foam_env()['PATH']):return self.json_response({'error':os.environ.get('AERO_ENGINE_ERROR') or 'The bundled simulation engine is unavailable. Reopen Aero Bench to see its startup checks.'},503)
            if not LOCK.acquire(blocking=False):return self.json_response({'error':'Another simulation is running. Wait for it to finish.'},409)
            run_id='run-'+time.strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:5];case=RUNS/run_id;case.mkdir(parents=True)
            threading.Thread(target=job,args=(case,clean),daemon=True).start();return self.json_response({'id':run_id},202)
        except (ValueError,TypeError,json.JSONDecodeError) as e:return self.json_response({'error':str(e)},400)

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--port',type=int,default=int(os.environ.get('PORT','8080')));p.add_argument('--host',default='0.0.0.0');p.add_argument('--recover',action='store_true');args=p.parse_args()
    RUNS.mkdir(parents=True,exist_ok=True)
    if os.environ.get('AERO_NATIVE_READY')=='1':
        mounted_engine=os.open(os.environ['WM_PROJECT_DIR'],os.O_RDONLY) # Keep the solver disk mounted until shutdown.
    access_key() # Create/validate private state before serving any requests.
    if args.recover:
        for path in RUNS.glob('*/status.json'):
            state=read_json(path,{})
            if state.get('status')=='running':path.write_text(json.dumps({'status':'failed','stage':'interrupted','progress':0,'message':'This calculation was interrupted by a server restart. Start a new run to calculate this configuration again.'}))
    print(f'Aero Bench: http://localhost:{args.port}  (listening on {args.host})',flush=True)
    ThreadingHTTPServer((args.host,args.port),Handler).serve_forever()

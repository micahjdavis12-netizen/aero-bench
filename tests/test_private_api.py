from pathlib import Path
import os,shutil,socket,subprocess,sys,tempfile,time,unittest,urllib.request,urllib.error
ROOT=Path(__file__).resolve().parent.parent
class PrivateAPI(unittest.TestCase):
 def test_private_assets_and_api_require_key_even_with_normalized_paths(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp)
   for name in ['auth.py','cfd.py','mesh_exports.py','models.py','postprocess.py','runner.py','server.py','project.json']:shutil.copy(ROOT/name,root/name)
   path=root/'web/baseline';path.mkdir(parents=True);(path/'model.glb').write_bytes(b'private-model-test-fixture')
   with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
   key='test-fixture-not-a-real-private-key-123456'
   env={**os.environ,'AERO_ACCESS_KEY':key,'AERO_NATIVE_MAC':'1','AERO_NATIVE_READY':'0'}
   p=subprocess.Popen([sys.executable,str(root/'server.py'),'--host','127.0.0.1','--port',str(port)],cwd=root,env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
   def request(path,headers=None,method='GET'):
    req=urllib.request.Request('http://127.0.0.1:'+str(port)+path,headers=headers or {},method=method)
    try:
     with urllib.request.urlopen(req,timeout=2) as response:return response.status,response.read()
    except urllib.error.HTTPError as error:return error.code,error.read()
   try:
    for _ in range(100):
     try:
      if request('/api/health')[0]==200:break
     except OSError:time.sleep(.05)
    else:self.fail('Test server failed to start')
    for path in ['/api/state','/baseline/model.glb','/unused/../baseline/model.glb','/%62aseline/model.glb']:
     self.assertEqual(request(path)[0],401,path)
    self.assertEqual(request('/baseline/model.glb',method='HEAD')[0],401)
    self.assertEqual(request('/baseline/model.glb',{'Authorization':'Bearer '+key})[1],b'private-model-test-fixture')
    self.assertEqual(request('/api/state',{'Authorization':'Bearer '+key,'Origin':'https://untrusted.example'})[0],403)
   finally:p.terminate();p.wait(timeout=5)
if __name__=='__main__':unittest.main()

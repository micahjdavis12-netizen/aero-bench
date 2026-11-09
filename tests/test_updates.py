from pathlib import Path
import hashlib,json,tempfile,unittest
from desktop.bootstrap import ALLOWED,validate_manifest,obtain_release,verify_release
ROOT=Path(__file__).resolve().parent.parent
class Updates(unittest.TestCase):
 def manifest(self,commit='1'*40,version='0.3.0'):
  return {'format':1,'version':version,'commit':commit,'files':{name:{'bytes':len((ROOT/name).read_bytes()),'sha256':hashlib.sha256((ROOT/name).read_bytes()).hexdigest()} for name in ALLOWED}}
 def fetcher(self,manifest,corrupt=None):
  def fetch(url,limit,context):
   if url.endswith('/updates/stable.json'):return json.dumps(manifest).encode()
   path=url.split('/'+manifest['commit']+'/',1)[1]
   return b'corrupted' if path==corrupt else (ROOT/path).read_bytes()
  return fetch
 def test_atomic_verified_update_and_cached_fallback(self):
  with tempfile.TemporaryDirectory() as tmp:
   home=Path(tmp);private=home/'app/data/private';private.mkdir(parents=True);key=private/'connection.json';key.write_text('private-fixture')
   first=self.manifest();folder,meta,error=obtain_release(home,None,self.fetcher(first));self.assertIsNone(error);verify_release(folder,meta)
   broken=self.manifest('2'*40,'0.3.1');old,meta,error=obtain_release(home,None,self.fetcher(broken,'cfd.py'))
   self.assertEqual(old,folder);self.assertIsNotNone(error);self.assertEqual(meta['commit'],first['commit']);self.assertEqual(key.read_text(),'private-fixture')
   self.assertFalse((home/'releases'/('0.3.1-'+'2'*12)).exists())
 def test_reject_private_paths_and_mutable_refs(self):
  value=self.manifest();value['files']['../app/data/private/connection.json']=value['files'].pop('cfd.py')
  with self.assertRaises(ValueError):validate_manifest(value)
  value=self.manifest();value['commit']='main'
  with self.assertRaises(ValueError):validate_manifest(value)
 def test_first_launch_requires_verified_complete_payload(self):
  with tempfile.TemporaryDirectory() as tmp:
   with self.assertRaises(RuntimeError):obtain_release(Path(tmp),None,self.fetcher(self.manifest(),'server.py'))
   self.assertFalse((Path(tmp)/'current-update.json').exists())
if __name__=='__main__':unittest.main()

"""Promote the latest code-only commit to the desktop update channel."""
from pathlib import Path
import hashlib,json,subprocess
from desktop.bootstrap import ALLOWED
ROOT=Path(__file__).resolve().parent

def generate():
 version=json.loads((ROOT/'updates/channel.json').read_text())['version']
 command=['git','log','-1','--format=%H','--',*sorted(ALLOWED),'updates/channel.json']
 commit=subprocess.check_output(command,cwd=ROOT,text=True).strip()
 if len(commit)!=40:raise ValueError('Commit not found')
 files={}
 for path in sorted(ALLOWED):
  raw=subprocess.check_output(['git','show',commit+':'+path],cwd=ROOT)
  files[path]={'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw)}
 value={'format':1,'version':version,'commit':commit,'files':files}
 from desktop.bootstrap import validate_manifest
 validate_manifest(value)
 (ROOT/'updates/stable.json').write_text(json.dumps(value,indent=2)+'\n')
 print('Desktop update:',version,'from',commit,';',sum(x['bytes'] for x in files.values()),'bytes')
if __name__=='__main__':generate()

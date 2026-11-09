"""Build the public interface without publishing any car scans or solver results."""
from pathlib import Path
import argparse,shutil,hashlib
ROOT=Path(__file__).resolve().parent

def build(output):
 output=output.resolve()
 if output.parent!=ROOT or output.name not in ['dist','docs','site-preview']:raise ValueError('Use a project-local dist, docs or site-preview output.')
 if output.exists():shutil.rmtree(output)
 shutil.copytree(ROOT/'web',output,ignore=shutil.ignore_patterns('baseline','vendor'))
 vendor=output/'vendor';vendor.mkdir();three=ROOT/'node_modules/three'
 for name in ['three.module.js','three.core.js']:shutil.copy(three/'build'/name,vendor/name)
 shutil.copy(three/'LICENSE',vendor/'THREE-LICENSE.txt')
 for name in ['loaders/GLTFLoader.js','controls/OrbitControls.js','utils/BufferGeometryUtils.js','utils/SkeletonUtils.js']:
  path=vendor/'addons'/name;path.parent.mkdir(parents=True,exist_ok=True);shutil.copy(three/'examples/jsm'/name,path)
 qr=ROOT/'node_modules/qrcode-generator';shutil.copy(qr/'dist/qrcode.js',vendor/'qrcode.js');shutil.copy(qr/'README.md',vendor/'QRCODE-README.md')
 # Give each module a content-specific URL so GitHub/browser caches cannot hold an old fix.
 def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()[:12]
 transport=digest(output/'transport.js')
 connection=output/'connection-ui.js';connection.write_text(connection.read_text().replace("'./transport.js'","'./transport.js?v="+transport+"'"))
 app=output/'app.js';app.write_text(app.read_text().replace("'./transport.js'","'./transport.js?v="+transport+"'").replace("'./connection-ui.js'","'./connection-ui.js?v="+digest(connection)+"'"))
 index=output/'index.html';index.write_text(index.read_text().replace('src="./app.js"','src="./app.js?v='+digest(app)+'"').replace('href="./style.css"','href="./style.css?v='+digest(output/'style.css')+'"').replace('src="./vendor/qrcode.js"','src="./vendor/qrcode.js?v='+digest(vendor/'qrcode.js')+'"'))
 (output/'.nojekyll').touch();print('Public code-only site built at',output)

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--output',default='dist');a=p.parse_args();build(ROOT/a.output)

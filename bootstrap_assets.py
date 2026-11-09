"""Restore the bundled model and saved baseline, without overwriting private data."""
from pathlib import Path,PurePosixPath
import json,zipfile,hashlib,shutil

ROOT=Path(__file__).resolve().parent

def ensure_assets(root=ROOT):
    if (root/'data/geometry/body_closed.stl').exists() and (root/'data/runs/baseline-80mph/viewer/summary.json').exists() and (root/'web/vendor/qrcode.js').exists():
        prepare_web(root);return
    archive=root/'baseline-assets.zip'
    manifest=json.loads((root/'assets-manifest.json').read_text())
    if hashlib.sha256(archive.read_bytes()).hexdigest()!=manifest['sha256']:raise RuntimeError('Baseline asset checksum mismatch. Download the repository again.')
    with zipfile.ZipFile(archive) as z:
        for item in z.infolist():
            path=PurePosixPath(item.filename)
            if path.is_absolute() or '..' in path.parts or not path.parts or not (path.parts[0]=='data' or path.parts[:2]==('web','vendor')) or 'private' in path.parts:raise RuntimeError('Unsafe baseline asset path.')
            dest=root.joinpath(*path.parts)
            if item.is_dir():dest.mkdir(parents=True,exist_ok=True);continue
            dest.parent.mkdir(parents=True,exist_ok=True)
            if not dest.exists():dest.write_bytes(z.read(item))

    prepare_web(root)

def prepare_web(root=ROOT):
    baseline=root/'web/baseline';baseline.mkdir(parents=True,exist_ok=True)
    case=root/'data/runs/baseline-80mph'
    for name in ['summary.json','surface.json','slice.json','streamlines.json']:
        if not (baseline/name).exists():shutil.copy(case/'viewer'/name,baseline/name)
    for source,name in [(root/'data/geometry/gtv6_closed_baseline.glb','model.glb'),(case/'run_config.json','config.json'),(case/'log.checkMesh.extended','mesh-check.txt'),(root/'BASELINE-RESULTS.md','run-notes.txt')]:
        if not (baseline/name).exists():shutil.copy(source,baseline/name)
    summary=json.loads((baseline/'summary.json').read_text());summary.pop('history',None)
    model=json.loads((root/'data/models/baseline.json').read_text());model['model_url']='baseline/model.glb'
    state={'runs':[{'id':'baseline-80mph','config':json.loads((baseline/'config.json').read_text()),'status':'complete','stage':'complete','progress':100,'summary':summary}],'models':[model],'busy':False,'solver_available':False,'backend_connected':False,'model_url':'baseline/model.glb'}
    (baseline/'state.json').write_text(json.dumps(state,separators=(',',':')))

if __name__=='__main__':ensure_assets()


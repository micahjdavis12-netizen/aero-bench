"""Bearer-key authentication for the private computer backend."""
from pathlib import Path
from urllib.parse import urlparse
import os,json,secrets,hmac

ROOT=Path(__file__).resolve().parent

def connection_settings():
    path=Path(os.environ.get('AERO_PRIVATE_DIR',str(ROOT/'data/private')))/'connection.json'
    path.parent.mkdir(parents=True,exist_ok=True)
    try:settings=json.loads(path.read_text())
    except (OSError,ValueError):settings={}
    if not settings.get('access_key'):
        settings={'access_key':secrets.token_urlsafe(32)}
        # Exclusive creation avoids overwriting a key being created by another process.
        try:
            fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
            with os.fdopen(fd,'w') as f:json.dump(settings,f)
        except FileExistsError:
            settings=json.loads(path.read_text())
            if not settings.get('access_key'):raise RuntimeError('Invalid private connection file. Rename data/private/connection.json to reset your access key.')
    try:path.chmod(0o600)
    except OSError:pass
    return settings

def access_key():return os.environ.get('AERO_ACCESS_KEY') or connection_settings()['access_key']

def allowed_origins():
    try:origins=json.loads((ROOT/'project.json').read_text())['allowed_origins']
    except (OSError,ValueError,KeyError):origins=[]
    origins+=os.environ.get('AERO_ALLOWED_ORIGINS','').split(',')
    if os.environ.get('AERO_NATIVE_MAC')=='1':
        try:origins+=connection_settings().get('allowed_origins',[])
        except (OSError,ValueError):pass
    return {o.strip().rstrip('/') for o in origins if o.strip()}

def origin_allowed(origin,host):
    if not origin:return True
    try:
        value=urlparse(origin)
        if value.scheme not in ['http','https'] or value.path or value.query or value.fragment:return False
        return origin.rstrip('/') in allowed_origins() or value.netloc==host
    except ValueError:return False

def authorized(header):
    prefix='Bearer '
    return bool(header and header.startswith(prefix) and hmac.compare_digest(header[len(prefix):],access_key()))

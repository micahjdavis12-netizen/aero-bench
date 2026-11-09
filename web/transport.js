// Static GitHub Pages + a private HTTPS computer backend. No secrets in this file.
const base=new URL('./',import.meta.url);
export const asset=path=>new URL(path.replace(/^\//,''),base).href;
let connection={url:'',key:''},online=false,lastError='';
try{connection=JSON.parse(sessionStorage.getItem('aero-connection')||'{}');}catch{}
function normalize(url){const u=new URL(url);if(!['http:','https:'].includes(u.protocol)||u.username||u.password||u.search||u.hash||!['','/'].includes(u.pathname))throw Error('Use the backend address printed by your computer.');if(location.protocol==='https:'&&u.protocol!=='https:')throw Error('GitHub Pages needs an HTTPS backend. Use the tunnel address from the launcher.');return u.origin;}
function save(){try{sessionStorage.setItem('aero-connection',JSON.stringify(connection));}catch{}}
function consumeFragment(){try{const f=new URLSearchParams(location.hash.slice(1));if(f.has('backend')&&f.has('key')){if(f.get('key').length<20)throw Error('Invalid private access key.');connection={url:normalize(f.get('backend')),key:f.get('key')};save();history.replaceState(null,'',location.pathname+location.search);return true;}}catch(e){lastError=e.message;history.replaceState(null,'',location.pathname+location.search);}return false;}
consumeFragment();window.addEventListener('hashchange',()=>{if(consumeFragment())window.dispatchEvent(new Event('aero-connection'));});
export function info(){return {url:connection.url||'',configured:!!(connection.url&&connection.key),online,error:lastError};}
export function pair(url,key){if(!key||key.length<20)throw Error('Paste the private access key from your computer.');connection={url:normalize(url),key};save();online=false;lastError='';window.dispatchEvent(new Event('aero-connection'));}
export function disconnect(){connection={url:'',key:''};online=false;lastError='';try{sessionStorage.removeItem('aero-connection');}catch{}window.dispatchEvent(new Event('aero-connection'));}
export function privateLink(){if(!connection.url||!connection.key)throw Error('Connect your computer first.');const u=new URL('./',base);u.hash=new URLSearchParams({backend:connection.url,key:connection.key}).toString();return u.href;}
async function remote(path,init={}){const {timeout=30000,...options}=init;const headers=new Headers(options.headers||{});headers.set('Authorization','Bearer '+connection.key);return fetch(connection.url+path,{...options,headers,credentials:'omit',mode:'cors',redirect:'error',signal:AbortSignal.timeout(timeout)});}
function response(value,status=200,type='application/json'){return new Response(type==='application/json'?JSON.stringify(value):value,{status,headers:{'Content-Type':type}});}
async function saved(path){
 if(path==='/api/state')return response({runs:[],models:[],busy:false,solver_available:false,backend_connected:false,connection_error:lastError});
 return response({error:'Connect your Mac to load your private models and run calculations.'},503);
}

export async function request(path,init={}){
 if(!path.startsWith('/api/')&&!path.startsWith('/data/'))throw Error('Invalid backend route.');
 if(connection.url&&connection.key){try{const r=await remote(path,init);if(path==='/api/state'){if(!r.ok){const e=await r.json().catch(()=>({}));throw Error(e.error||'Computer connection failed.');}const data=await r.json();online=true;lastError='';return response({...data,backend_connected:true});}return r;}catch(e){online=false;lastError=e.name==='TimeoutError'?'The computer did not respond.':e.message;if(path!=='/api/state')throw e;}}
 return saved(path);
}
export async function modelBytes(url){if(url.startsWith('/api/')||url.startsWith('/data/')){const r=await request(url);if(!r.ok)throw Error('The private model could not be loaded. Reconnect your computer.');return r.arrayBuffer();}const u=new URL(url,base);if(u.origin!==base.origin||!u.pathname.startsWith(base.pathname))throw Error('Unexpected model source.');return (await fetch(u)).arrayBuffer();}
export async function download(path){const r=await request(path);if(!r.ok){const e=await r.json().catch(()=>({}));throw Error(e.error||'Download unavailable.');}const blob=await r.blob(),u=URL.createObjectURL(blob),a=document.createElement('a');a.href=u;const name=path.endsWith('/forces.csv')?'aero-forces.csv':path.split('/').pop();a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(u),60000);}

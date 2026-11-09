import numpy as np
import json,struct

def obj(path,meshes):
    with open(path,'w') as out:
        out.write('# Geometry preparation only; NOT CFD validated. Metres; X forward Y left Z up.\n')
        off=1
        for name,v,f in meshes:
            out.write('o '+name+'\n')
            np.savetxt(out,v,fmt='v %.8f %.8f %.8f')
            np.savetxt(out,f+off,fmt='f %d %d %d');off+=len(v)

def glb(path,meshes):
    # glTF is Y-up. Map preparation (X,Y,Z) to (X,Z,-Y).
    doc={'asset':{'version':'2.0','generator':'GTV6 conservative geometry preparation'},'scene':0,'scenes':[{'nodes':[]}],'nodes':[],'meshes':[],'buffers':[{'byteLength':0}],'bufferViews':[],'accessors':[],'materials':[]}
    binary=bytearray()
    def accessor(arr,ctype,kind,target):
        while len(binary)%4:binary.append(0)
        off=len(binary);binary.extend(arr.tobytes());view=len(doc['bufferViews']);doc['bufferViews'].append({'buffer':0,'byteOffset':off,'byteLength':arr.nbytes,'target':target})
        a={'bufferView':view,'componentType':ctype,'count':len(arr),'type':kind}
        if kind=='VEC3':a.update(min=arr.min(0).tolist(),max=arr.max(0).tolist())
        doc['accessors'].append(a);return len(doc['accessors'])-1
    for i,(name,v,f) in enumerate(meshes):
        p=v[:,[0,2,1]].copy();p[:,2]*=-1;p=p.astype('<f4');indices=f.astype('<u4').reshape(-1)
        normals=np.zeros_like(p);n=np.cross(p[f[:,1]]-p[f[:,0]],p[f[:,2]]-p[f[:,0]])
        for j in range(3):np.add.at(normals,f[:,j],n)
        normals/=np.maximum(np.linalg.norm(normals,axis=1)[:,None],1e-20)
        a=accessor(p,5126,'VEC3',34962);b=accessor(normals,5126,'VEC3',34962);c=accessor(indices,5125,'SCALAR',34963)
        color=[0.12,0.14,0.17,1] if name.startswith('wheel') else [0.58,0.64,0.70,1]
        doc['materials'].append({'name':name,'doubleSided':True,'pbrMetallicRoughness':{'baseColorFactor':color,'metallicFactor':0.1,'roughnessFactor':0.7}})
        doc['meshes'].append({'name':name,'primitives':[{'attributes':{'POSITION':a,'NORMAL':b},'indices':c,'material':i}]})
        doc['nodes'].append({'name':name,'mesh':i});doc['scenes'][0]['nodes'].append(i)
    while len(binary)%4:binary.append(0)
    doc['buffers'][0]['byteLength']=len(binary);raw=json.dumps(doc,separators=(',',':')).encode()
    raw+=b' '*((-len(raw))%4)
    path.write_bytes(struct.pack('<4sII',b'glTF',2,12+8+len(raw)+8+len(binary))+struct.pack('<I4s',len(raw),b'JSON')+raw+struct.pack('<I4s',len(binary),b'BIN\0')+binary)

from pathlib import Path
import json,uuid
from cfd import ROOT

def import_model(raw,filename,units='m',up='z'):
    import vtk,numpy as np
    from vtk.util.numpy_support import vtk_to_numpy
    from mesh_exports import glb
    extension=Path(filename).suffix.lower()
    if extension not in ['.stl','.obj']:raise ValueError('Use a closed STL or OBJ exterior mesh.')
    model_id='model-'+uuid.uuid4().hex[:12];folder=ROOT/'data/models'/model_id;folder.mkdir(parents=True)
    source=folder/('source'+extension);source.write_bytes(raw)
    reader=vtk.vtkSTLReader() if extension=='.stl' else vtk.vtkOBJReader();reader.SetFileName(str(source));reader.Update()
    tri=vtk.vtkTriangleFilter();tri.SetInputConnection(reader.GetOutputPort());tri.Update();p=tri.GetOutput()
    if not p.GetNumberOfPolys():raise ValueError('The file contains no readable surface triangles.')
    if p.GetNumberOfPolys()>2500000:raise ValueError('Reduce the mesh below 2.5 million triangles before importing.')
    scale={'m':1,'mm':.001,'in':.0254}.get(units)
    if scale is None:raise ValueError('Choose metres, millimetres or inches.')
    points=vtk_to_numpy(p.GetPoints().GetData());points*=scale
    if up=='y':points[:]=points[:,[0,2,1]]*np.array([1,-1,1])
    elif up!='z':raise ValueError('Choose the model up axis.')
    lo=points.min(0);hi=points.max(0);dims=hi-lo
    if not 2<=dims[0]<=6.5 or not .8<=dims[1]<=3.5 or not .4<=dims[2]<=3.5:raise ValueError('Check the file units and orientation: the car should face +X and be about 2–6.5 m long.')
    points[:,0]-=(lo[0]+hi[0])/2;points[:,1]-=(lo[1]+hi[1])/2;points[:,2]-=lo[2]
    p.GetPoints().Modified();clean=vtk.vtkCleanPolyData();clean.SetInputData(p);clean.ToleranceIsAbsoluteOn();clean.SetAbsoluteTolerance(1e-6);clean.Update()
    edges=vtk.vtkFeatureEdges();edges.SetInputConnection(clean.GetOutputPort());edges.BoundaryEdgesOn();edges.NonManifoldEdgesOn();edges.FeatureEdgesOff();edges.ManifoldEdgesOff();edges.Update()
    if edges.GetOutput().GetNumberOfCells():raise ValueError('This mesh has open or non-manifold edges. Repair and close the exterior before importing for CFD; no force estimate has been fabricated.')
    normals=vtk.vtkPolyDataNormals();normals.SetInputConnection(clean.GetOutputPort());normals.ConsistencyOn();normals.AutoOrientNormalsOn();normals.SplittingOff();normals.Update();p=normals.GetOutput()
    w=vtk.vtkSTLWriter();w.SetFileTypeToBinary();w.SetFileName(str(folder/'body_closed.stl'));w.SetInputData(p);w.Write()
    v=vtk_to_numpy(p.GetPoints().GetData());f=vtk_to_numpy(p.GetPolys().GetData()).reshape(-1,4)[:,1:]
    glb(folder/'model.glb',[('body',v,f)])
    metadata={'id':model_id,'name':Path(filename).stem[:60],'model_url':'/api/models/'+model_id+'/model.glb','rotating_wheels':False,'parts':['body'],'bounds_m':[v.min(0).tolist(),v.max(0).tolist()],'triangles':len(f),'notes':'Single exterior mesh; wheel surfaces are stationary. Ground moves. Model scale and orientation supplied by the user.'}
    (folder/'metadata.json').write_text(json.dumps(metadata,indent=2));return metadata

def model_list():
    base=ROOT/'data/models/baseline.json';result=[json.loads(base.read_text())] if base.exists() else []
    for p in sorted((ROOT/'data/models').glob('model-*/metadata.json')):
        try:result.append(json.loads(p.read_text()))
        except (ValueError,OSError):pass
    return result

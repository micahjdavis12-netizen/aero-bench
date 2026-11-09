"""Export actual OpenFOAM fields and force histories for the local viewer."""
from pathlib import Path
import json,re,math
import numpy as np

def read_force_file(path):
    rows=[]
    for line in path.read_text().splitlines():
        if not line.strip() or line.lstrip().startswith('#'):continue
        row=np.fromstring(line.replace('(',' ').replace(')',' '),sep=' ')
        if len(row)>=7:rows.append(row)
    return rows

def forces(case):
    folder=case/'postProcessing/aeroForces'
    forcefiles=sorted(folder.rglob('force.dat'),key=lambda p:float(p.parent.name)) or sorted(folder.rglob('forces.dat'),key=lambda p:float(p.parent.name))
    if not forcefiles:raise RuntimeError('Solver did not write forces.')
    rows=[row for file in forcefiles for row in read_force_file(file)];momfiles=sorted(folder.rglob('moment.dat'),key=lambda p:float(p.parent.name))
    moments={float(row[0]):row for file in momfiles for row in read_force_file(file)}
    history=[]
    for i,row in enumerate(rows):
        # force.dat: time, total(3), pressure(3), viscous(3), optional porous(3).
        # forces.dat: time, pressure/viscous/porous force vectors then moment vectors.
        if forcefiles[-1].name=='force.dat':
            F=row[1:4];M=moments[float(row[0])][1:4] if float(row[0]) in moments else np.zeros(3)
        else:
            F=row[1:4]+row[4:7]+(row[7:10] if len(row)>=10 else 0)
            M=row[10:13]+row[13:16]+row[16:19] if len(row)>=19 else np.zeros(3)
        history.append({'iteration':float(row[0]),'drag_n':float(-F[0]),'downforce_n':float(-F[2]),'side_force_n':float(F[1]),'pitch_moment_nm':float(M[1])})
    history=sorted({x['iteration']:x for x in history}.values(),key=lambda x:x['iteration'])
    if not history:raise RuntimeError('No force samples in solver output.')
    tail=history[-min(200,max(10,len(history)//4)):]
    mean={k:float(np.mean([x[k] for x in tail])) for k in ['drag_n','downforce_n','side_force_n','pitch_moment_nm']}
    mean['front_equivalent_downforce_n']=mean['downforce_n']/2+mean['pitch_moment_nm']/2.4045657
    mean['rear_equivalent_downforce_n']=mean['downforce_n']/2-mean['pitch_moment_nm']/2.4045657
    drag=[x['drag_n'] for x in tail];vertical=[x['downforce_n'] for x in tail]
    metrics={'averaging_samples':len(tail),'iterations_completed':len(history),'drag_std_fraction':float(np.std(drag)/max(abs(mean['drag_n']),1)),'vertical_force_std_n':float(np.std(vertical)),'first_iteration_in_average':tail[0]['iteration'],'last_iteration':history[-1]['iteration']}
    return mean,metrics,history

def dump(path,data):path.write_text(json.dumps(data,separators=(',',':'),allow_nan=False))

def export(case):
    import vtk
    from vtk.util.numpy_support import vtk_to_numpy
    case=Path(case);config=json.loads((case/'run_config.json').read_text());out=case/'viewer';out.mkdir(exist_ok=True)
    mean,metrics,history=forces(case)
    if config.get('model_id','baseline')!='baseline':mean['front_equivalent_downforce_n']=None;mean['rear_equivalent_downforce_n']=None
    q=.5*config['density_kg_m3']*config['speed_mps']**2;mean['cd_reference_area_2m2']=mean['drag_n']/(q*2);mean['cl_down_reference_area_2m2']=mean['downforce_n']/(q*2)
    log=(case/'log.simpleFoam').read_text();continuity=re.findall(r'time step continuity errors : sum local = ([^,]+), global = ([^,]+), cumulative = ([\S]+)',log)
    metrics['final_continuity']=list(map(float,continuity[-1])) if continuity else None
    metrics['solver_reported_convergence']='SIMPLE solution converged' in log
    metrics['force_stable']=metrics['drag_std_fraction']<.02 and metrics['vertical_force_std_n']<max(5,.05*abs(mean['downforce_n']))
    meshlog=(case/'log.checkMesh').read_text();mesh_ok='Mesh OK' in meshlog
    config['mesh_check_ok']=mesh_ok
    cellmatch=re.search(r'^\s*cells:\s+(\d+)',meshlog,re.M)
    if cellmatch:config['mesh_cells']=int(cellmatch.group(1))
    extended=(case/'log.checkMesh.extended').read_text() if (case/'log.checkMesh.extended').exists() else ''
    metrics['extended_mesh_checks_failed']=int(re.search(r'Failed (\d+) mesh checks',extended).group(1)) if re.search(r'Failed (\d+) mesh checks',extended) else 0
    summary={'id':case.name,'title':config.get('title','GTV6 baseline'),'status':'complete','quality':'preliminary_stable' if metrics['force_stable'] and mesh_ok else 'preliminary_not_converged','config':config,'forces':mean,'convergence':metrics,'history':history,'warnings':['Single preliminary mesh; no mesh-independence or experimental validation.','Geometry uses a repaired approximate body and closed wheel faces.','Force stability is not proof of physical accuracy.'],'created_at':config.get('created_at')}
    if metrics['extended_mesh_checks_failed']:summary['warnings'].append(f"Standard mesh checks passed; {metrics['extended_mesh_checks_failed']} extended geometry checks flagged cells. See mesh logs before engineering use.")
    if config.get('numerics')=='exploratory' or 'first-order' in config.get('momentum_convection_scheme',''):summary['warnings'].append('First-order momentum convection adds numerical diffusion. Refine the mesh and check numerical-method sensitivity before relying on forces.')
    if not metrics['solver_reported_convergence']:summary['warnings'].append('The residual convergence criterion was not met; a stable force window alone does not establish a converged flow solution.')
    if config.get('numerical_sensitivity_note'):summary['warnings'].append(config['numerical_sensitivity_note'])
    (case/'case.foam').touch()
    reader=vtk.vtkOpenFOAMReader();reader.SetFileName(str(case/'case.foam'));reader.SetCreateCellToPoint(1);reader.SetSkipZeroTime(1);reader.UpdateInformation();reader.EnableAllPatchArrays();reader.EnableAllCellArrays()
    times=reader.GetTimeValues();latest=times.GetValue(times.GetNumberOfValues()-1);reader.SetTimeValue(latest);reader.Update();blocks=reader.GetOutput()
    summary['field_iteration']=float(latest)
    print('Read CFD time',latest,'blocks',blocks.GetNumberOfBlocks(),flush=True)
    internal=None;patches=[]
    def visit(block,name=''):
        nonlocal internal
        if isinstance(block,vtk.vtkMultiBlockDataSet):
            for i in range(block.GetNumberOfBlocks()):
                meta=block.GetMetaData(i);n=meta.Get(vtk.vtkCompositeDataSet.NAME()) if meta else str(i)
                visit(block.GetBlock(i),n or str(i))
        elif block is not None:
            if name=='internalMesh' or isinstance(block,vtk.vtkUnstructuredGrid):internal=block
            elif any(name==p or name.startswith(p+'_') for p in config['parts']):patches.append(block)
    visit(blocks)
    if internal is None or not patches:raise RuntimeError('Missing fluid mesh or vehicle patches in solved fields.')
    append=vtk.vtkAppendPolyData()
    for patch in patches:
        sf=vtk.vtkDataSetSurfaceFilter();sf.SetInputData(patch);sf.Update();append.AddInputData(sf.GetOutput())
    append.Update();tri=vtk.vtkTriangleFilter();tri.SetInputConnection(append.GetOutputPort());tri.Update();skin=tri.GetOutput()
    if skin.GetPointData().GetArray('p') is None:
        c2p=vtk.vtkCellDataToPointData();c2p.SetInputData(skin);c2p.Update();skin=c2p.GetOutput()
    points=vtk_to_numpy(skin.GetPoints().GetData());faces=vtk_to_numpy(skin.GetPolys().GetData()).reshape(-1,4)[:,1:]
    pressure=vtk_to_numpy(skin.GetPointData().GetArray('p'));cp=pressure/(.5*config['speed_mps']**2)
    dump(out/'surface.json',{'points':np.round(points,5).ravel().tolist(),'triangles':faces.ravel().tolist(),'cp':np.round(cp,5).tolist(),'pressure_pa':np.round(pressure*config['density_kg_m3'],2).tolist()})
    # A centreline plane sampled from the actual solved volumetric velocity.
    plane=vtk.vtkPlaneSource();plane.SetOrigin(-10,0,.015);plane.SetPoint1(5,0,.015);plane.SetPoint2(-10,0,3);plane.SetXResolution(150);plane.SetYResolution(42);plane.Update()
    probe=vtk.vtkProbeFilter();probe.SetInputConnection(plane.GetOutputPort());probe.SetSourceData(internal);probe.Update();sample=probe.GetOutput()
    pts=vtk_to_numpy(sample.GetPoints().GetData());valid=vtk_to_numpy(sample.GetPointData().GetArray('vtkValidPointMask'));vel=vtk_to_numpy(sample.GetPointData().GetArray('U'))
    strip=vtk.vtkTriangleFilter();strip.SetInputData(sample);strip.Update();faces=vtk_to_numpy(strip.GetOutput().GetPolys().GetData()).reshape(-1,4)[:,1:];faces=faces[np.all(valid[faces]!=0,axis=1)]
    dump(out/'slice.json',{'points':np.round(pts,5).ravel().tolist(),'triangles':faces.ravel().tolist(),'speed_mps':np.round(np.linalg.norm(vel,axis=1),4).tolist(),'freestream_mps':config['speed_mps']})
    if internal.GetPointData().GetArray('U') is None:
        c2p=vtk.vtkCellDataToPointData();c2p.SetInputData(internal);c2p.Update();internal=c2p.GetOutput()
    seeds=vtk.vtkPoints()
    for y in np.linspace(-1.5,1.5,11):
        for z in [.16,.4,.7,1.0,1.4,1.8]:seeds.InsertNextPoint(4.5,float(y),z)
    seeddata=vtk.vtkPolyData();seeddata.SetPoints(seeds)
    trace=vtk.vtkStreamTracer();trace.SetInputData(internal);trace.SetSourceData(seeddata);trace.SetInputArrayToProcess(0,0,0,vtk.vtkDataObject.FIELD_ASSOCIATION_POINTS,'U');trace.SetIntegratorTypeToRungeKutta45();trace.SetIntegrationDirectionToForward();trace.SetMaximumPropagation(22);trace.SetInitialIntegrationStep(.08);trace.SetMinimumIntegrationStep(.01);trace.SetMaximumIntegrationStep(.2);trace.SetMaximumNumberOfSteps(3000);trace.SetTerminalSpeed(.01);trace.Update()
    stream=trace.GetOutput();sp=vtk_to_numpy(stream.GetPoints().GetData()) if stream.GetNumberOfPoints() else np.zeros((0,3));lines=[];ids=vtk.vtkIdList();stream.GetLines().InitTraversal()
    while stream.GetLines().GetNextCell(ids):
        line=[ids.GetId(i) for i in range(ids.GetNumberOfIds())];lines.append(np.round(sp[line],4).ravel().tolist())
    dump(out/'streamlines.json',{'lines':lines,'source':'integrated from solved OpenFOAM U field'})
    summary['field_ranges']={'cp':[float(np.min(cp)),float(np.max(cp))],'pressure_pa':[float(pressure.min()*config['density_kg_m3']),float(pressure.max()*config['density_kg_m3'])],'streamline_count':len(lines),'vehicle_surface_triangles':len(vtk_to_numpy(skin.GetPolys().GetData()).reshape(-1,4))}
    dump(out/'summary.json',summary);(case/'status.json').write_text(json.dumps({'status':'complete','stage':'complete','progress':100,'summary':summary['quality']},indent=2));print('Export complete',json.dumps({'forces':mean,'metrics':metrics}),flush=True)
    return summary

if __name__=='__main__':
    import sys
    export(Path(sys.argv[1]))

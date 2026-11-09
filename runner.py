from pathlib import Path
import json,subprocess,shutil,time,os,sys
from cfd import ROOT,foam_env,generate,command

def status(case,stage,progress,message=''):
    (case/'status.json').write_text(json.dumps({'status':'running','stage':stage,'progress':progress,'message':message}))

def solve(case,config=None,reuse_mesh=False):
    case=Path(case).resolve();env=foam_env();case.mkdir(parents=True,exist_ok=True)
    try:
        if not reuse_mesh:
            status(case,'preparing',2);generate(case,config or {})
            status(case,'meshing',5);command(case,['blockMesh'],'log.blockMesh',env);command(case,['snappyHexMesh','-overwrite'],'log.snappyHexMesh',env)
            command(case,['checkMesh','-allTopology','-allGeometry'],'log.checkMesh.extended',env)
            command(case,['checkMesh','-allTopology'],'log.checkMesh',env)
        if 'Mesh OK' not in (case/'log.checkMesh').read_text():raise RuntimeError('Mesh quality checks failed; solver was not started. See log.checkMesh.')
        status(case,'decomposing',35);command(case,['decomposePar','-force'],'log.decomposePar',env)
        mpirun=shutil.which('mpirun',path=env['PATH']) or shutil.which('mpirun.openmpi',path=env['PATH']) or shutil.which('mpiexec',path=env['PATH'])
        if not mpirun:raise RuntimeError('OpenMPI is required for the configured six-worker case.')
        status(case,'solving',40,'Solving pressure, velocity and turbulence equations.')
        solver=shutil.which('simpleFoam',path=env['PATH'])
        if sys.platform=='darwin':
            args=[mpirun,'-np',env.get('AERO_WORKERS','4'),solver,'-parallel']
        else:
            args=[mpirun,'--oversubscribe','--mca','btl','self,vader,tcp','-np','6','/usr/bin/env','LD_LIBRARY_PATH='+env.get('LD_LIBRARY_PATH',''),'PATH='+env['PATH'],solver,'-parallel']
        command(case,args,'log.simpleFoam',env)
        status(case,'reconstructing',85);command(case,['reconstructPar','-latestTime'],'log.reconstructPar',env)
        status(case,'exporting',92)
        from postprocess import export
        return export(case)
    except Exception as e:
        (case/'status.json').write_text(json.dumps({'status':'failed','stage':'failed','progress':0,'message':str(e)}));raise

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('case');p.add_argument('--reuse-mesh',action='store_true');args=p.parse_args();solve(args.case,reuse_mesh=args.reuse_mesh)

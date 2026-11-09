"""OpenFOAM 2412 external-aerodynamics case generator and runner."""
from pathlib import Path
import json,math,os,re,shutil,subprocess,time,sys

ROOT=Path(__file__).resolve().parent
PARTS=['body','wheel_front_left','wheel_front_right','wheel_rear_left','wheel_rear_right']
CENTERS={'wheel_front_left':(1.2831433,.6688369,.30043435),'wheel_front_right':(1.2831434,-.6688366,.30043435),'wheel_rear_left':(-1.1214224,.6688369,.30043435),'wheel_rear_right':(-1.1214222,-.6688373,.30043435)}

def foam_env():
    env=os.environ.copy()
    if sys.platform=='darwin':
        env['OMP_NUM_THREADS']='1'
        return env
    modern=ROOT.parent/'of-modern/usr/lib/openfoam/openfoam2412'
    portable=ROOT.parent/'of-runtime'
    if (modern/'etc/bashrc').exists():
        platform=modern/'platforms/linux64GccDPInt32Opt'
        env['PATH']=str(platform/'bin')+':'+str(portable/'usr/bin')+':'+env['PATH']
        env['LD_LIBRARY_PATH']=':'.join(map(str,[platform/'lib/sys-openmpi',platform/'lib',platform/'lib/dummy',portable/'usr/lib/x86_64-linux-gnu']))+':'+env.get('LD_LIBRARY_PATH','')
        env['WM_PROJECT_DIR']=str(modern);env['FOAM_ETC']=str(modern/'etc');env['FOAM_LIBBIN']=str(platform/'lib');env['FOAM_APPBIN']=str(platform/'bin')
        env['OPAL_PREFIX']=str(portable/'usr');env['OMPI_MCA_mca_base_component_path']=str(portable/'usr/lib/x86_64-linux-gnu/openmpi/lib/openmpi3')
    elif (portable/'usr/bin/simpleFoam').exists():
        env['PATH']=str(portable/'usr/bin')+':'+env['PATH']
        env['LD_LIBRARY_PATH']=str(portable/'usr/lib')+':'+str(portable/'usr/lib/x86_64-linux-gnu')+':'+env.get('LD_LIBRARY_PATH','')
        env['WM_PROJECT_DIR']=str(portable/'usr/share/openfoam');env['FOAM_ETC']=str(portable/'usr/share/openfoam/etc')
        env['OPAL_PREFIX']=str(portable/'usr');env['OMPI_MCA_component_path']=str(portable/'usr/lib/x86_64-linux-gnu/openmpi/lib/openmpi3')
        env['OMPI_MCA_mca_base_component_path']=env['OMPI_MCA_component_path']
    else:
        env.setdefault('WM_PROJECT_DIR','/usr/share/openfoam');env.setdefault('FOAM_ETC','/usr/share/openfoam/etc')
    env['OMPI_ALLOW_RUN_AS_ROOT']='1';env['OMPI_ALLOW_RUN_AS_ROOT_CONFIRM']='1';env['OMP_NUM_THREADS']='1';env['OMPI_MCA_btl_vader_single_copy_mechanism']='none';env['OMPI_MCA_pml']='ob1'
    return env

def header(obj,klass='dictionary'):
    return f'FoamFile {{ version 2.0; format ascii; class {klass}; object {obj}; }}\n'

def write(case,rel,body,klass='dictionary'):
    p=case/rel;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(header(p.name,klass)+body)

def make_aero(case,config):
    import vtk
    names=[]
    if config.get('splitter'):
        cube=vtk.vtkCubeSource();projection=float(config.get('splitter_projection_in',10))*.0254
        cube.SetBounds(1.65,2.18+projection,-.82,.82,.13,.14);cube.Update()
        t=vtk.vtkTriangleFilter();t.SetInputConnection(cube.GetOutputPort());t.Update()
        w=vtk.vtkSTLWriter();w.SetFileTypeToBinary();w.SetFileName(str(case/'constant/triSurface/splitter.stl'));w.SetInputConnection(t.GetOutputPort());w.Write();names.append('splitter')
    if config.get('wing'):
        import numpy as np
        from vtk.util.numpy_support import numpy_to_vtk,numpy_to_vtkIdTypeArray
        chord=float(config.get('wing_chord_in',12))*.0254;span=float(config.get('wing_span_in',60))*.0254;angle=math.radians(float(config.get('wing_angle_deg',8)))
        x=(1-np.cos(np.linspace(0,np.pi,70)))/2
        yt=5*.12*(.2969*np.sqrt(x)-.1260*x-.3516*x*x+.2843*x**3-.1036*x**4)
        profile=np.column_stack([np.r_[x,x[-2:0:-1]],np.r_[yt,-yt[-2:0:-1]]])*chord
        verts=[]
        for y in [-span/2,span/2]:
            for xi,zi in profile:
                verts.append([-1.65-xi*math.cos(angle)+zi*math.sin(angle),y,1.52+xi*math.sin(angle)+zi*math.cos(angle)])
        n=len(profile);faces=[]
        for i in range(n):
            j=(i+1)%n;faces.extend([[i,j,n+i],[j,n+j,n+i]])
        # Convex polygon cap triangulation through a fan; symmetric NACA profile is convex here.
        for i in range(1,n-1):faces.extend([[0,i+1,i],[n,n+i,n+i+1]])
        p=vtk.vtkPolyData();points=vtk.vtkPoints();points.SetData(numpy_to_vtk(np.array(verts),deep=True));p.SetPoints(points)
        cells=vtk.vtkCellArray();cells.SetCells(len(faces),numpy_to_vtkIdTypeArray(np.column_stack([np.full(len(faces),3),faces]).astype(np.int64).ravel(),deep=True));p.SetPolys(cells)
        normals=vtk.vtkPolyDataNormals();normals.SetInputData(p);normals.SplittingOff();normals.ConsistencyOn();normals.AutoOrientNormalsOn();normals.Update()
        w=vtk.vtkSTLWriter();w.SetFileTypeToBinary();w.SetFileName(str(case/'constant/triSurface/wing.stl'));w.SetInputConnection(normals.GetOutputPort());w.Write();names.append('wing')
    return names

def generate(case,config):
    config={'speed_mph':80,'iterations':2400,'model_id':'baseline','numerics':'exploratory','mesh_resolution':'exploratory',**config}
    case=Path(case);case.mkdir(parents=True,exist_ok=True)
    (case/'constant/triSurface').mkdir(parents=True,exist_ok=True)
    speed=float(config.get('speed_mph',80))*.44704
    model_id=config.get('model_id','baseline')
    if model_id=='baseline':source=ROOT/'data/geometry';base_parts=PARTS
    else:
        if not re.fullmatch(r'model-[a-f0-9]{12}',model_id):raise ValueError('Invalid model.')
        source=ROOT/'data/models'/model_id
        if not (source/'metadata.json').exists():raise ValueError('Model not found.')
        base_parts=['body']
        if config.get('wing') or config.get('splitter'):raise ValueError('The current aero editor is calibrated to the GTV6. Imported models can run baseline airflow tests.')
    for name in base_parts:shutil.copyfile(source/(name+'_closed.stl'),case/'constant/triSurface'/(name+'.stl'))
    parts=base_parts+make_aero(case,config)
    config={**config,'speed_mps':speed,'density_kg_m3':1.225,'kinematic_viscosity_m2_s':1.5e-5,'road_z_m':.004,'wheel_radius_m':.30043435,'reference_area_m2':2.0,'domain_m':{'x':[-28,15],'y':[-9,9],'z':[.004,12.004]},'solver':'OpenFOAM 2412 simpleFoam / steady incompressible RANS k-omega SST','engine_build':os.environ.get('AERO_ENGINE_BUILD','Linux OpenFOAM 2412 patch260127'),'parts':parts,'model_assumptions':['Approximate repaired source body; physical dimensions unverified','Closed windows, cooling paths and wheel faces','4 mm road/tire intersection approximates a finite contact patch','Idealized aero additions; mounts and structural behaviour omitted']}
    (case/'run_config.json').write_text(json.dumps(config,indent=2))
    write(case,'system/blockMeshDict','''convertToMeters 1;
vertices ((-28 -9 .004)(15 -9 .004)(15 9 .004)(-28 9 .004)(-28 -9 12.004)(15 -9 12.004)(15 9 12.004)(-28 9 12.004));
blocks (hex (0 1 2 3 4 5 6 7) (58 24 16) simpleGrading (1 1 1));
edges ();
boundary (
 inlet {type patch; faces ((1 2 6 5));}
 outlet {type patch; faces ((0 4 7 3));}
 ground {type wall; faces ((0 3 2 1));}
 farfield {type symmetryPlane; faces ((0 1 5 4)(3 7 6 2)(4 5 6 7));}
);
mergePatchPairs ();
''')
    # A single symmetryPlane patch cannot contain non-coplanar faces; use slip patch instead.
    p=case/'system/blockMeshDict';p.write_text(p.read_text().replace('farfield {type symmetryPlane;','farfield {type patch;'))
    geometry='\n'.join(f'{n}.stl {{type triSurfaceMesh; name {n};}}' for n in parts)
    refinement='\n'.join(f'{n} {{level ({7 if n=="splitter" else 6 if n=="wing" else 4} {7 if n in ["splitter","wing"] else 5}); patchInfo {{type wall;}}}}' for n in parts)
    layer='\n'.join(f'{n} {{nSurfaceLayers {3 if n=="body" else 2};}}' for n in parts)
    write(case,'system/snappyHexMeshDict',f'''castellatedMesh true; snap true; addLayers true;
geometry {{
{geometry}
 nearCar {{type searchableBox; min (-3 -1.6 .004); max (3.3 1.6 2.1);}}
 wake {{type searchableBox; min (-13 -2 .004); max (-2 2 3);}}
}}
castellatedMeshControls {{
 maxLocalCells 400000; maxGlobalCells 1600000; minRefinementCells 0; maxLoadUnbalance .1; nCellsBetweenLevels 3;
 features (); refinementSurfaces {{{refinement}}}
 resolveFeatureAngle 45;
 refinementRegions {{nearCar {{mode inside; levels ((1e15 3));}} wake {{mode inside; levels ((1e15 2));}}}}
 locationInMesh (8 4 3); allowFreeStandingZoneFaces true;
}}
snapControls {{nSmoothPatch 4; tolerance 1.5; nSolveIter 50; nRelaxIter 5; nFeatureSnapIter 10; implicitFeatureSnap true; explicitFeatureSnap false; multiRegionFeatureSnap false;}}
addLayersControls {{
 relativeSizes true; layers {{{layer}}}
 expansionRatio 1.2; finalLayerThickness .4; minThickness .1; nGrow 0; featureAngle 60; nRelaxIter 5;
 nSmoothSurfaceNormals 1; nSmoothNormals 3; nSmoothThickness 10; maxFaceThicknessRatio .5;
 maxThicknessToMedialRatio .3; minMedialAxisAngle 90; nBufferCellsNoExtrude 0; nLayerIter 40;
}}
meshQualityControls {{
 maxNonOrtho 65; maxBoundarySkewness 20; maxInternalSkewness 4; maxConcave 80;
 minVol 1e-13; minTetQuality 1e-15; minArea -1; minTwist .02; minDeterminant .001; minFaceWeight .02; minVolRatio .01; minTriangleTwist -1;
 nSmoothScale 4; errorReduction .75; relaxed {{maxNonOrtho 75;}}
}}
writeFlags (scalarLevels layerSets layerFields); mergeTolerance 1e-6;
''')
    if config['mesh_resolution']=='refined':
        path=case/'system/snappyHexMeshDict';path.write_text(path.read_text().replace('maxGlobalCells 1600000','maxGlobalCells 2400000').replace('level (4 5)','level (5 6)'))
    solid='|'.join(parts)
    write(case,'system/controlDict',f'''application simpleFoam;
startFrom startTime; startTime 0; stopAt endTime; endTime {int(config.get('iterations',1200))}; deltaT 1;
writeControl timeStep; writeInterval {math.gcd(int(config['iterations']),400)}; purgeWrite 1; writeFormat ascii; writePrecision 8; writeCompression off; timeFormat general; timePrecision 6; runTimeModifiable true;
functions {{
 aeroForces {{type forces; libs ("libforces.so"); patches ("({solid})"); p p; U U; rho rhoInf; rhoInf 1.225; CofR (.0808605 0 .004); writeControl timeStep; writeInterval 1; log true;}}
 yPlus {{type yPlus; libs ("libfieldFunctionObjects.so"); writeControl writeTime; log true;}}
}}
''')
    write(case,'system/fvSchemes','''ddtSchemes {default steadyState;}
gradSchemes {default cellLimited Gauss linear 1;}
divSchemes {default none; div(phi,U) bounded Gauss linearUpwind grad(U); div(phi,k) bounded Gauss upwind; div(phi,omega) bounded Gauss upwind; div((nuEff*dev2(T(grad(U))))) Gauss linear;}
laplacianSchemes {default Gauss linear limited .5;}
interpolationSchemes {default linear;}
snGradSchemes {default limited .5;}
wallDist {method meshWave;}
''')
    if config['numerics']=='exploratory':
        path=case/'system/fvSchemes';path.write_text(path.read_text().replace('bounded Gauss linearUpwind grad(U)','bounded Gauss upwind'))
    write(case,'system/fvSolution','''solvers {
 p {solver GAMG; tolerance 1e-7; relTol .05; smoother GaussSeidel;}
 "(U|k|omega)" {solver smoothSolver; smoother symGaussSeidel; tolerance 1e-8; relTol .1;}
 Phi {solver GAMG; tolerance 1e-7; relTol .01; smoother GaussSeidel;}
}
SIMPLE {nNonOrthogonalCorrectors 1; consistent yes; residualControl {p 1e-4; U 1e-5; k 1e-5; omega 1e-5;}}
potentialFlow {nNonOrthogonalCorrectors 10;}
relaxationFactors {fields {p .2;} equations {U .3; k .3; omega .3;}}
''')
    workers=int(os.environ.get('AERO_WORKERS','6'))
    if workers not in (4,6):raise ValueError('Supported solver worker counts are 4 and 6.')
    n='2 2 1' if workers==4 else '3 2 1'
    write(case,'system/decomposeParDict',f'numberOfSubdomains {workers}; method simple; simpleCoeffs {{n ({n}); delta .001;}}')
    if sys.platform=='darwin':
        control=case/'system/controlDict'
        text=control.read_text()
        for name in ['forces','fieldFunctionObjects']:
            libdir=Path(os.environ.get('FOAM_LIBBIN',''))
            candidates=[p for p in [libdir/('lib'+name+'.dylib'),libdir/('lib'+name+'.so')] if p.is_file()]
            if not candidates:raise RuntimeError('Native OpenFOAM library missing: '+name)
            text=text.replace('lib'+name+'.so',str(candidates[0]))
        control.write_text(text)
    write(case,'constant/transportProperties','transportModel Newtonian; nu [0 2 -1 0 0 0 0] 1.5e-5;')
    write(case,'constant/turbulenceProperties','simulationType RAS; RAS {RASModel kOmegaSST; turbulence on; printCoeffs on;}')
    vel=f'(-{speed:.8f} 0 0)';k=1.5*(.01*speed)**2;omega=math.sqrt(k)/(.09**.25*.2)
    for field,dim,internal,klass in [('U','0 1 -1 0 0 0 0',vel,'volVectorField'),('p','0 2 -2 0 0 0 0','0','volScalarField'),('k','0 2 -2 0 0 0 0',str(k),'volScalarField'),('omega','0 0 -1 0 0 0 0',str(omega),'volScalarField'),('nut','0 2 -1 0 0 0 0','0','volScalarField')]:
        bcs={}
        if field=='U':
            bcs={'inlet':f'type fixedValue; value uniform {vel};','outlet':f'type inletOutlet; inletValue uniform {vel}; value uniform {vel};','farfield':'type slip;','ground':f'type fixedValue; value uniform {vel};'}
            for n in parts:
                if n in CENTERS:
                    c=' '.join(str(x) for x in CENTERS[n]);bcs[n]=f'type rotatingWallVelocity; origin ({c}); axis (0 1 0); omega {speed/.30043435}; value uniform (0 0 0);'
                else:bcs[n]='type noSlip;'
        elif field=='p':
            bcs={'inlet':'type zeroGradient;','outlet':'type fixedValue; value uniform 0;','farfield':'type zeroGradient;','ground':'type zeroGradient;'}
            bcs.update({n:'type zeroGradient;' for n in parts})
        elif field=='nut':
            bcs={n:'type calculated; value uniform 0;' for n in ['inlet','outlet','farfield']}
            bcs.update({n:'type nutkWallFunction; value uniform 0;' for n in ['ground']+parts})
        else:
            bcs={'inlet':f'type fixedValue; value uniform {internal};','outlet':f'type inletOutlet; inletValue uniform {internal}; value uniform {internal};','farfield':'type zeroGradient;'}
            wall='kqRWallFunction' if field=='k' else 'omegaWallFunction'
            bcs.update({n:f'type {wall}; value uniform {internal};' for n in ['ground']+parts})
        text='\n'.join(f'{n} {{{val}}}' for n,val in bcs.items())
        write(case,'0/'+field,f'dimensions [{dim}];\ninternalField uniform {internal};\nboundaryField {{{text}}}\n',klass)
    return config

def command(case,args,logname,env=None):
    env=(env or foam_env()).copy();env['PWD']=str(Path(case).resolve())
    with open(Path(case)/logname,'w') as log:
        p=subprocess.run(args,cwd=case,env=env,stdout=log,stderr=subprocess.STDOUT)
    if p.returncode:raise RuntimeError(f'{args[0]} failed ({p.returncode}); see {logname}: '+(Path(case)/logname).read_text()[-1600:])

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('case');p.add_argument('--speed',type=float,default=80);p.add_argument('--iterations',type=int,default=2400);args=p.parse_args()
    print(json.dumps(generate(args.case,{'speed_mph':args.speed,'iterations':args.iterations}),indent=2))

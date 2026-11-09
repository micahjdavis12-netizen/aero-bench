"""Check exported field structure, pressure units, and force-history averaging."""
from pathlib import Path
import json,math,statistics,sys

case=Path(sys.argv[1]) if len(sys.argv)>1 else Path(__file__).resolve().parent/'data/runs/baseline-80mph'
s=json.loads((case/'viewer/summary.json').read_text());surface=json.loads((case/'viewer/surface.json').read_text());plane=json.loads((case/'viewer/slice.json').read_text());lines=json.loads((case/'viewer/streamlines.json').read_text())
assert s['status']=='complete'
for field in [surface,plane]:
    assert len(field['points'])%3==0 and len(field['triangles'])%3==0
    assert all(math.isfinite(v) for v in field['points'])
    assert all(0<=v<len(field['points'])//3 for v in field['triangles'])
assert len(surface['cp'])==len(surface['points'])//3==len(surface['pressure_pa'])
assert all(math.isfinite(v) for v in surface['cp']+surface['pressure_pa']+plane['speed_mps'])
q=.5*s['config']['density_kg_m3']*s['config']['speed_mps']**2
assert max(abs(cp-pa/q) for cp,pa in zip(surface['cp'],surface['pressure_pa']))<1e-4
n=s['convergence']['averaging_samples'];tail=s['history'][-n:]
for key in ['drag_n','downforce_n','side_force_n','pitch_moment_nm']:
    assert math.isclose(statistics.mean(x[key] for x in tail),s['forces'][key],rel_tol=1e-10,abs_tol=1e-9),key
assert lines['lines'] and all(len(line)%3==0 and all(math.isfinite(v) for v in line) for line in lines['lines'])
assert s['history'][-1]['iteration']==s['convergence']['last_iteration']
assert math.isclose(s['forces']['front_equivalent_downforce_n']+s['forces']['rear_equivalent_downforce_n'],s['forces']['downforce_n'],abs_tol=1e-9) if s['config'].get('model_id','baseline')=='baseline' else True
print('PASS: solved-field arrays, pressure/Cp units, force averaging, axle-load sum and streamline exports.')
print('Run quality:',s['quality'],'; solver residual convergence:',s['convergence']['solver_reported_convergence'])
print('These data checks do not establish mesh independence or physical accuracy.')

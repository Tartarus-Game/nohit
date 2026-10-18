import hashlib,json,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from nohit import _configure_solver_process
_configure_solver_process()
from nohit.engine.human_difficulty import analyze_route
from tools.benchmark_samples import implementations
base=ROOT/'build/one-second-20261018/native-final'
route=json.loads((base/'sans_bonegap1-optimized.json').read_text());entry=json.loads((base/'sans_bonegap1-entry.json').read_text())
settings=dict(seed=42,dt_schedule=entry['dt_schedule'],initial_environment=entry['initial_environment'],
    initial_arena=entry['initial_arena'],max_ticks=40000,termination_policy='eof_hazards_drained')
before=implementations()
report=analyze_route(ROOT/'build/realhell-final-20261018/source.csv',entry['initial'],settings,route)
assert before==implementations()
record=dict(kind='analysis of previously original-engine-verified route; not a fresh human-friendly solve',
    source_sha256=hashlib.sha256((ROOT/'build/realhell-final-20261018/source.csv').read_bytes()).hexdigest(),
    route_sha256=hashlib.sha256((base/'sans_bonegap1-optimized.json').read_bytes()).hexdigest(),
    implementation_sha256=hashlib.sha256(json.dumps(before,sort_keys=True).encode()).hexdigest(),difficulty=report)
out=ROOT/'build/human-friendly-20261018/realhell-difficulty.json';out.write_text(json.dumps(record,ensure_ascii=False,allow_nan=False,indent=2))
print(json.dumps({k:report[k] for k in ('score','label','minimum_clearance_px','operations','timing_coverage','human_feasibility','analysis_seconds')},ensure_ascii=False))

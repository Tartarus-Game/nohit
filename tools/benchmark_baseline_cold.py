"""Measure a separate original checkout in a fresh process and empty JIT cache."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

ROOT=Path(__file__).resolve().parents[1]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline',type=Path,required=True)
    parser.add_argument('--wave',default='sans_bonegap1')
    parser.add_argument('--entry',type=Path,default=ROOT/'tools/optimization-results/sans_bonegap1-entry.json')
    parser.add_argument('--output',type=Path,default=ROOT/'tools/optimization-results/cold-baseline.json')
    parser.add_argument('--child',action='store_true');args=parser.parse_args()
    if args.child:
        started=time.perf_counter()
        import resource
        from nohit.engine.csv_solver import solve_csv
        imported=time.perf_counter()
        entry=json.loads(args.entry.read_text())
        result=solve_csv(args.baseline/'c2-sans-fight'/(args.wave+'.csv'),entry['initial'],
            initial_environment=entry['initial_environment'],initial_arena=entry['initial_arena'],
            initial_confirm=entry['initial_confirm'],previous_confirm=entry['previous_confirm'],
            dt_schedule=[1/30]*40000,max_ticks=40000,width=3000,seconds=60)
        print(json.dumps(dict(status=result['status'],reason=result['reason'],
            import_seconds=imported-started,inside_seconds=time.perf_counter()-started,
            solve_seconds=result['wall_seconds'],search_stats=result['search_stats'],
            rss_kb=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)))
        return
    baseline=args.baseline.resolve()
    commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=baseline,text=True).strip()
    with tempfile.TemporaryDirectory(prefix='nohit-baseline-empty-') as cache:
        env=dict(os.environ,NUMBA_CACHE_DIR=cache,OMP_WAIT_POLICY='PASSIVE',PYTHONPATH=str(baseline))
        started=time.perf_counter()
        process=subprocess.run([sys.executable,str(Path(__file__).resolve()),'--child',
            '--baseline',str(baseline),'--wave',args.wave,'--entry',str(args.entry.resolve())],cwd=baseline,env=env,
            capture_output=True,text=True,timeout=120)
        wall=time.perf_counter()-started
        if process.returncode:raise RuntimeError(process.stdout+process.stderr)
        record=json.loads(process.stdout);record.update(external_wall_seconds=wall,
            empty_numba_cache=True,route_cache=False,environment_cache=False,base_commit=commit)
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(record,indent=2))
        print(json.dumps({key:value for key,value in record.items() if key!='search_stats'}))


if __name__=='__main__':main()

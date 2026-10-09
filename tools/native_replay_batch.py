"""CPU-budgeted independent original-game replays; no shared runtime or routes.

Campaign rounds with inherited state must use solve_normal_native.mjs instead.
"""
import argparse,concurrent.futures,json,os,subprocess,time
from pathlib import Path


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('waves',nargs='+');parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--cpu-budget',type=int,default=8);parser.add_argument('--processes',type=int,default=4)
    args=parser.parse_args()
    if not 1<=args.cpu_budget<=32 or not 1<=args.processes<=args.cpu_budget:parser.error('require 1 <= processes <= cpu-budget <= 32')
    if len(set(args.waves))!=len(args.waves):parser.error('wave names must be unique')
    workers=max(1,args.cpu_budget//args.processes);args.out.mkdir(parents=True,exist_ok=True)
    started=time.perf_counter()
    def run(wave):
        if not wave.startswith('sans_') or any(c not in 'abcdefghijklmnopqrstuvwxyz0123456789_' for c in wave):raise ValueError('invalid wave name')
        directory=(args.out/wave).resolve();directory.mkdir(exist_ok=True)
        env=dict(os.environ,NOHIT_BENCH_OUT=str(directory),NOHIT_WORKERS=str(workers))
        began=time.perf_counter()
        with (directory/'native.log').open('w') as log:
            result=subprocess.run(['node','tools/native_optimized_replay.mjs',wave],env=env,stdout=log,stderr=subprocess.STDOUT)
        file=directory/'native-summary.json'
        records=json.loads(file.read_text()) if file.exists() else []
        return dict(wave=wave,exit_code=result.returncode,wall_seconds=time.perf_counter()-began,
            passed=result.returncode==0 and len(records)==1 and records[0]['passed'],records=records)
    runs=[]
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.processes) as executor:
        futures=[executor.submit(run,wave) for wave in args.waves]
        for future in concurrent.futures.as_completed(futures):
            result=future.result();runs.append(result)
            print(json.dumps({key:result[key] for key in ('wave','passed','wall_seconds')}),flush=True)
    order={wave:i for i,wave in enumerate(args.waves)};runs.sort(key=lambda r:order[r['wave']])
    record=dict(scope='independent attacks, fresh unmodified C2 runtime per attack; not a continuous campaign',
        cpu_budget=args.cpu_budget,processes=args.processes,workers_per_process=workers,
        total_wall_seconds=time.perf_counter()-started,runs=runs,all_passed=all(r['passed'] for r in runs))
    (args.out/'batch.json').write_text(json.dumps(record,indent=2)+'\n')
    (args.out/'native-summary.json').write_text(json.dumps([row for run in runs for row in run['records']],indent=2)+'\n')
    if not record['all_passed']:raise SystemExit(1)

if __name__=='__main__':main()

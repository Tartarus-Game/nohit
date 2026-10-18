"""Alternate fresh-process benchmarks of two checkouts using identical inputs.

The checkouts must remain unchanged for the entire run. Compiled code may be
reused; each subprocess reconstructs its own world and discovers a new route.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import statistics
import subprocess
import sys
import time


def implementation(root):
    return {p.name:hashlib.sha256(p.read_bytes()).hexdigest()
            for p in (root/'nohit/engine').iterdir() if p.suffix in ('.py','.cpp')}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline',type=Path,required=True)
    parser.add_argument('--optimized',type=Path,required=True)
    parser.add_argument('--csv',type=Path,required=True)
    parser.add_argument('--entry',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--repeats',type=int,default=3)
    parser.add_argument('--workers',type=int,default=4)
    args=parser.parse_args()
    if args.repeats<1:parser.error('repeats must be positive')
    roots={name:getattr(args,name).resolve() for name in ('baseline','optimized')}
    identities={name:implementation(root) for name,root in roots.items()}
    records=[];args.out.parent.mkdir(parents=True,exist_ok=True)
    for repeat in range(args.repeats):
        order=('baseline','optimized') if repeat%2==0 else ('optimized','baseline')
        for name in order:
            root=roots[name]
            if implementation(root)!=identities[name]:raise RuntimeError('Checkout changed before run')
            command=[sys.executable,'-m','tools.benchmark_round8_request',str(args.csv.resolve()),
                '--entry',str(args.entry.resolve()),'--out',str(args.out.resolve()),'--child',
                '--workers',str(args.workers),'--seconds','180','--width','8192','--memory-mb','512',
                '--observation-chunk-ticks','480','--observation-preview-ticks','480']
            began=time.perf_counter()
            environment=dict(os.environ,NOHIT_NATIVE_CACHE=str(roots['optimized']/'build/native'))
            result=subprocess.run(command,cwd=root,capture_output=True,text=True,env=environment)
            elapsed=time.perf_counter()-began
            if result.returncode:raise RuntimeError(result.stdout+'\n'+result.stderr)
            if implementation(root)!=identities[name]:raise RuntimeError('Checkout changed during run')
            record=json.loads(result.stdout)
            stats=record.pop('search_stats',{})
            record.update(revision=name,repeat=repeat,external_wall_seconds=elapsed,
                implementation=identities[name],search_seconds=stats.get('search_seconds'),
                verification_seconds=stats.get('verification_seconds'),
                expanded_states=stats.get('expanded_states'),native_code=stats.get('native_code'),
                fixed_prefix_ticks=stats.get('fixed_prefix_ticks'),
                observation_backtracks=stats.get('observation_backtracks',0))
            records.append(record)
            summaries={label:{'solve_seconds_median':statistics.median(r['solve_seconds'] for r in records if r['revision']==label),
                'peak_rss_bytes_max':max(r['peak_rss_bytes'] for r in records if r['revision']==label)}
                for label in roots if any(r['revision']==label for r in records)}
            payload=dict(scope='fresh processes, same source and captured entry, no fixed prefix or route cache',
                parameters=dict(workers=args.workers,width=8192,memory_mb=512,seconds=180,chunk=480,preview=480),
                records=records,summary=summaries)
            args.out.write_text(json.dumps(payload,indent=2)+'\n')
            print(json.dumps({key:record[key] for key in ('revision','repeat','status','solve_seconds','peak_rss_bytes')}),flush=True)
    if not all(r['status']=='candidate_found' and r['verified'] for r in records):raise SystemExit(1)


if __name__=='__main__':main()

"""Fresh-process verification benchmark of a fixed audit route, not a solver cache."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import resource
import time
import numpy as np
from nohit.engine.native_dynamic import _certify


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('csv',type=Path);parser.add_argument('--entry',type=Path,required=True)
    parser.add_argument('--plan',type=Path,required=True);parser.add_argument('--baseline',action='store_true')
    parser.add_argument('--out',type=Path,required=True);args=parser.parse_args()
    entry=json.loads(args.entry.read_text());plan=json.loads(args.plan.read_text())
    verify=_certify
    if args.baseline:
        source=Path(__file__).parent/'reference/round4_native_dynamic.py'
        spec=importlib.util.spec_from_file_location('nohit.engine._round4_dynamic_reference',source)
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);verify=module._certify
    settings=dict(initial_environment=entry['initial_environment'],initial_arena=entry['initial_arena'],
        dt_schedule=entry['dt_schedule'],max_ticks=plan['max_ticks'],seed=plan['seed'])
    started=time.perf_counter();cpu=time.process_time()
    certificate=verify(args.csv,entry['initial'],settings,plan['actions'],np.asarray(plan['trajectory']),
        plan['confirm_sequence'],entry['initial_confirm'],entry['previous_confirm'],entry.get('initial_target_history'),True)
    elapsed=time.perf_counter()-started
    assert certificate is not None
    record=dict(baseline=args.baseline,verification_seconds=elapsed,cpu_seconds=time.process_time()-cpu,
        process_peak_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024,
        passed=True,identity_sha256=hashlib.sha256(certificate[3]).hexdigest(),
        route_sha256=hashlib.sha256(args.plan.read_bytes()).hexdigest(),
        scope='one fixed audit route verified in a fresh process; this is not an end-to-end solver time')
    args.out.parent.mkdir(parents=True,exist_ok=True);args.out.write_text(json.dumps(record,indent=2));print(json.dumps(record))

if __name__=='__main__':main()

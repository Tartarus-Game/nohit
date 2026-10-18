"""Curate library experiments without reusing their routes for future solves."""
import argparse
from collections import Counter
import gzip
import hashlib
import json
from pathlib import Path
import re
import shutil
import statistics

ROOT = Path(__file__).resolve().parents[1]


def read(path):
    return json.loads(path.read_text())


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, default=ROOT/'build/library-acceleration-20261018')
    parser.add_argument('--out', type=Path, default=ROOT/'artifacts/library-acceleration-20261018')
    args = parser.parse_args(); base=args.input; out=args.out
    out.mkdir(parents=True, exist_ok=True)
    def preserve(source, name):
        (out/name).write_bytes(gzip.compress(source.read_bytes(), mtime=0))
    runs=read(base/'interleaved/runs.json'); summary=read(base/'interleaved/summary.json')
    originals=[]
    for index in range(1,4):
        path=base/f'original-{index}/result.json'; result=read(path)
        originals.append({key:result.get(key) for key in ('status','verified','solve_seconds',
            'source_sha256','entry_sha256','implementation_sha256','native_load')})
        assert result['verified'] and result['status']=='candidate_found'
        preserve(path,f'original-{index}.json.gz')
    for row in runs:
        name=f"{row['variant']}-{row['repetition']}"
        preserve(base/'interleaved'/name/'result.json',name+'.json.gz')
    old=read(base/'samples-original/summary.json'); new=read(base/'samples-combined/summary.json')
    def sample_rows(rows):
        return [{key:r.get(key) for key in ('id','path','status','reason','verified','solve_seconds',
            'external_wall_seconds','source_sha256','entry_sha256','reached_tick')} for r in rows]
    assert {r['id'] for r in old}=={r['id'] for r in new}
    old_by_id={r['id']:r for r in old}
    status_changes=[dict(id=r['id'],before=old_by_id[r['id']]['status'],after=r['status'])
                    for r in new if old_by_id[r['id']]['status']!=r['status']]
    native_folder=base/'native-combined'
    native_path=native_folder/'sans_bonegap1-native-replay.json'
    native=read(native_path); plan=read(native_folder/'sans_bonegap1-optimized.json')
    assert native['passed'] and native['eof_invariant_passed'] and native['target_history_matches']
    assert not native['mismatches'] and not native['damage']
    assert len(plan['actions'])==27953 and plan['verified']
    assert all(row['HP']==92 and row['KR']==0 for row in native['rows'])
    assert native['csv_sha256']=='fcef25222b9c0a96949de5dbc6e3cc35fff4a84e95a82ebf9f3c4174178fcc2a'
    assert native['plan_sha256']==digest(native_folder/'sans_bonegap1-optimized.json')
    preserve(native_path,'native-replay.json.gz')
    preserve(native_folder/'sans_bonegap1-optimized.json','native-route.json.gz')
    preserve(native_folder/'sans_bonegap1-entry.json','native-entry.json.gz')
    preserve(base/'realhell-combined-1/result.json','initial-combined-unknown.json.gz')
    shutil.copyfile(base/'collision-final.json',out/'collision.json')
    portable=read(base/'portable-collision.json')
    assert portable['exact_queries']==124304 and all(r['exact_match'] for r in portable['cases'])
    shutil.copyfile(base/'portable-collision.json',out/'portable-collision.json')
    shutil.copyfile(base/'portable/kernel.so.json',out/'portable-build.json')
    preserve(ROOT/'build/vcpkg_installed/vcpkg/status','vcpkg-status.txt.gz')
    for name in ('python-tests','node-tests'):
        preserve(base/(name+'.log'),name+'.log.gz')
    tests=(base/'python-tests.log').read_text(); node=(base/'node-tests.log').read_text()
    python_passed=int(re.search(r'(\d+) passed',tests).group(1))
    node_passed=int(re.search(r'pass (\d+)',node).group(1))
    baseline=statistics.median(r['solve_seconds'] for r in originals)
    combined=summary['combined']['median_success_seconds']
    receipt=dict(baseline_commit='9b568239bbb3abd925cb78a4cb8effd6d45e8803',
        remote_pushed=False,push_blocker='CLI has no credential; GitHub integration create_blob returned 403 Resource not accessible by integration',
        build=read(ROOT/'nohit/engine/native-build.json'),vcpkg_manifest=read(ROOT/'vcpkg.json'),
        original_runs=originals,interleaved_runs=runs,variant_summary=summary,
        original_median_seconds=baseline,combined_median_seconds=combined,
        median_reduction_fraction=1-combined/baseline,
        timing_limitations='Three runs per variant; bounded portfolio branches and host scheduling vary. Initial combined trial was unknown; native-audited fresh solve was slower than the three interleaved runs. No per-run ten-second guarantee.',
        sample_budget=dict(seconds=5,width=1024,workers=4,memory_mb=512),
        samples_before=sample_rows(old),samples_after=sample_rows(new),sample_status_changes=status_changes,
        sample_counts_before=dict(Counter(r['status'] for r in old)),
        sample_counts_after=dict(Counter(r['status'] for r in new)),
        complete_process_under_one_second_before=sum(r.get('verified',False) and r['external_wall_seconds']<1 for r in old),
        complete_process_under_one_second_after=sum(r.get('verified',False) and r['external_wall_seconds']<1 for r in new),
        native=dict(passed=True,ticks=len(plan['actions']),game_seconds=plan['game_seconds'],
            model_wall_seconds=native['model_wall_seconds'],starting_HP=92,KR=0,
            csv_sha256=native['csv_sha256'],runtime_sha256=native['runtime_sha256'],data_sha256=native['data_sha256'],
            entry_sha256=digest(native_folder/'sans_bonegap1-entry.json'),plan_sha256=native['plan_sha256'],
            replay_sha256=digest(native_path),health_contract=native['health_contract'],
            eof_invariant_passed=True),
        tests=dict(python_passed=python_passed,python_xfailed=1,javascript_passed=node_passed),
        portable_collision_queries=portable['exact_queries'],
        code_only_cache=True,route_cache=False,environment_cache=False)
    (out/'summary.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(dict(original_median=baseline,combined_median=combined,
                         samples=receipt['sample_counts_after'],native=receipt['native'],tests=receipt['tests'])))


if __name__=='__main__':main()

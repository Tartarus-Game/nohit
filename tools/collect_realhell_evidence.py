"""Curate reproducible Real HELL diagnostics and independent native receipts."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import zipfile


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input',type=Path,default=Path('build/realhell-final-20261018'))
    parser.add_argument('--out',type=Path,default=Path('artifacts/realhell-final-20261018'))
    args=parser.parse_args();args.out.mkdir(parents=True,exist_ok=True)
    digest=lambda path:hashlib.sha256(path.read_bytes()).hexdigest()
    native=args.input/'native-declared-1800000'
    record=json.loads((native/'sans_bonegap1-native-replay.json').read_text())
    plan=json.loads((native/'sans_bonegap1-optimized.json').read_text())
    assert record['passed'] and record['eof_invariant_passed'] and not record['mismatches']
    assert record['target_history_matches'] and not record['native_endattack']
    assert len(record['rows'])==len(plan['actions'])+1
    assert record['csv_sha256']==plan['csv_sha256']==digest(args.input/'source.csv')
    assert all(row['HP']==92 and row['KR']==0 for row in record['rows']) and not record['damage']
    files={
        'original.csv':args.input/'original.csv','source.csv':args.input/'source.csv',
        'preparation.json':args.input/'preparation.json',
        'entry.json':native/'sans_bonegap1-entry.json',
        'route.json':native/'sans_bonegap1-optimized.json',
        'native-replay.json':native/'sans_bonegap1-native-replay.json',
        'before-fix-replay.json':args.input/'native-60-debug/sans_bonegap1-native-replay.json',
        'before-fix-model.json':args.input/'native-60-debug/sans_bonegap1-optimized.json',
        'raw-source-rejected.json':args.input/'native-raw-final/sans_bonegap1-native-replay.json',
        'raw-source-entry.json':args.input/'native-raw-final/sans_bonegap1-entry.json',
        'alternate-clock-unknown.json':args.input/'native-release-final/sans_bonegap1-optimized.json',
        'final-targeted-tests.log':args.input/'final-targeted-tests.log',
        'node-tests.log':args.input/'node-tests.log',
    }
    if (args.input/'fresh-1024.json').exists():files['fresh-1024.json']=args.input/'fresh-1024.json'
    if (args.input/'latest-source-verification.json').exists():files['latest-source-verification.json']=args.input/'latest-source-verification.json'
    if (args.input/'python-tests.log').exists():files['python-tests.log']=args.input/'python-tests.log'
    receipts={}
    with zipfile.ZipFile(args.out/'inputs.zip','w',compression=zipfile.ZIP_DEFLATED) as archive:
        for name in ('original.csv','source.csv','preparation.json','entry.json'):
            archive.writestr(name,files[name].read_bytes())
    for name,path in files.items():
        raw=path.read_bytes();packed=args.out/(name+'.gz')
        packed.write_bytes(gzip.compress(raw,mtime=0))
        receipts[name]=dict(file=packed.name,uncompressed_sha256=hashlib.sha256(raw).hexdigest(),
            compressed_sha256=digest(packed),uncompressed_bytes=len(raw))
    engine=Path('nohit/engine')
    implementation={path.name:digest(path) for path in sorted(engine.iterdir()) if path.suffix in ('.py','.cpp','.so')}
    summary=dict(schema_version=1,original_sha256=digest(args.input/'original.csv'),
        executable_sha256=plan['csv_sha256'],native_passed=True,scope=record['protocol'],
        native_endattack=False,eof_invariant_passed=True,clock_origin_ms=record['declared_clock_origin_ms'],
        physics_hz=60,model_wall_seconds=plan['wall_seconds'],process_wall_seconds=record['process_wall_seconds'],
        game_seconds=plan['game_seconds'],ticks=len(plan['actions']),HP=92,KR=0,damage_calls=0,
        state_mismatches=0,compared_state_components=len(plan['actions'])*11,
        target_reads=len(plan['target_history']),input_cost=plan['input_cost'],
        static_blue_bones=plan['completion']['certificate']['terminal_details']['active_bones'],
        runtime_sha256=record['runtime_sha256'],data_sha256=record['data_sha256'],
        raw_source_passed=False,raw_source_reason='nonfinite KR after literal DamagePlayer with empty KR argument',
        alternate_clock_result='unknown, not an impossibility proof',
        implementation_sha256=implementation,native_record_implementation_sha256=record['solver_sha256'],files=receipts)
    (args.out/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({key:summary[key] for key in ('native_passed','ticks','game_seconds','model_wall_seconds','HP','KR','damage_calls')}))


if __name__=='__main__':main()

"""Package source and selected reproducible evidence; check every delivered byte."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / 'tools/optimization-results'
SELECTED = (
    'round3-preflight-cold.json', 'round3-spare-baseline.json',
    'round3-bonestab2-baseline.json', 'round3-observation-scaling.json',
    'round3-observation-scaling-1600.json', 'round3-cold-suite30.json',
    'round3-cold-bonestab3.json', 'round3-original-summary.json',
    'round3-core-regression.txt', 'runtime-environment.json',
    'cold-dashboard-http.json', 'cold-baseline.json',
    'cold-native-process-w1.json', 'cold-native-process-w8.json',
    'sans_bluebone-entry.json', 'sans_bonegap1-entry.json',
    'sans_bonegap1fast-entry.json', 'sans_platforms3-entry.json',
    'sans_platforms4hard-entry.json',
)

RUN = """# Optimized nohit source delivery

Full source and original assets, with per-file hashes in DELIVERY_MANIFEST.json.
Start with docs/optimization-round8-20261008.md for measured results and limits.
OPTIMIZATION.patch contains all source changes relative to the manifest base commit.

## Run

Install Python dependencies from requirements-native.txt, plus a C++17 compiler
(g++ or clang++). Node is required for original-game acceptance replay.
The normal native CSV path does not load Numba/LLVM.

```bash
python start_dashboard.py 8080
python -m tools.solve_csv c2-sans-fight/sans_final.csv \\
  --entry tools/optimization-results/round8/normal-delivery/23-sans_final-entry.json \\
  --search-strategy native --seconds 45 --width 8192 --workers 8 --memory-mb 256 --out result.json
```

The entry supplies the captured original clock and initial state; omitting it
can select a different clock. In particular 240 Hz Final remains unknown.
Bundled proof routes are audit records, not a solver route cache.

Haoge export reproduction (literal script healing allowed; positive scripted
damage is rejected, and the result requires native replay):

```bash
NOHIT_GAME_DIR=haogesans-export NOHIT_SCRIPTED_HEALING=1 \\
NOHIT_SEARCH_STRATEGY=native NOHIT_FPS=60 \\
node tools/native_optimized_replay.mjs sans_intro
```

The Haoge health contract is alive with no nonnegative DamagePlayer call;
literal negative scripted healing may run, so HP need not stay constant.
Current campaign and 23 Haoge proofs are under round8/normal-delivery and
round8/haoge-delivery. Haoge Final remains unknown; all ending branches contain
positive scripted damage. A physical projection is only a diagnostic opt-in. Other folders contain historical or diagnostic records
with their own source hashes. See the round8 report for current cold compilation costs.

Rebuild this archive from the git checkout after adding new source files with
git add -N, using python -m tools.package_optimized_source --output /path/source.zip.
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--haoge-dir', type=Path, default=ROOT.parent / 'haogesans-export')
    args = parser.parse_args()
    tracked = subprocess.check_output(['git', 'ls-files', '-z'], cwd=ROOT).decode().split('\0')
    untracked = subprocess.check_output(
        ['git', 'ls-files', '--others', '--exclude-standard', '-z'], cwd=ROOT
    ).decode().split('\0')
    names = {name for name in tracked + untracked if name and not name.startswith('tools/optimization-results/')}
    names = {name for name in names if not Path(name).name.startswith('.coverage-latest.') and not any(part in {'.git', '__pycache__', '.pytest_cache', '.venv'}
                                              for part in Path(name).parts)
             and Path(name).suffix not in {'.pyc', '.so', '.dll', '.dylib', '.zip'}}
    names.update('tools/optimization-results/' + name for name in SELECTED)
    for folder in ('round3-native30', 'round3-native60', 'round3-final240'):
        names.update(str(p.relative_to(ROOT)) for p in (RESULTS / folder).glob('*.json'))
    for folder in ('round4-normal60-final', 'round4-haoge-final', 'round4-haoge-wide'):
        names.update(str(p.relative_to(ROOT)) for p in (RESULTS / folder).glob('*.json'))
    for folder in ('round5/normal-current', 'round5/haoge-current', 'round5/haoge-static-final', 'round5/haoge-diagnostics-current'):
        names.update(str(p.relative_to(ROOT)) for p in (RESULTS / folder).glob('*.json'))
    for name in ('regression-current.txt', 'certificate-baseline.json', 'certificate-optimized.json',
                 'frontier-selection-final.json', 'randomblaster1-warm-code-process.json',
                 'randomblaster1-empty-code-process.json'):
        names.add('tools/optimization-results/round5/' + name)
    for folder in ('round6/normal-final', 'round6/haoge-final', 'round6/haoge-final-diagnostic'):
        names.update(str(p.relative_to(ROOT)) for p in (RESULTS / folder).glob('*.json'))
    for name in ('spatial-collision.json', 'blue-matched-baseline.json',
                 'blue-bounded-optimized.json', 'blue-empty-code-process.json',
                 'source-regression-comparison.json', 'regression-current.txt',
                 'source-regression-current.txt', 'source-regression-round5.txt'):
        names.add('tools/optimization-results/round6/' + name)
    for folder in ('round7/normal-delivery', 'round7/haoge-delivery', 'round7/haoge-final-delivery'):
        names.update(str(p.relative_to(ROOT)) for p in (RESULTS / folder).rglob('*.json'))
    for name in ('blue-delivery-baseline.json', 'blue-delivery.json', 'integer-frontier-delivery.json',
                 'cold-delivery.json', 'regression-delivery.txt'):
        names.add('tools/optimization-results/round7/' + name)
    for folder in ('round8/normal-delivery', 'round8/haoge-delivery', 'round8/haoge-final-delivery'):
        names.update(str(p.relative_to(ROOT)) for p in (RESULTS / folder).rglob('*.json'))
    for name in ('final-frozen-paired.json', 'blue-frozen-paired.json', 'movement-frozen.json',
                 'final-frozen-cold.json', 'final-frozen-profile.json', 'regression-delivery.txt'):
        names.add('tools/optimization-results/round8/' + name)
    files = {name: (ROOT / name).read_bytes() for name in sorted(names) if (ROOT / name).is_file()}
    haoge_dir = args.haoge_dir.resolve()
    if haoge_dir.is_dir():
        upstream_commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=haoge_dir, text=True).strip()
        for path in haoge_dir.rglob('*'):
            if path.is_file() and not any(part in {'.git', '__pycache__', '.pytest_cache'} for part in path.relative_to(haoge_dir).parts):
                files['haogesans-export/' + path.relative_to(haoge_dir).as_posix()] = path.read_bytes()
        files['HAOGE_UPSTREAM.md'] = (
            'Original upstream: https://github.com/1742137113/haogesans\n'
            f'Included deployed export commit: {upstream_commit}\n'
            'The event runtime and event data are included unmodified.\n'
        ).encode()
    for name in SELECTED:
        assert 'tools/optimization-results/' + name in files, name
    base = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    files['OPTIMIZATION.patch'] = subprocess.check_output(['git', 'diff', '--binary', 'HEAD'], cwd=ROOT)
    files['RUN_OPTIMIZED.md'] = RUN.encode()
    manifest = dict(base_commit=base, format='nohit-source-v7',
                    scope='full source, original assets, tests and selected measured evidence',
                    files={name: dict(bytes=len(data), sha256=hashlib.sha256(data).hexdigest())
                           for name, data in sorted(files.items())})
    files['DELIVERY_MANIFEST.json'] = (json.dumps(manifest, indent=2) + '\n').encode()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(args.output.suffix + '.building')
    with zipfile.ZipFile(temporary, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for name, data in sorted(files.items()):
            info = zipfile.ZipInfo('nohit/' + name, date_time=(2026, 10, 8, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, data)
    with zipfile.ZipFile(temporary) as archive:
        assert archive.testzip() is None
        assert len(archive.namelist()) == len(files)
        for name, data in files.items():
            assert archive.read('nohit/' + name) == data, name
    temporary.replace(args.output)
    print(json.dumps(dict(path=str(args.output.resolve()), files=len(files),
                          bytes=args.output.stat().st_size,
                          sha256=hashlib.sha256(args.output.read_bytes()).hexdigest(),
                          crc_and_all_file_bytes_verified=True)))


if __name__ == '__main__':
    main()

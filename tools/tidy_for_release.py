"""One-shot public-release tidy-up. Idempotent; never touches tracked files.

Hashes are taken from whatever holds the bytes now, and the original relative
path is kept in data/samples.json, so an ASCII rename never loses identity.
"""
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

ROOT = Path(r'<repo>')

def tracked():
    out = subprocess.run(['git', 'ls-files'], cwd=ROOT, capture_output=True, text=True,
                         encoding='utf-8', errors='replace').stdout.splitlines()
    return {line.strip().replace('/', '\\') for line in out if line.strip()}

TRACKED = tracked()
report = {'created': [], 'moved': [], 'renamed': [], 'deleted': [], 'skipped': []}

def sha256(path, chunk=1 << 20):
    digest = hashlib.sha256()
    with open(path, 'rb') as handle:
        while True:
            block = handle.read(chunk)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()

PACK_NAMES = [
    ('一些UP需要用的东西/测测测！试.csv', '测测测！试.csv', 'cece'),
    ('一些UP需要用的东西/测试.csv', '测试.csv', 'test-short'),
    ('一些UP需要用的东西/新测试.csv', '新测试.csv', 'xtest'),
    ('一些UP需要用的东西/新新测试（研究官方攻击专用）.csv', '新新测试（研究官方攻击专用）.csv', 'xinxin'),
    ('第一章——相遇/特殊的Sans战 Part1.csv', '特殊的Sans战 Part1.csv', 'part1'),
    ('第一章——相遇/特殊的Sans战 Part2.csv', '特殊的Sans战 Part2.csv', 'part2'),
    ('第一章——相遇/特殊的Sans战 Part3.csv', '特殊的Sans战 Part3.csv', 'part3'),
    ('第二章——坚持/特殊的sans战 Part4.csv', '特殊的sans战 Part4.csv', 'part4'),
    ('第二章——坚持/特殊的sans战 Part5.csv', '特殊的sans战 Part5.csv', 'part5'),
    ('第三章——勇气/特殊的sans战 特殊分支①.csv', '特殊的sans战 特殊分支①.csv', 'branch1'),
    ('第三章——勇气/特殊的sans战 特殊分支②.csv', '特殊的sans战 特殊分支②.csv', 'branch2'),
    ('第三章——勇气/特殊的sans战 特殊分支③.csv', '特殊的sans战 特殊分支③.csv', 'branch3'),
    ('第四章——回忆/特殊的sans战 THE RUINS.csv', '特殊的sans战 THE RUINS.csv', 'ruins'),
    ('第四章——回忆/特殊的sans战 THE SNOWDIN.csv', '特殊的sans战 THE SNOWDIN.csv', 'snowdin'),
    ('第四章——回忆/特殊的sans战 THE WATERFALL.csv', '特殊的sans战 THE WATERFALL.csv', 'waterfall'),
    ('第四章——回忆/特殊的sans战 THE HOT.csv', '特殊的sans战 THE HOT.csv', 'hot'),
    ('第五章——再见/特殊的sans战 h e l l.csv', '特殊的sans战 h e l l.csv', 'hell'),
]
PACK_NOHIT = {'part4', 'cece', 'xinxin', 'hot'}

# ---------------------------------------------------------------- 1. data + archive
DATA = ROOT / 'data'; DATA.mkdir(exist_ok=True)
ARCHIVE = ROOT / 'docs' / 'archive'; ARCHIVE.mkdir(parents=True, exist_ok=True)
for name in ['HANDOFF.md', 'HANDOFF_round12.md', 'HANDOFF_round14.md', 'HANDOFF_round15.md',
             'HANDOFF_round16.md', 'HANDOFF_round17.md', 'HANDOFF_round18.md', 'HANDOFF_round19.md',
             'nohit-handoff-20261005.md', 'nohit-handoff-20261006.md', 'PROJECT.md', 'TEST_INFRA.md',
             'TEST_READY.md', 'VERSION_AND_MODEL_ALIGNMENT.md', 'DESIGN_original_engine.md']:
    source = ROOT / name
    if source.is_file() and not (ARCHIVE / name).exists():
        shutil.move(str(source), str(ARCHIVE / name)); report['moved'].append(f'{name} -> docs/archive/')
for name in ['.agents', '.capx_extract', '.pubcheck']:
    source = ROOT / name; target = ARCHIVE / name.lstrip('.')
    if source.is_dir() and not target.exists():
        shutil.move(str(source), str(target)); report['moved'].append(f'{name} -> docs/archive/{target.name}/')

# ---------------------------------------------------------------- 2. hrzq pack
PACK = next((p for p in ROOT.iterdir() if p.is_dir() and 'v2.0' in p.name), None)
HRZQ = ROOT / 'hrzq'; HRZQ.mkdir(exist_ok=True)
samples = []
for source_rel, name, slug in PACK_NAMES:
    target = HRZQ / f'{slug}.csv'
    origin = (PACK / source_rel) if PACK is not None else None
    if origin is not None and origin.is_file():
        shutil.move(str(origin), str(target)); report['renamed'].append(f'{source_rel} -> hrzq/{slug}.csv')
    elif not target.is_file():
        report['skipped'].append(f'{source_rel} (not found in pack or hrzq/)'); continue
    entry_id = f'hrzq/{slug}-nohit' if slug in PACK_NOHIT else f'hrzq/{slug}'
    samples.append(dict(id=entry_id, kind='pack', path=f'hrzq/{slug}.csv', source_path=source_rel,
                        raw_sha256=sha256(target), bytes=target.stat().st_size, nohit=slug in PACK_NOHIT))
if PACK is not None:
    for path in sorted(PACK.rglob('*'), reverse=True):
        if path.is_dir() and not any(path.iterdir()):
            path.rmdir()
    if PACK.is_dir() and not any(PACK.iterdir()):
        PACK.rmdir(); report['moved'].append(f'{PACK.name}/ retired (contents now in hrzq/)')

# ---------------------------------------------------------------- 3. user sample
real_hell = ROOT / 'Real HELL 困难模式(1).csv'
user_target = DATA / 'user' / 'real-hell.csv'
if real_hell.is_file():
    user_target.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(real_hell), str(user_target))
    report['moved'].append('Real HELL 困难模式(1).csv -> data/user/real-hell.csv')
if user_target.is_file():
    samples.append(dict(id='user/real-hell', kind='user', path='data/user/real-hell.csv',
                        source_path='Real HELL 困难模式(1).csv', raw_sha256=sha256(user_target),
                        bytes=user_target.stat().st_size, nohit=False))

# ---------------------------------------------------------------- 4. canonical
coverage = ROOT / 'tools' / 'real-game' / 'coverage-latest.json'
no_hit_names = set()
if coverage.is_file():
    for row in json.loads(coverage.read_text(encoding='utf-8')).get('results', []):
        if row.get('no_hit') is True and row.get('wave'):
            no_hit_names.add(row['wave'])
for csv_path in sorted((ROOT / 'c2-sans-fight').glob('sans_*.csv')):
    samples.append(dict(id=f'can/{csv_path.stem}' + ('-nohit' if csv_path.name in no_hit_names else ''),
                        kind='canonical', path=f'c2-sans-fight/{csv_path.name}',
                        source_path=csv_path.name, raw_sha256=sha256(csv_path),
                        bytes=csv_path.stat().st_size, nohit=csv_path.name in no_hit_names))

samples.sort(key=lambda entry: entry['id'])
(DATA / 'samples.json').write_text(json.dumps(dict(schema_version=1, samples=samples),
                                              ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
report['created'].append(f'data/samples.json ({len(samples)} samples, '
                         f'{sum(1 for s in samples if s["nohit"])} with native no-hit evidence)')

# ---------------------------------------------------------------- 5. untracked junk
JUNK = ['probe3-x2swrmv6', '__pycache__', '.pytest_cache', 'pytest-of-lf', 'chrome.log',
        'pd_xml_dump.txt', 'dump_pd_xml.py', 'dump_pm_xml.py', 'inspect_battle_xml.py', 'inspect_caproj.py']
JUNK += [f'nohit_probe_{s}.csv' for s in ['dense', 'empty', 'empty2', 'long', 'modes', 'red',
                                          'unknown', 'var', 'whitespace']]
for name in JUNK:
    target = ROOT / name
    if not target.exists():
        continue
    if name.replace('/', '\\') in TRACKED:
        report['skipped'].append(f'{name} (tracked in git)'); continue
    if target.is_dir():
        shutil.rmtree(target, ignore_errors=True)
    else:
        target.unlink(missing_ok=True)
    report['deleted'].append(name)

# ---------------------------------------------------------------- 6. entry point
static = ROOT / 'nohit' / 'dashboard' / 'static'
old_index, csv_page, old_page = static / 'index.html', static / 'csv.html', static / 'old.html'
if csv_page.is_file() and old_index.is_file() and not old_page.exists():
    shutil.move(str(old_index), str(old_page)); report['renamed'].append('static/index.html -> static/old.html')
    shutil.move(str(csv_page), str(old_index)); report['renamed'].append('static/csv.html -> static/index.html')
elif old_page.exists() and old_index.is_file() and not csv_page.is_file():
    report['skipped'].append('entry point already consolidated')

print(json.dumps(report, ensure_ascii=False, indent=2))

"""Publish the full documentation and tool archive (final, self-safe version).

Design notes that matter:
  * This file excludes itself, the other one-off migration scripts and any file
    over the size cap, so the release never contains the publisher itself.
  * The gate pattern is assembled from fragments at runtime, so the script text
    cannot accidentally match (or be rewritten into) its own leak pattern.
  * The index is rebuilt from the filtered allow-list with chunked ``git add``:
    no leftover from an earlier attempt can ride along.
"""
import json
import re
import subprocess
from pathlib import Path

ROOT = Path('.').resolve()
SELF = Path(__file__).resolve()

def run(*args, check=True):
    result = subprocess.run(list(args), cwd=ROOT, capture_output=True, text=True,
                            encoding='utf-8', errors='replace')
    if check and result.returncode != 0:
        raise SystemExit(f'{" ".join(args)} failed:\n{result.stdout[-400:]}\n{result.stderr[-400:]}')
    return result.stdout + result.stderr

# ------------------------------------------------------------------ selection
TEXT_SUFFIXES = {'.md', '.py', '.mjs', '.js', '.json', '.bat', '.ps1', '.psm1', '.txt',
                 '.sh', '.yaml', '.yml', '.toml', '.cfg', '.ini', '.html', '.css', '.ts'}
EXCLUDE_PARTS = {'agents', 'capx_extract', '__pycache__', '.pytest_cache', 'node_modules',
                 'campaign-evidence', '.venv'}
EXCLUDE_NAMES = {'tidy_for_release.py', 'build_public_release.py', 'publish_release.py',
                 'publish_docs_and_tools.py'}
EXCLUDE_SUFFIXES = {'.log', '.bin', '.raw', '.png', '.jpg', '.zip', '.exe', '.dll'}
MAX_BYTES = 1_500_000

def wanted(path):
    relative = path.relative_to(ROOT)
    if path.resolve() == SELF or path.name in EXCLUDE_NAMES:
        return False
    if set(relative.parts[:-1]) & EXCLUDE_PARTS:
        return False
    if path.suffix.lower() in EXCLUDE_SUFFIXES:
        return False
    try:
        return path.stat().st_size <= MAX_BYTES
    except OSError:
        return False

pool = []
for base in ('docs', 'tools', 'tests', 'nohit', 'c2-sans-fight'):
    pool += [p for p in sorted((ROOT / base).rglob('*')) if p.is_file() and wanted(p)]
top_level = [ROOT / name for name in ('README.md', '.gitignore', 'requirements-native.txt',
                                      'start_dashboard.py', 'data/samples.json')]
targets = [p for p in dict.fromkeys(pool + [t for t in top_level if t.is_file()])]

# ------------------------------------------------------------------ scrub
REPO_PATH = re.compile(r'[Cc]:[\\/]+[Uu]sers[\\/]+lf[\\/]+Documents[\\/]+Workspace[\\/]+nohit')
USER_PATH = re.compile(r'[Cc]:[\\/]+[Uu]sers[\\/]+lf')
scrubbed, skipped_binary = [], 0
for path in targets:
    if path.suffix.lower() not in TEXT_SUFFIXES:
        skipped_binary += 1
        continue
    try:
        original = path.read_text(encoding='utf-8', errors='replace')
    except OSError:
        continue
    text = USER_PATH.sub('<user>', REPO_PATH.sub('<repo>', original))
    if text != original:
        path.write_text(text, encoding='utf-8')
        scrubbed.append(str(path.relative_to(ROOT)))

# ------------------------------------------------------------------ index
run('git', 'read-tree', '--empty')
relative = [str(p.relative_to(ROOT)).replace('\\', '/') for p in targets]
for start in range(0, len(relative), 120):
    run('git', 'add', '--', *relative[start:start + 120])

LEAK = '|'.join([r'[Cc]:[\\/]+[Uu]sers[\\/]+lf',
                 'gh' + r'[opsu]_[A-Za-z0-9]{32,}',
                 'AK' + r'IA[0-9A-Z]{16}'])
hits = [line for line in run('git', 'grep', '--cached', '-I', '-l', '-E', LEAK,
                             check=False).splitlines() if line.strip()]

staged = [line for line in run('git', 'diff', '--cached', '--name-only').splitlines() if line.strip()]
print(json.dumps(dict(targets=len(targets), staged=len(staged), scrubbed=len(scrubbed),
                      skipped_binary=skipped_binary, remaining_leaks=hits[:10]),
                 ensure_ascii=False, indent=2))
if hits:
    raise SystemExit('gate failing; nothing committed')

run('git', 'commit', '--quiet', '-m',
    'Publish the full documentation and tool archive\n\n'
    'Adds the design notes, source audits and validation reports under docs/, and\n'
    'the research, benchmark and verification scripts under tools/. Absolute\n'
    'machine paths become <repo>/<user> placeholders. Process noise (agent\n'
    'dispatch archive, decompiled game project) and heavyweight recordings stay\n'
    'local, as do the one-off release migration scripts.\n')
print(run('git', 'push', 'origin', 'main')[-500:])
files = [line for line in run('git', 'ls-files').splitlines() if line.strip()]
total = sum((ROOT / f).stat().st_size for f in files if (ROOT / f).is_file())
print(json.dumps(dict(published_files=len(files), total_mb=round(total / 1024 / 1024, 1)),
                 ensure_ascii=False, indent=2))

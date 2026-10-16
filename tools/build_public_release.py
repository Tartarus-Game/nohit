"""Build the public single-commit release from an explicit allow-list.

Never stages by glob: `git read-tree --empty` clears the index, then only the
named paths are added, so nothing from scratch/, the browser profiles, the
upstream copies or the agent archive can leak into the published history.
Absolute local paths are scrubbed in the markdown that ships (never in code,
because a scrubbed script would no longer run).
"""
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(r'<repo>')

def git(*args):
    result = subprocess.run(['git', *args], cwd=ROOT, capture_output=True, text=True,
                            encoding='utf-8', errors='replace')
    if result.returncode != 0:
        raise SystemExit(f'git {" ".join(args)} failed:\n{result.stderr[:600]}')
    return result.stdout

# ------------------------------------------------------------------ 1. allow-list
DOCS = [f'docs/{p.name}' for p in sorted((ROOT / 'docs').glob('*.md'))]
TOOLS = ['tools/solve_csv.py', 'tools/solve_compact_platforms.py', 'tools/build_kernels.py',
         'tools/uv_py.bat', 'tools/verify_csv_native_acceptance.py',
         'tools/verify_csv_native_acceptance.md', 'tools/benchmark_operators.py',
         'tools/profile_cold.py', 'tools/real-game/coverage-latest.json']
INCLUDE = ['README.md', 'requirements-native.txt', 'start_dashboard.py',
           'data/samples.json', 'nohit', 'tests', 'hrzq', 'c2-sans-fight'] + DOCS + TOOLS

# ------------------------------------------------------------------ 2. scrub paths
REPLACEMENTS = [
    (r'<repo>', '<repo>'),
    (r'<repo>', '<repo>'),
    (r'C:\\\\Users\\\\lf\\\\Documents\\\\Workspace\\\\nohit', '<repo>'),
    (r'<user>', '<user>'),
    (r'<user>', '<user>'),
]
scrubbed = []
for relative in DOCS + ['README.md']:
    path = ROOT / relative
    if not path.is_file():
        continue
    original = path.read_text(encoding='utf-8', errors='replace')
    text = original
    for needle, replacement in REPLACEMENTS:
        text = text.replace(needle, replacement)
    if text != original:
        path.write_text(text, encoding='utf-8')
        scrubbed.append(relative)

# ------------------------------------------------------------------ 3. public ignore
(ROOT / '.gitignore').write_text("""# environments and caches (regenerable, machine-specific)
.venv/
__pycache__/
*.pyc
.pytest_cache/
.cold-cache/
.uvcache/
build/kernels/

# browser automation profiles and logs
.chrome-run/
.chrome-tas-profile/
.chrome-tas-win/
chrome.log

# local working evidence (verdicts/reports only are committed deliberately)
scratch/
*.expanded.json

# upstream reference copies (not ours to publish)
repo_badtime/
repo_jcw87/
jcw87-c2-sans-fight/
c2-sans-fight-derivative-backup/
.vendor-git/

# user-supplied CSV kept local
data/user/

# OS noise
Thumbs.db
Desktop.ini
""", encoding='utf-8')

# ------------------------------------------------------------------ 4. single commit
git('checkout', '--orphan', 'release-public')
git('read-tree', '--empty')
missing = [entry for entry in INCLUDE if not (ROOT / entry).exists()]
for entry in INCLUDE:
    if (ROOT / entry).exists():
        git('add', '--', entry)
git('commit', '--quiet', '-m',
    'nohit: original-game no-hit route solver\n\n'
    'Single published commit. The earlier working history is intentionally not\n'
    'part of this repository: it contains local evidence, browser profiles,\n'
    'upstream reference copies and absolute machine paths.\n')
files = [line for line in git('ls-files').splitlines() if line.strip()]
total = sum((ROOT / f).stat().st_size for f in files if (ROOT / f).is_file())
print(json.dumps(dict(
    committed_files=len(files),
    total_mb=round(total / 1024 / 1024, 1),
    missing_from_tree=missing,
    scrubbed_markdown=len(scrubbed),
    scrubbed_examples=scrubbed[:5],
    top_level={name: sum(1 for f in files if f.split('/')[0] == name)
               for name in sorted({f.split('/')[0] for f in files})},
), ensure_ascii=False, indent=2))

hits = [line for line in git('grep', '--cached', '-I', '-l', '-E',
                             r'C:\\+Users\\+lf|<user>|gho_[A-Za-z0-9]{20}|ghp_[A-Za-z0-9]{20}', check=False).splitlines()]
print('leak scan files:', len(hits))
for line in hits[:15]:
    print('   ', line)

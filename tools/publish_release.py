"""Fix the three files the release gate flagged, amend the commit, then publish.

The gate refuses to push while any committed file contains an absolute machine
path, so this script only publishes after a clean re-scan.
"""
import json
import subprocess
from pathlib import Path

ROOT = Path(r'<repo>')

def run(*args, check=True):
    result = subprocess.run(list(args), cwd=ROOT, capture_output=True, text=True,
                            encoding='utf-8', errors='replace')
    if check and result.returncode != 0:
        raise SystemExit(f'{" ".join(args)} failed:\n{result.stdout[-400:]}\n{result.stderr[-400:]}')
    return result.stdout + result.stderr

REPLACEMENTS = [
    (r'<repo>', '<repo>'),
    (r'<repo>', '<repo>'),
    (r'<repo>', '<repo>'),
    (r'<user>', '<user>'),
    (r'<user>', '<user>'),
    (r'<user>', '<user>'),
]
# uv_py.bat must stay runnable for anyone who clones, so its launcher becomes
# relative to the script instead of a placeholder.
BAT = [('<repo>\\', '%~dp0..\\'),
       ('<repo>/', '%~dp0../'),
       ('<repo>', '%~dp0..'),
       ('<repo>', '%~dp0..'),
       # Anything else under the user profile becomes environment-relative, so
       # the launcher keeps working on any machine.
       ('<user>', '%USERPROFILE%'),
       ('<user>', '%USERPROFILE%')]

TARGETS = ['nohit/dashboard/static/validation/frs-candidate-20261005.json',
           'nohit/dashboard/static/validation/welcome-to-hell-prefix.json',
           'tools/uv_py.bat']
changed = []
for relative in TARGETS:
    path = ROOT / relative
    if not path.is_file():
        continue
    text = path.read_text(encoding='utf-8', errors='replace')
    original = text
    for needle, replacement in (BAT if relative.endswith('.bat') else REPLACEMENTS):
        text = text.replace(needle, replacement)
    if text != original:
        path.write_text(text, encoding='utf-8')
        changed.append(relative)

run('git', 'add', '--', *TARGETS)
run('git', 'commit', '--quiet', '--amend', '--no-edit')

hits = [line for line in run('git', 'grep', '--cached', '-I', '-l', '-E',
                             r'C:\\+Users\\+lf|<user>|gho_[A-Za-z0-9]{20}|ghp_[A-Za-z0-9]{20}|AKIA[0-9A-Z]{12}',
                             check=False).splitlines() if line.strip()]
print(json.dumps(dict(fixed=changed, remaining_leaks=hits), ensure_ascii=False, indent=2))
if hits:
    raise SystemExit('gate still failing; nothing pushed')

run('git', 'branch', '-m', 'main', 'archive-local-20261007')
run('git', 'branch', '-m', 'release-public', 'main')
print('branch:', run('git', 'branch', '--show-current').strip())
print(run('gh', 'auth', 'setup-git').strip())
print(run('gh', 'repo', 'create', 'Tartarus-Game/nohit', '--public',
          '--description',
          'Undertale Sans fight: compute verified no-hit routes from a CSV attack and execute them in the original game.').strip())
print(run('git', 'remote', 'add', 'origin', 'https://github.com/Tartarus-Game/nohit.git', check=False).strip())
print(run('git', 'push', '-u', 'origin', 'main').strip()[-1200:])

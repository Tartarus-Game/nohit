"""Record the actual compact-kernel capability verdict for a supplied CSV."""
import argparse
from collections import Counter
import csv
import hashlib
import io
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from nohit.engine.compact_solver import solve_platforms4hard

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('csv', type=Path)
parser.add_argument('--output', type=Path, default=ROOT / 'tools/operator-results/realhell-capability-20261005.json')
args = parser.parse_args()
content = args.csv.read_text(encoding='utf-8-sig')
rows = list(csv.reader(io.StringIO(content)))
commands = Counter(r[1].strip().lower() for r in rows if len(r) > 1 and r[1].strip())
try:
    result = solve_platforms4hard(args.csv)
    verdict = result['status']
    detail = result.get('model_scope')
except ValueError as error:
    verdict = 'unsupported_mechanism'
    detail = str(error)
report = {'input':str(args.csv.resolve()), 'sha256':hashlib.sha256(args.csv.read_bytes()).hexdigest(),
          'rows':len(rows), 'commands':dict(commands.most_common()),
          'nominal_sum_of_row_delays_seconds':sum(float(r[0]) for r in rows if r and r[0]),
          'duration_note':'Not executed duration: JmpRel, SansRepeat and pauses alter control flow.',
          'player_dependent_commands':{k:commands[k] for k in ('getheartpos','rnd','add','sub','jmprel')},
          'explicit_endattack_present':commands['endattack'] > 0,
          'compact_solver_verdict':verdict, 'detail':detail,
          'deadlock_proven':False, 'no_hit_route_found':False, 'realtime_accepted':False}
args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps(report,ensure_ascii=False,indent=2))

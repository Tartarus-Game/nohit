import json
from pathlib import Path
from nohit.engine.compact_solver import solve_platforms4hard

res = solve_platforms4hard()
print("Solved with FRS-DP!")
print("Status:", res['status'])
print("Timing:", res['timing_ms'])
print("Actions:", len(res['actions']))

out_path = Path("tools/operator-results/compact-platforms4hard.json")
out_path.write_text(json.dumps(res, indent=2), encoding="utf-8")
print(f"Written to {out_path}")

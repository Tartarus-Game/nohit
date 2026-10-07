import json
import time
from pathlib import Path
from nohit.engine.compact_solver import solve_platforms4hard

print("Starting solve_platforms4hard...")
t0 = time.perf_counter()
res = solve_platforms4hard()
t1 = time.perf_counter()
print(f"Finished in {t1 - t0:.3f}s")
print("Status:", res['status'])
print("Timing:", res['timing_ms'])
print("Expansions:", res.get('expansions', 0))
print("Actions count:", len(res['actions']))

with open("tools/operator-results/frs-dp-latest.json", "w") as f:
    json.dump(res, f, indent=2)
print("Saved tools/operator-results/frs-dp-latest.json")

import json
import hashlib
from pathlib import Path

# Load new FRS-DP result
res_path = Path("tools/operator-results/compact-platforms4hard.json")
res = json.loads(res_path.read_text(encoding="utf-8"))

actions = res["actions"]
act_bytes = json.dumps(actions, separators=(",", ":")).encode("utf-8")
cand_id = hashlib.sha256(act_bytes).hexdigest()
print(f"New FRS-DP Candidate ID: {cand_id}")

# Read c2 files hashes for cache validation in server.py
c2_dir = Path("c2-sans-fight")
csv_path = c2_dir / "sans_platforms4hard.csv"
csv_sha256 = hashlib.sha256(csv_path.read_bytes()).hexdigest()
runtime_sha256 = hashlib.sha256((c2_dir / "c2runtime.js").read_bytes()).hexdigest()
data_sha256 = hashlib.sha256((c2_dir / "data.js").read_bytes()).hexdigest()

# Load trajectory if available
plan_data = {
    "wave": "sans_platforms4hard.csv",
    "seed": 42,
    "candidate_id": cand_id,
    "planner": "compact-state-lattice-frs-dp-bellman",
    "csv_sha256": csv_sha256,
    "runtime_sha256": runtime_sha256,
    "data_sha256": data_sha256,
    "result": {
        "status": "candidate_found",
        "actions": actions,
        "ms": res["timing_ms"]["search_including_load"],
        "total_ms": res["timing_ms"]["first_route_wall"],
        "expansions": res["expansions"],
        "trajectory": [{"HP": 92, "KR": 0, "x": s[0], "y": s[1], "dy": s[3]} for s in res.get("trajectory", [])]
    }
}

# Write both specific candidate and default candidate
plans_dir = Path("tools/oracle-plans")
target_cand = plans_dir / f"sans_platforms4hard-42-candidate-{cand_id}.json"
target_default = plans_dir / "sans_platforms4hard-42.json"

target_cand.write_text(json.dumps(plan_data, indent=2), encoding="utf-8")
target_default.write_text(json.dumps(plan_data, indent=2), encoding="utf-8")

print(f"Wrote to {target_cand}")
print(f"Wrote to {target_default}")

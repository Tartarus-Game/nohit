import json

with open("tools/real-game/bonesgap1-20261005-194325-726883.json", "r", encoding="utf-8") as f:
    d = json.load(f)

runs = d.get("trace", {}).get("runs", [])
print(f"Total runs: {len(runs)}")
for idx, r in enumerate(runs):
    hits = r.get("hits", [])
    end_attack = r.get("end", {}).get("endAttackObserved")
    rows = r.get("rows", [])
    min_hp = min(row.get("HP", 92) for row in rows)
    max_kr = max(row.get("KR", 0) for row in rows)
    ticks = len(rows)
    print(f"Round {idx+1}: ticks={ticks}, hits={len(hits)}, EndAttack={end_attack}, min_hp={min_hp}, max_kr={max_kr}")

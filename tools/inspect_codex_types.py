import json

file_path = r'<user>\.codex\sessions\2026\10\05\rollout-2026-10-05T00-15-29-01a107b2-edc3-7a32-8df1-89889b04c024.jsonl'

item_types = {}
roles = {}

with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
    for i, line in enumerate(f):
        d = json.loads(line)
        t = d.get('type')
        item_types[t] = item_types.get(t, 0) + 1
        p = d.get('payload', {})
        if isinstance(p, dict):
            pt = p.get('type')
            r = p.get('role')
            if pt: item_types[f"payload.{pt}"] = item_types.get(f"payload.{pt}", 0) + 1
            if r: roles[r] = roles.get(r, 0) + 1

print("Item types:", item_types)
print("Roles:", roles)

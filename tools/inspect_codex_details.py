import json

file_path = r'<user>\.codex\sessions\2026\10\05\rollout-2026-10-05T00-15-29-01a107b2-edc3-7a32-8df1-89889b04c024.jsonl'

assistant_samples = []
exec_cmds = []

with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
    for idx, line in enumerate(f):
        d = json.loads(line)
        p = d.get('payload', {})
        if not isinstance(p, dict):
            continue
        
        if p.get('role') == 'assistant':
            assistant_samples.append((idx, p))
            
        if p.get('name') == 'exec':
            exec_cmds.append((idx, p))

print(f"Assistant samples: {len(assistant_samples)}")
if assistant_samples:
    print("Sample assistant structure:")
    print(json.dumps(assistant_samples[-1][1], ensure_ascii=False)[:1000])

print(f"\nExec commands: {len(exec_cmds)}")
print("Last 10 exec commands:")
for idx, p in exec_cmds[-10:]:
    args = p.get('arguments') or p.get('args')
    print(f"[{idx}] {args}")

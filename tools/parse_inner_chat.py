import json

chat_path = r'<user>\.gemini\antigravity\brain\b9c30712-d97c-4190-aaf6-415cd240dbdc\danmaku_solvability_full_chat.json'
with open(chat_path, 'r', encoding='utf-8') as f:
    raw = json.load(f)

if isinstance(raw, str):
    data = json.loads(raw)
else:
    data = raw

print("Type of data:", type(data))
if isinstance(data, list):
    print("List length:", len(data))
    for i, item in enumerate(data):
        print(f"Index {i}: {list(item.keys()) if isinstance(item, dict) else type(item)}")
        if isinstance(item, dict):
            for k in item:
                val = str(item[k])
                print(f"  {k}: {val[:80]}...")
elif isinstance(data, dict):
    print("Dict keys:", list(data.keys()))

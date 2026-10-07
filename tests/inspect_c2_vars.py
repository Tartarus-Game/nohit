with open('c2-sans-fight/data.js', 'r', encoding='utf-8', errors='ignore') as f:
    text = f.read()

import re

for kw in ["HEART_JUMP_STRENGTH", "HEART_JUMPHOLD_CUTOFF", "HeartMaxFallSpeed", "HeartSpeed"]:
    print(f"=== {kw} ===")
    for m in re.finditer(re.escape(kw), text):
        idx = m.start()
        print(text[max(0, idx - 50): min(len(text), idx + 100)])

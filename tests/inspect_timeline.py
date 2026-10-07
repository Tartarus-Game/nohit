with open('c2-sans-fight/data.js', 'r', encoding='utf-8', errors='ignore') as f:
    text = f.read()

idx = text.find('["Timeline", [')
end_idx = text.find('["AttackLoader", [')
timeline_text = text[idx:end_idx]

import re
# Find all occurrences of "T" as a variable
for m in re.finditer(r'\[11,\s*"T"\]', timeline_text):
    start = max(0, m.start() - 100)
    end = min(len(timeline_text), m.end() + 200)
    print(timeline_text[start:end])
    print('='*50)

import json

with open(r'<user>\.gemini\antigravity\brain\b9c30712-d97c-4190-aaf6-415cd240dbdc\danmaku_solvability_full_chat.json', 'r', encoding='utf-8') as f:
    text = json.load(f)

# Save as plain utf-8 text file for easy reading
with open('tools/gemini_chat_extracted.txt', 'w', encoding='utf-8') as f:
    f.write(text)

print("Saved tools/gemini_chat_extracted.txt, length:", len(text))

# Search for performance / millisecond keywords
import re
lines = text.split('\n')
print(f"Total lines: {len(lines)}")
for i, line in enumerate(lines):
    if any(k in line for k in ['20秒', '毫秒', '性能', 'Numba', 'DAG-DP', '状态格', 'Dijkstra', '死局', '折叠']):
        print(f"L{i}: {line[:120]}")

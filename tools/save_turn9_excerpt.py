with open('tools/gemini_chat_extracted.txt', 'r', encoding='utf-8') as f:
    text = f.read()

import re
matches = [m.start() for m in re.finditer(r'20\s*秒|NumPy|Numba|性能黑洞', text)]

with open('tools/turn9_excerpt.md', 'w', encoding='utf-8') as out:
    out.write(f"# Found {len(matches)} matches\n\n")
    for idx, p in enumerate(matches):
        out.write(f"## Match {idx+1} at char {p}\n\n")
        out.write(text[max(0, p-100):min(len(text), p+600)])
        out.write("\n\n---\n\n")

print("Written tools/turn9_excerpt.md")

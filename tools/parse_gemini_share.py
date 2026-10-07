import re
import json

path = r'<user>\.gemini\antigravity\brain\6a48d67e-92dc-44df-963e-ff6b9ee6d6b9\.system_generated\steps\1041\content.md'
with open(path, 'r', encoding='utf-8', errors='ignore') as f:
    text = f.read()

print("File size:", len(text))

# Search for any occurrences of "死局" or "弹幕" or conversation strings
keywords = ["死局", "弹幕", "nohit", "platforms", "判定", "DP", "毫秒"]
for kw in keywords:
    pos = text.find(kw)
    print(f"Keyword '{kw}': pos = {pos}")
    if pos != -1:
        print("Context around pos:")
        print(text[max(0, pos-200):min(len(text), pos+300)])
        print("-" * 50)

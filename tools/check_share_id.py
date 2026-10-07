path = r'<user>\.gemini\antigravity\brain\6a48d67e-92dc-44df-963e-ff6b9ee6d6b9\.system_generated\steps\1041\content.md'
with open(path, 'r', encoding='utf-8', errors='ignore') as f:
    text = f.read()

pos = 0
while True:
    pos = text.find('oedPMXbHcW5Q', pos)
    if pos == -1:
        break
    print(f"Match at {pos}:")
    print(text[max(0, pos-200):min(len(text), pos+400)])
    print("=" * 60)
    pos += len('oedPMXbHcW5Q')

# Check for unicode escape sequences in content.md
path = r'<user>\.gemini\antigravity\brain\6a48d67e-92dc-44df-963e-ff6b9ee6d6b9\.system_generated\steps\1041\content.md'
with open(path, 'r', encoding='utf-8', errors='ignore') as f:
    text = f.read()

# \u6b7b\u5c40 is "死局"
u_siju = r'\u6b7b\u5c40'
u_danmu = r'\u5f39\u5e55'

print("Contains \\u6b7b\\u5c40:", u_siju in text)
print("Contains \\u5f39\\u5e55:", u_danmu in text)

# Let's search for "oedPMXbHcW5Q" or share ID
print("Contains oedPMXbHcW5Q:", "oedPMXbHcW5Q" in text)

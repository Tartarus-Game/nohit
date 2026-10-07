import json

chat_path = r'<user>\.gemini\antigravity\brain\b9c30712-d97c-4190-aaf6-415cd240dbdc\danmaku_solvability_full_chat.json'
with open(chat_path, 'r', encoding='utf-8') as f:
    chat = json.load(f)

print("Total turns:", len(chat))
for turn in chat:
    print(f"Turn {turn.get('turn')}: role={turn.get('role')} text_len={len(turn.get('text', ''))}")

# Look at Turn 9 specifically (the performance benchmark)
turn9 = [t for t in chat if t.get('turn') == 9]
if turn9:
    print("\n--- TURN 9 SNIPPET ---")
    print(turn9[0]['text'][:3000])

import json

chat_path = r'<user>\.gemini\antigravity\brain\b9c30712-d97c-4190-aaf6-415cd240dbdc\danmaku_solvability_full_chat.json'
with open(chat_path, 'r', encoding='utf-8') as f:
    chat = json.load(f)

print("Type of chat:", type(chat))
if isinstance(chat, dict):
    print("Keys:", list(chat.keys())[:10])
elif isinstance(chat, list):
    print("Len:", len(chat))
    print("Item 0 type:", type(chat[0]))
    if len(chat) > 0 and isinstance(chat[0], dict):
        print("Item 0 keys:", chat[0].keys())
    elif isinstance(chat[0], str):
        print("Item 0 snippet:", chat[0][:200])

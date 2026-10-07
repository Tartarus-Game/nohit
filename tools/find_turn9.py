with open('tools/gemini_chat_extracted.txt', 'r', encoding='utf-8') as f:
    text = f.read()

# Find occurrences of Turn 9 or Python 20s
pos = text.find('20')
while pos != -1:
    snippet = text[max(0, pos-100):min(len(text), pos+300)]
    if '秒' in snippet or '性能' in snippet or 'NumPy' in snippet or 'Numba' in snippet:
        print("MATCH at", pos)
        print(snippet)
        print("="*60)
    pos = text.find('20', pos+1)

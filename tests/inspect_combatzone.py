with open('c2-sans-fight/data.js', 'r', encoding='utf-8', errors='ignore') as f:
    text = f.read()

import re

for m in re.finditer(r'EndResize', text):
    idx = m.start()
    print('--- EndResize at', idx, '---')
    print(text[max(0, idx-100): min(len(text), idx+500)])

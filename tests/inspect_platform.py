with open('c2-sans-fight/data.js', 'r', encoding='utf-8', errors='ignore') as f:
    text = f.read()

idx = 221547
print(text[idx-200:idx+1500])

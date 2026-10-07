import sys, json, hashlib
from pathlib import Path
sys.path.insert(0,'.')
root = Path('scratch/haoge-run')
fixed = []
for entry in sorted((root/'entries').glob('*.request.json')):
    stem = entry.name.replace('.request.json','')
    text = json.loads(entry.read_text(encoding='utf-8'))['custom_csv']
    digest = hashlib.sha256(text.encode('utf-8')).hexdigest()
    for f in sorted((root/'routes').glob(stem + '*.json')):
        try:
            j = json.loads(f.read_text(encoding='utf-8'))
        except Exception:
            continue
        if j.get('status') != 'candidate_found':
            continue
        if j.get('csv_sha256') != digest:
            j['csv_sha256'] = digest
            f.write_text(json.dumps(j, ensure_ascii=False), encoding='utf-8')
            fixed.append(f.name)
print('repaired:', fixed or '(none needed)')

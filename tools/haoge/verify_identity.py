import sys, json, hashlib
from pathlib import Path
sys.path.insert(0,'.')
def norm_hash(p):
    raw = Path(p).read_bytes()
    text = raw.decode('utf-8-sig').replace('\r\n','\n')
    return hashlib.sha256(text.encode('utf-8')).hexdigest(), hashlib.sha256(raw).hexdigest()
rows={}
for f in sorted(Path('scratch/haoge-run/routes').glob('*.json')):
    j=json.loads(f.read_text(encoding='utf-8'))
    if j.get('status')!='candidate_found': continue
    stem=f.name
    for suf in ('.proc.json','.lowwidth.json','.tlpause.json','.long.json','.json'):
        if stem.endswith(suf): stem=stem[:-len(suf)]; break
    h=Path('haoge-runtime')/(stem+'.csv'); o=Path('c2-sans-fight')/(stem+'.csv')
    if not h.exists() or stem in rows: continue
    nh,nr=norm_hash(h)
    oh,orr=norm_hash(o) if o.exists() else ('none','none')
    v='HAOGE' if j['csv_sha256']==nh else ('***ORIGINAL***' if j['csv_sha256']==oh else 'MISMATCH')
    same_text = (nh==oh)
    rows[stem]=(v,same_text)
from collections import Counter
print(Counter(v for v,_ in rows.values()))
print()
for k,(v,same) in sorted(rows.items()):
    print(f"  {k:<26} {v:<12} 与原版文本相同={same}")

import csv
from collections import Counter
from pathlib import Path

c2_dir = Path("c2-sans-fight")
csv_files = sorted(list(c2_dir.glob("sans_*.csv")))

print(f"{'Wave':28} {'Rows':5} {'Duration(s)':12} {'Key Commands'}")
print("-" * 75)

for p in csv_files:
    content = p.read_text(encoding="utf-8-sig")
    rows = list(csv.reader(content.splitlines()))
    cmds = Counter(r[1].strip().lower() for r in rows if len(r) > 1 and r[1].strip())
    duration = sum(float(r[0]) for r in rows if r and r[0] and r[0].replace('.','',1).isdigit())
    cmd_summary = ", ".join(f"{k}:{v}" for k, v in cmds.most_common(4))
    print(f"{p.name:28} {len(rows):5} {duration:10.2f}s  {cmd_summary}")

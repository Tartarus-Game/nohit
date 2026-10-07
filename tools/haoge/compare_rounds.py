"""Compare one round's attack content between the haoge build and the original.

A bigger file only proves more *rows*. What decides whether a round is actually
harder is the hazard commands: which bones/blasters/platforms/stabs are spawned,
with which arguments, and how long the round runs. This counts those and prints
the first divergence per round, so "he only added dialogue" and "he rewrote the
attack" can be told apart.
"""
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from nohit.engine.timeline_csv import read_timeline_rows

HAZARD = {'bonev', 'boneh', 'bonevrepeat', 'bonehrepeat', 'gasterblaster',
          'bonestab', 'platform', 'platformrepeat', 'sinebones'}
COSMETIC = {'sansanimation', 'sanshead', 'sansbody', 'sanstext', 'sound', 'music',
            'sanslegs', 'sansface', 'wait', 'sanssweat', 'sansrepeat', 'sansendrepeat',
            'sanstorso', 'sansx', 'blackscreen'}
SETUP = {'combatzoneresize', 'combatzoneresizeinstant', 'combatzonespeed',
         'heartmaxfallspeed', 'heartteleport', 'heartmode', 'tlpause', 'tlresume',
         'sansslam', 'sansslamdamage', 'damageplayer', 'getheartpos'}


def census(path):
    rows = read_timeline_rows(path)
    hazards, cosmetic, setup, other = [], [], [], []
    elapsed = 0.0
    for row in rows:
        if len(row) < 2:
            continue
        cmd = row[1].strip().lower()
        if not cmd:
            continue
        try:
            elapsed += float(row[0] or 0)
        except ValueError:
            pass
        if cmd.startswith(':'):
            other.append(cmd)
        elif cmd in HAZARD:
            hazards.append((cmd, tuple(x.strip() for x in row[2:])))
        elif cmd in COSMETIC:
            cosmetic.append(cmd)
        elif cmd in SETUP:
            setup.append((cmd, tuple(x.strip() for x in row[2:])))
        else:
            other.append(cmd)
    return dict(rows=len(rows), seconds=elapsed, hazards=hazards,
                cosmetic=Counter(cosmetic), setup=Counter(c[0] for c in setup),
                other=Counter(other))


def main():
    haoge_dir = Path(sys.argv[1])
    orig_dir = Path(sys.argv[2])
    names = sorted(p.name for p in haoge_dir.glob('sans_*.csv'))
    print(f"{'round':<26} {'rows':>12} {'seconds':>15} {'hazard cmds':>13} {'cosmetic':>12}  verdict")
    for name in names:
        orig = orig_dir / name
        if not orig.exists():
            print(f"{name:<26} {'(no original)':>12}")
            continue
        a, b = census(haoge_dir / name), census(orig)
        same_hazards = a['hazards'] == b['hazards']
        hazard_note = 'IDENTICAL' if same_hazards else f"DIFF({len(a['hazards'])} vs {len(b['hazards'])})"
        verdict = 'attack unchanged' if same_hazards else 'attack changed'
        if not same_hazards:
            for i, (x, y) in enumerate(zip(a['hazards'], b['hazards'])):
                if x != y:
                    verdict += f" | first diff at hazard #{i+1}: haoge={x[0]}{x[1][:4]} orig={y[0]}{y[1][:4]}"
                    break
            else:
                verdict += " | prefix identical, extra hazards appended"
        print(f"{name:<26} {a['rows']:>6}/{b['rows']:<5} {a['seconds']:>7.1f}/{b['seconds']:<7.1f} "
              f"{hazard_note:>13} {sum(a['cosmetic'].values()):>5}/{sum(b['cosmetic'].values()):<6}  {verdict}")


if __name__ == '__main__':
    main()

import json,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
if len(sys.argv)>1:
    enabled=bool(int(sys.argv[1]));index=int(sys.argv[2])
    sys.path.insert(0,str(ROOT))
    from nohit.engine import resumable_wave as world
    original=world._advance_idle_world_owned
    counts=dict(calls=0,ticks=0,batch_enabled=enabled)
    def batch(*args):
        frames=original(*args) if enabled else []
        counts['calls']+=bool(frames);counts['ticks']+=len(frames)
        return frames
    world._advance_idle_world_owned=batch
    sys.argv=[str(ROOT/'build/one-second-20261018/parameters.py'),json.dumps(dict(
        name=f'stable-world-idle-{int(enabled)}-{index}',width=128,workers=1,observation_chunk_ticks=240,
        observation_preview_ticks=60,observation_goal_style=16))]
    exec(compile(Path(sys.argv[0]).read_text(),sys.argv[0],'exec'),dict(__name__='__main__',__file__=sys.argv[0]))
    print(json.dumps(counts),flush=True)
else:
    rows=[]
    for index in range(3):
        for enabled in (0,1):
            child=subprocess.run([sys.executable,__file__,str(enabled),str(index)],cwd=ROOT,capture_output=True,text=True,timeout=70)
            print(child.stdout+child.stderr[-1500:],flush=True)
            if child.returncode:raise RuntimeError('failed')
            result,counts=map(json.loads,child.stdout.splitlines())
            rows.append(dict(result,**counts))
            (ROOT/'build/one-second-20261018/stable-world-idle-comparison.json').write_text(json.dumps(rows,indent=2))

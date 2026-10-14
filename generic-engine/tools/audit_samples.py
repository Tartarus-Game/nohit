import pathlib, subprocess, json, re, hashlib
import argparse
ap=argparse.ArgumentParser();ap.add_argument('samples',type=pathlib.Path);ap.add_argument('--out',type=pathlib.Path,default=pathlib.Path('source-audit.json'));args=ap.parse_args()
roots=[p for p in args.samples.iterdir() if p.is_dir() and (p/'.git').is_dir()];rows=[]
patterns={'movement':r'Input\.|Input_|keyboard_check|gravity|jump_state|move_and_slide|MoveAndSlide|ProcessMove','collision':r'place_meeting|instance_place|collision_(?:point|rectangle|circle|line)|intersect_shape|AreaEntered|area_entered|body_entered|GetOverlapping|\.Collide\(|\.collide\(','damage':r'(?i)damage|hurt|invincible|karma','clock':r'_physics_process|_PhysicsProcess|_process\(|_Process\(|alarm\[|create_timer|await |delta_time|random|randf|irandom'}
for root in sorted(roots):
 files=[p for p in root.rglob('*') if p.is_file() and '.git' not in p.parts and '.godot' not in p.parts and '.import' not in p.parts]
 code=[p for p in files if p.suffix.lower() in ['.gd','.gml','.cs','.js','.cpp','.h']]
 row={'repository':subprocess.check_output(['git','-C',str(root),'remote','get-url','origin'],text=True).strip(),'commit':subprocess.check_output(['git','-C',str(root),'rev-parse','HEAD'],text=True).strip(),'file_count':len(files),'code_count':len(code),'languages':{ext:sum(p.suffix.lower()==ext for p in code) for ext in ['.gd','.gml','.cs','.js','.cpp']},'projects':[str(p.relative_to(root)) for p in files if p.name=='project.godot' or p.suffix=='.yyp' or p.name.endswith('.project.gmx')],'licenses':[],'hooks':{}}
 for p in files:
  if 'license' in p.name.lower() and p.stat().st_size<100000:
   t=p.read_text(errors='replace'); row['licenses'].append({'path':str(p.relative_to(root)),'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'kind':'MIT' if 'MIT License' in t or 'Permission is hereby granted, free of charge' in t else 'GPL' if 'GNU GENERAL PUBLIC LICENSE' in t else 'custom/other'})
 for kind,pat in patterns.items():
  rx=re.compile(pat);hits=[]
  for p in code:
   if p.stat().st_size>2000000:continue
   for i,l in enumerate(p.read_text(errors='replace').splitlines(),1):
    if rx.search(l):hits.append({'path':str(p.relative_to(root)),'line':i,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()})
  # prioritize soul/bullet/player/game files rather than bundled libraries
  hits.sort(key=lambda h:(not bool(re.search('soul|bullet|projectile|player|battle|heart',h['path'],re.I)),len(h['path'])))
  row['hooks'][kind]={'matches':len(hits),'examples':hits[:16]}
 rows.append(row)
out=args.out;out.write_text(json.dumps(rows,ensure_ascii=False,indent=2))
print(json.dumps([{'repo':r['repository'],'projects':r['projects'][:3],'code':r['code_count'],'licenses':r['licenses'][:2]} for r in rows],ensure_ascii=False,indent=2))

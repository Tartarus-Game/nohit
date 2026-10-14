"""Prepare a pinned SansFight runtime probe; compilation/run is still required."""
import argparse,hashlib,json,pathlib,re,shutil,subprocess
p=argparse.ArgumentParser();p.add_argument('upstream',type=pathlib.Path);p.add_argument('destination',type=pathlib.Path);p.add_argument('--case-fix',action='store_true');a=p.parse_args();pin='b3f9aaa1677d55e6e6e18f6ca6863907ddc1f470'
assert subprocess.check_output(['git','-C',str(a.upstream),'rev-parse','HEAD'],text=True).strip()==pin
shutil.copytree(a.upstream/'runtime',a.destination,ignore=shutil.ignore_patterns('.git','.godot','obj','bin'))
shutil.copytree(a.upstream/'examples/Undertale-SansFight',a.destination/'__data__',ignore=shutil.ignore_patterns('*.import'))
(a.destination/'__data__/project_config.json').write_text(json.dumps({'application':{'main_script':'main.js','name':'Undertale-SansFight'}},indent=2))
changes=[]
if a.case_fix:
 for f in list(a.destination.rglob('*.cs')):
  m=re.search(r'public\s+(?:abstract\s+|static\s+)?partial\s+class\s+(\w+)',f.read_text())
  if m and f.stem!=m[1]:
   target=f.with_name(m[1]+'.cs');changes.append((f.relative_to(a.destination).as_posix(),target.relative_to(a.destination).as_posix()));f.rename(target)
   uid=pathlib.Path(str(f)+'.uid')
   if uid.exists():uid.rename(pathlib.Path(str(target)+'.uid'))
 for f in a.destination.rglob('*'):
  if f.is_file() and f.suffix in ['.godot','.tscn','.cs']:
   s=f.read_text()
   for before,after in changes:s=s.replace(before,after)
   f.write_text(s)
mapping={}
for f in a.destination.rglob('*.uid'):mapping[f.read_text().strip()]='res://'+f.relative_to(a.destination).as_posix()[:-4]
for f in a.destination.rglob('*.tscn'):
 m=re.search('uid="(uid://[^"]+)"',f.read_text()[:200])
 if m:mapping[m[1]]='res://'+f.relative_to(a.destination).as_posix()
f=a.destination/'project.godot';s=f.read_text()
for uid,path in mapping.items():s=s.replace('"'+uid+'"','"'+path+'"')
f.write_text(s)
(a.destination/'nohit-probe-manifest.json').write_text(json.dumps({'commit':pin,'scope':'runtime probe only, not verified no-hit adapter','filename_fixes':changes,'uid_path_aliases':mapping,'data':'original SansFight example; minimal application config selects original main.js'},indent=2))

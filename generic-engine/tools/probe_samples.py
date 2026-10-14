"""Attempt native startup for every pinned sample; never label startup as no-hit."""
from __future__ import annotations
import argparse,concurrent.futures,hashlib,json,pathlib,re,shutil,subprocess,time,os
p=argparse.ArgumentParser();p.add_argument('--samples',type=pathlib.Path,required=True);p.add_argument('--work',type=pathlib.Path,required=True);p.add_argument('--out',type=pathlib.Path,required=True);p.add_argument('--godot3',type=pathlib.Path,required=True);p.add_argument('--godot4',type=pathlib.Path,required=True);p.add_argument('--mono',type=pathlib.Path);p.add_argument('--dotnet',type=pathlib.Path);p.add_argument('--only');a=p.parse_args()
for attr in ['samples','work','out','godot3','godot4','mono','dotnet']:
 if getattr(a,attr):setattr(a,attr,getattr(a,attr).resolve())
a.work.mkdir(parents=True,exist_ok=True);a.out.mkdir(parents=True,exist_ok=True)
probe='''extends Node
var tick = 0
var stage
var max_nodes = 0
var max_collisions = 0
var node_paths = {}
func _ready():
 var scene = load("MAIN_SCENE")
 if not scene:
  print("NOHIT_PROBE_LOAD_FAILED")
  get_tree().quit(3)
  return
 stage = scene.INSTANTIATE()
 add_child(stage)
 print("NOHIT_PROBE_LOADED")
func visit(n):
 var count = 1
 if n is CollisionObject2D: max_collisions += 1
 if n.get_script(): node_paths[str(n.get_path())] = str(n.get_script().resource_path)
 for c in n.get_children(): count += visit(c)
 return count
func _physics_process(_delta):
 tick += 1
 if tick % 60 == 0:
  max_collisions = 0
  max_nodes = max(max_nodes,visit(get_tree().root))
 for name in ["ui_accept","ui_cancel","confirm","accept","z","enter"]:
  if InputMap.has_action(name):
   if tick % 90 == 1: Input.action_press(name)
   else: Input.action_release(name)
 if tick >= 600:
  print("NOHIT_PROBE_FINISHED ", tick, " nodes=",max_nodes," collision_objects=",max_collisions)
  print("NOHIT_PROBE_SCRIPTS ", node_paths)
  get_tree().quit()
'''
rows=json.loads((a.samples/'restoration.json').read_text())
if a.only:rows=[r for r in rows if re.search(a.only,r['repository'])]
def run_cmd(cmd,log,timeout=60,env=None):
 start=time.monotonic()
 if env is None:
  env=os.environ.copy()
  env['LANG']='en_US.UTF-8'
  if a.dotnet:
   env['DOTNET_ROOT']=str(a.dotnet.parent)
   env['PATH']=str(a.dotnet.parent)+os.pathsep+env['PATH']
   env['DOTNET_CLI_TELEMETRY_OPTOUT']='1'
 try:
  r=subprocess.run(cmd,capture_output=True,text=True,timeout=timeout,env=env);text=r.stdout+r.stderr;code=r.returncode;timed=False
 except OSError as e:text=str(e);code=None;timed=False
 except subprocess.TimeoutExpired as e:text=(e.stdout or b'').decode(errors='replace')+(e.stderr or b'').decode(errors='replace');code=None;timed=True
 log.write_text(text);return {'command':cmd,'returncode':code,'timeout':timed,'seconds':time.monotonic()-start,'log':log.name,'errors': [l for l in text.splitlines() if re.search('SCRIPT ERROR|Parse Error|ERROR:|error [A-Z]+[0-9]+',l)][:25]},text

def one(row):
 name=row['repository'].replace('/','--');src=a.samples/name;out={'repository':row['repository'],'commit':row.get('commit'),'projects':[]}
 if not row['ok']:out['status']='fetch_failed';return out
 root=a.work/name
 if not root.exists():shutil.copytree(src,root,ignore=shutil.ignore_patterns('.git','.godot','.import','bin','obj'))
 # Keep shipped native extension binaries; don't ignore source bin directories.
 for folder in src.rglob('bin'):
  if folder.is_dir() and any(folder.rglob('*.gdextension')):
   target=root/folder.relative_to(src);shutil.copytree(folder,target,dirs_exist_ok=True)
 projects=list(root.rglob('project.godot'));yyps=list(root.rglob('*.yyp'))
 if not projects:
  out['status']='gamemaker_runtime_missing' if yyps else 'resource_tool_no_battle_project'
  out['gamemaker_projects']=[str(f.relative_to(root)) for f in yyps]
  out['compiler_probe']={n:shutil.which(n) for n in ['Igor','igor','GameMaker','wine']}
  out['attack_candidates']=[str(f.relative_to(root)) for f in root.rglob('*.gml') if re.search('attack|bullet|hurt',str(f),re.I)][:25]
  print(name,out['status'],flush=True);return out
 for i,config in enumerate(projects):
  folder=config.parent;s=config.read_text();old='config_version=4' in s;cs='"C#"' in s
  original=re.search(r'^run/main_scene="(.*?)"',s,re.M)
  label=name+'-'+str(i);rec={'project':str(config.relative_to(root)),'engine_major':3 if old else 4,'csharp':cs,'original_main':original.group(1) if original else None,'patches':[]}
  exe=a.godot3 if old else (a.mono if cs and a.mono else a.godot4)
  # Choose GL in the headless test copy; gameplay scripts remain untouched.
  if not old:
   if '[rendering]' not in s:s+='\n[rendering]\n'
   s=re.sub(r'^renderer/rendering_method=.*$', '', s, flags=re.M)
   s=s.replace('[rendering]','[rendering]\nrenderer/rendering_method="gl_compatibility"',1);config.write_text(s);rec['patches'].append('GL compatibility renderer in test copy')
  args=[str(exe),'--path',str(folder)] + ([] if old else ['--headless'])
  import_rec,log=run_cmd(args+(['--editor'] if old else ['--editor','--import']),a.out/(label+'-import.log'),15 if old else 90)
  rec['import']=import_rec
  if cs:
   csprojects=list(folder.glob('*.csproj'))
   if a.dotnet and csprojects:
    env=os.environ.copy();env['DOTNET_CLI_HOME']=str(a.work/'dotnet-home');env['DOTNET_SKIP_FIRST_TIME_EXPERIENCE']='1';env['DOTNET_CLI_TELEMETRY_OPTOUT']='1';env['DOTNET_ROOT']=str(a.dotnet.parent)
    rec['build'],_=run_cmd([str(a.dotnet),'exec',str(a.dotnet.parent/'sdk/8.0.408/MSBuild.dll'),str(csprojects[0]),'/restore','/t:Build','/v:minimal','/nologo'],a.out/(label+'-build.log'),150,env)
   else:rec['build']={'status':'dotnet_unavailable'}
  if not original:rec['status']='no_main_scene';out['projects'].append(rec);continue
  gd=probe.replace('MAIN_SCENE',original.group(1)).replace('INSTANTIATE','instance' if old else 'instantiate');(folder/'nohit_probe.gd').write_text(gd)
  (folder/'nohit_probe.tscn').write_text('[gd_scene load_steps=2 format='+('2' if old else '3')+']\n[ext_resource path="res://nohit_probe.gd" type="Script" id="1"]\n[node name="NoHitStartupProbe" type="Node"]\nscript = ExtResource('+('1' if old else '"1"')+')\n')
  s=config.read_text().replace(original.group(0),'run/main_scene="res://nohit_probe.tscn"');config.write_text(s)
  rec['run'],log=run_cmd(args+['--fixed-fps','60'],a.out/(label+'-run.log'),25)
  rec['status']='startup_600_frames' if 'NOHIT_PROBE_FINISHED' in log and not re.search('SCRIPT ERROR|Parse Error|ERROR:.*(?:GDExtension|Error loading extension|Cannot get class)',log) else ('startup_with_errors' if 'NOHIT_PROBE_FINISHED' in log else 'startup_failed')
  rec['probe_lines']=[l for l in log.splitlines() if l.startswith('NOHIT_PROBE')]
  out['projects'].append(rec)
  print(label,rec['status'],flush=True)
 out['status']='attempted';return out
with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:result=list(ex.map(one,rows))
(a.out/'startup.json').write_text(json.dumps(result,indent=2))

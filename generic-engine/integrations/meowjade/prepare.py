"""Prepare a pinned upstream project copy; preserve original gameplay files."""
import argparse,pathlib,shutil,subprocess,json,hashlib
PIN='729dfb7ef9ba41f8695724cb31e5cd360d49128d'
p=argparse.ArgumentParser();p.add_argument('upstream',type=pathlib.Path);p.add_argument('destination',type=pathlib.Path);a=p.parse_args()
head=subprocess.check_output(['git','-C',str(a.upstream),'rev-parse','HEAD'],text=True).strip()
if head!=PIN:raise SystemExit('upstream commit mismatch')
if subprocess.run(['git','-C',str(a.upstream),'diff','--quiet',PIN,'--','*.gd','*.tscn','*.tres','project.godot']).returncode:
 raise SystemExit('upstream gameplay/config has local changes; use a clean checkout')
if a.destination.exists():raise SystemExit('destination must not exist')
shutil.copytree(a.upstream,a.destination,ignore=shutil.ignore_patterns('.git','.godot','*.uid'))
patches=[]
for name,before,after,reason in [
 ('Battle/AttackMeter/meter.gd','"scale:x", 0b, TIME','"scale:x", 0, TIME','fix invalid numeric literal in unused attack-meter UI'),
 ('Battle/Attacks/default_attack.gd','throw.emit(Vector2.UP)','throw.emit(Vector2.UP, 10)','supply original throw receiver default power to two-argument signal')]:
 f=a.destination/name;s=f.read_text();assert s.count(before)==1;f.write_text(s.replace(before,after));patches.append({'path':name,'before':before,'after':after,'reason':reason})
soul_scene=a.destination/'Battle/Soul/soul.tscn';soul_scene.write_text(soul_scene.read_text().replace('path="res://Battle/Soul/soul.gd"','path="res://nohit_integration/audited_soul.gd"'))
patches.append({'path':'Battle/Soul/soul.tscn','reason':'bind observing subclass; hurt/heal delegate to original superclass, preserve scene export values'})
shutil.rmtree(a.destination/'addons/git',ignore_errors=True)
config=a.destination/'project.godot';s=config.read_text().replace('version_control/plugin_name="GitPlugin"','version_control/plugin_name=""').replace('version_control/autoload_on_startup=true','version_control/autoload_on_startup=false');s=s.replace('run/main_scene="res://Singletons/scene_container.tscn"','run/main_scene="res://nohit_integration/driver.tscn"');s += '\n[rendering]\nrenderer/rendering_method="gl_compatibility"\n';config.write_text(s)
folder=a.destination/'nohit_integration';folder.mkdir()
shutil.copy2(pathlib.Path(__file__).parents[2]/'godot/addons/nohit/native_baker.gd',folder/'native_baker.gd')
for f in pathlib.Path(__file__).parent.glob('*.gd'):shutil.copy2(f,folder/f.name)
for f in pathlib.Path(__file__).parent.glob('*.tscn'):shutil.copy2(f,folder/f.name)
critical=['Battle/Soul/soul.gd','Battle/Bullets/bullet.gd','Battle/Bullets/bullet_area.gd','Battle/Bullets/defaultbullet.gd','Battle/Bullets/Bullet_Circle.gd','Battle/Platform/platform.gd','Battle/Box/BattleBox.gd','Singletons/global.gd']
identity={}
for n in critical:
 f=a.upstream/n
 if f.is_file():
  assert f.read_bytes()==(a.destination/n).read_bytes();identity[n]=hashlib.sha256(f.read_bytes()).hexdigest()
(folder/'upstream.json').write_text(json.dumps({'repository':'https://github.com/meowjade/Godot-Undertale-Engine','commit':head,'patches':patches,'unchanged_gameplay_sha256':identity,'harness_configuration':['replace entry scene with driver','disable unused Git editor extension','select GL compatibility renderer'],'integration_sha256':{f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in folder.iterdir() if f.suffix in ['.gd','.tscn']}},indent=2))
print(a.destination.resolve())

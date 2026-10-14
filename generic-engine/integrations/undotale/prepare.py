import argparse,pathlib,shutil,subprocess,json,hashlib
p=argparse.ArgumentParser();p.add_argument('upstream',type=pathlib.Path);p.add_argument('destination',type=pathlib.Path);a=p.parse_args();pin='9dc511a5ec5225866ceaf86f1f44de8972429490'
assert subprocess.check_output(['git','-C',str(a.upstream),'rev-parse','HEAD'],text=True).strip()==pin
shutil.copytree(a.upstream,a.destination,ignore=shutil.ignore_patterns('.git','.import'))
(a.destination/'nohit_driver.gd').write_bytes(pathlib.Path(__file__).with_name('driver.gd').read_bytes())
(a.destination/'nohit_driver.tscn').write_text('[gd_scene load_steps=2 format=2]\n[ext_resource path="res://nohit_driver.gd" type="Script" id=1]\n[node name="NativeAudit" type="Node"]\nscript = ExtResource(1)\n')
(a.destination/'nohit_observer.gd').write_text('extends "res://Shared/Soul/Soul.gd"\nfunc hit(damage = 0):\n get_tree().call_group("nohit_audit","on_damage")\n .hit(damage)\n')
f=a.destination/'nohit_driver.gd';s=f.read_text().replace('pause_mode = Node.PAUSE_MODE_PROCESS','pause_mode = Node.PAUSE_MODE_PROCESS\n add_to_group("nohit_audit")');f.write_text(s)
f=a.destination/'Shared/Soul/Soul.tscn';f.write_text(f.read_text().replace('res://Shared/Soul/Soul.gd','res://nohit_observer.gd'))
f=a.destination/'project.godot';s=f.read_text().replace('run/main_scene="res://BattleEngine/BattleEngine.tscn"','run/main_scene="res://nohit_driver.tscn"');f.write_text(s)
identity={str(f.relative_to(a.upstream)):hashlib.sha256(f.read_bytes()).hexdigest() for f in a.upstream.rglob('*.gd')}
(a.destination/'nohit-upstream.json').write_text(json.dumps({'pin':pin,'unchanged_gameplay_sha256':identity,'changes':['entry scene','observing soul subclass delegates original hit']},indent=2))

import pathlib,shutil,subprocess,sys,json,hashlib
src=pathlib.Path(sys.argv[1]);dst=pathlib.Path(sys.argv[2]);pin='b449c9c05f8af91b8e015d490ff9fdcb8913ed1e';assert subprocess.check_output(['git','-C',str(src),'rev-parse','HEAD'],text=True).strip()==pin
shutil.copytree(src,dst,ignore=shutil.ignore_patterns('.git','.import'))
s=pathlib.Path(__file__).with_name('driver.gd').read_text().replace('if tick>=replay.size():finish("replay_length_mismatch");return','if tick>=replay.size():\n   finish("replay_length_mismatch")\n   return');(dst/'nohit_driver.gd').write_text(s)
(dst/'nohit_driver.tscn').write_text('[gd_scene load_steps=2 format=2]\n[ext_resource path="res://nohit_driver.gd" type="Script" id=1]\n[node name="NativeAudit" type="Node"]\nscript = ExtResource(1)\n')
(dst/'nohit_soul.gd').write_text('extends "res://Scripts/Battle/Player/PlayerHeart.gd"\nfunc takeDamage(HP, KR = 0):\n get_tree().call_group("nohit_audit","on_damage",HP,KR)\n .takeDamage(HP,KR)\n')
for p in dst.rglob('*.tscn'):
 s=p.read_text()
 if 'res://Scripts/Battle/Player/PlayerHeart.gd' in s:p.write_text(s.replace('res://Scripts/Battle/Player/PlayerHeart.gd','res://nohit_soul.gd'))
p=dst/'project.godot';p.write_text(p.read_text().replace('run/main_scene="res://Scenes/gameview.tscn"','run/main_scene="res://nohit_driver.tscn"'))
(dst/'nohit-upstream.json').write_text(json.dumps({'pin':pin,'source_sha256':{str(p.relative_to(src)):hashlib.sha256(p.read_bytes()).hexdigest() for p in src.rglob('*.gd')},'changes':['entry scene','observing soul subclass delegates original takeDamage']},indent=2))

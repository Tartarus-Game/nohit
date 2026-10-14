"""Package the complete restored source tree and validate every delivered byte."""
import argparse,difflib,hashlib,json,pathlib,zipfile
p=argparse.ArgumentParser();p.add_argument('--root',type=pathlib.Path,required=True);p.add_argument('--output',type=pathlib.Path,required=True);p.add_argument('--previous',type=pathlib.Path);p.add_argument('--patch-name',default='PORTABLE_INTEGRATION.patch');a=p.parse_args();root=a.root.resolve()
assert pathlib.Path(a.patch_name).name==a.patch_name
files={}
for f in root.rglob('*'):
 if not f.is_file() or f.is_symlink():continue
 name=f.relative_to(root).as_posix()
 if any(part in ['.git','.godot','.import','__pycache__','.pytest_cache','.venv'] for part in f.relative_to(root).parts):continue
 if f.suffix in ['.pyc','.so','.dll','.zip','.core']:continue
 files[name]=f.read_bytes()
files.pop('DELIVERY_MANIFEST.json',None)
previous_hash=None
if a.previous:
 previous_hash=hashlib.sha256(a.previous.read_bytes()).hexdigest()
 with zipfile.ZipFile(a.previous) as z:
  old={name.removeprefix('nohit/'):z.read(name) for name in z.namelist() if name.startswith('nohit/')}
 patch=[]
 for name,data in sorted(files.items()):
  if pathlib.Path(name).suffix not in ['.py','.gd','.gml','.tscn','.godot','.md','.txt'] and not (name.startswith('generic-engine/portable/') and name.endswith('.json')):continue
  if old.get(name)==data:continue
  try:before=old.get(name,b'').decode().splitlines(True);after=data.decode().splitlines(True)
  except UnicodeDecodeError:continue
  patch.extend(difflib.unified_diff(before,after,fromfile='a/'+name if name in old else '/dev/null',tofile='b/'+name))
 files[a.patch_name]=''.join(patch).encode()
files['RUN_GENERIC.md']='''# Generic engine source delivery, 2026-10-09\n\nStart with generic-engine/portable/QUICKSTART.zh-CN.md.\nThe live SDK supports Godot 3/4 config-only or single-file adapters, without\nworld snapshots or replacement soul physics. Native fixtures and faults passed\n24 acceptance checks, plus the original Megalo bonegap through the same SDK.\nGameMaker remains a source template without native runtime acceptance.\n\nThis archive preserves all previous nohit source and all-sample evidence.\nThree upstream projects / six native tests were verified; not all levels solved.\nOPTIMIZATION.patch and NATIVE_INTEGRATION.patch are historical patches.\nPORTABLE_INTEGRATION.patch describes live SDK changes since the previous v10\narchive. Evidence is included directly. Upstream assets use pinned fetches.\n\nRepackage without requiring a .git directory:\npython generic-engine/tools/package_generic_snapshot.py --root . --output /path/source.zip\n'''.encode()
manifest={'format':'nohit-source-v11-portable-live-sdk','previous_source_sha256':previous_hash,'scope':'complete nohit source and prior evidence plus config/single-file live SDK, 24 acceptance checks and native Megalo SDK integration','files':{name:{'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()} for name,data in sorted(files.items())}}
files['DELIVERY_MANIFEST.json']=(json.dumps(manifest,indent=2)+'\n').encode()
a.output.parent.mkdir(parents=True,exist_ok=True);temp=a.output.with_suffix('.building')
with zipfile.ZipFile(temp,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
 for name,data in sorted(files.items()):
  info=zipfile.ZipInfo('nohit/'+name,date_time=(2026,10,9,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED;info.external_attr=0o100644<<16;z.writestr(info,data)
with zipfile.ZipFile(temp) as z:
 assert z.testzip() is None
 for name,data in files.items():assert z.read('nohit/'+name)==data,name
temp.replace(a.output)
print(json.dumps({'path':str(a.output.resolve()),'files':len(files),'bytes':a.output.stat().st_size,'sha256':hashlib.sha256(a.output.read_bytes()).hexdigest(),'all_file_bytes_verified':True}))

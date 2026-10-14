import concurrent.futures, subprocess, pathlib, json, time
import argparse
ap=argparse.ArgumentParser();ap.add_argument('destination',type=pathlib.Path);args=ap.parse_args();root=args.destination;root.mkdir(parents=True,exist_ok=True)
repos=['onezhazha233/Undertale-Engine-modded-by-Zhazha','Yanxiyimengya/UndertaleMakerX','TML233/UndertaleEngine','etherealxx/undotale-godot4','WDUT-Dev/UT-Godot-Engine','meowjade/Godot-Undertale-Engine','KoitoLov/UT-BattleEngine','neon-gr33n/underengine','NsCrosu/Undertale-Fight-Engine','znm2500/Undertale-Engine-Ultra','Stoxis/Godette-Tale','Oplexitie/Megalo-Framework','Maks7594/LVENGINE','CoalitionEngine/Coalition-Engine','mouse114514/End-Of-Truth','sultansagitov/UndertaleBattle','SagaPDev/Undertale-battle-system-prototipe','SamuelWolfang/UNDOTALE','techoskiller/AT-Engine','Animeliqite/understudio','ws3917/psoutertale-gms','Tartarus-Game/UndertaleEngine','rarespawns/UndertaleFangameFramework']
def one(repo):
 p=root/repo.replace('/','--');t=time.monotonic()
 try:
  r=subprocess.run(['git','clone','--depth','1','https://github.com/'+repo+'.git',str(p)],capture_output=True,text=True,timeout=180)
  out={'repository':repo,'path':str(p),'ok':r.returncode==0,'elapsed':round(time.monotonic()-t,2),'error':r.stderr[-1000:] if r.returncode else '', 'commit':subprocess.check_output(['git','-C',str(p),'rev-parse','HEAD'],text=True).strip() if not r.returncode else None}
 except Exception as e: out={'repository':repo,'ok':False,'error':str(e)}
 print(json.dumps(out),flush=True);return out
with concurrent.futures.ThreadPoolExecutor(max_workers=6) as ex: results=list(ex.map(one,repos))
(root/'collection.json').write_text(json.dumps(results,indent=2))

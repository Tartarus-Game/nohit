"""Finite native portfolios for the added Godot 3 adapters, with replay checks."""
import argparse,concurrent.futures,json,pathlib,subprocess,time
p=argparse.ArgumentParser();p.add_argument('--adapter',choices=['undotale','megalo'],required=True);p.add_argument('--godot',type=pathlib.Path,required=True);p.add_argument('--project',type=pathlib.Path,required=True);p.add_argument('--out',type=pathlib.Path,required=True);p.add_argument('--workers',type=int,default=6);a=p.parse_args()
if not 1<=a.workers<=16:p.error('workers must be 1..16')
a.godot=a.godot.resolve();a.project=a.project.resolve();a.out=a.out.resolve();a.out.mkdir(parents=True,exist_ok=True)
def run(label,args):
 target=a.out/(label+'.json');target.unlink(missing_ok=True);cmd=[str(a.godot),'--path',str(a.project),'--fixed-fps','60','--','--out='+str(target)]+args;start=time.monotonic()
 try:r=subprocess.run(cmd,capture_output=True,text=True,timeout=25)
 except subprocess.TimeoutExpired as e:
  (a.out/(label+'.log')).write_bytes((e.stdout or b'')+(e.stderr or b''));return None,{'label':label,'status':'timeout'}
 log=r.stdout+r.stderr;(a.out/(label+'.log')).write_text(log)
 if not target.exists() or 'SCRIPT ERROR' in log or 'Parse Error' in log:return None,{'label':label,'status':'runtime_error'}
 d=json.loads(target.read_text());return d,{'label':label,'status':d['status'],'ticks':d['ticks'],'damage_calls':d['damage_calls'],'wall_seconds':time.monotonic()-start}
def validate(d):
 assert d['status']=='native_nohit' and d['attack_completed'] and d['damage_calls']==0
 assert len(d['route'])==len(d['states'])==d['ticks']
 hp=d.get('entry_hp',48)
 assert d['hp']==hp and d.get('kr',0)==0 and d['observed_bullets']>0
 assert all(s['hp']==hp and s.get('kr',0)==0 and s.get('inv',0)==0 for s in d['states'])
report={'adapter':a.adapter,'attempts':[],'verified':[]}
specs=[(i,s) for i in range(6) for s in [0,4,5,6,16]] if a.adapter=='megalo' else [(0,s) for s in [0,4,5,6,1,2,16,17,8,9,10,12]]
def attempt(spec):
 pattern,s=spec;args=['--strategy='+str(s)]
 if a.adapter=='megalo':args+=['--pattern='+str(pattern)]
 return run(f'{pattern}-{s}',args)
with concurrent.futures.ThreadPoolExecutor(max_workers=a.workers) as ex:runs=list(ex.map(attempt,specs))
report['attempts']=[r for d,r in runs]
winners={}
for (pattern,s),(d,r) in zip(specs,runs):
 if d and d['status']=='native_nohit' and pattern not in winners:winners[pattern]=(d,r,[])
if a.adapter=='undotale':
 d,r=run('three-bones',['--component','--strategy=16']);report['attempts'].append(r)
 if d and d['status']=='native_nohit':winners['three-bones']=(d,r,['--component'])
for pattern,(candidate,record,extra) in winners.items():
 validate(candidate)
 args=extra+['--replay='+str(a.out/(record['label']+'.json'))]
 if a.adapter=='megalo':args+=['--pattern='+str(pattern)]
 replay,rec=run('replay-'+str(pattern),args);validate(replay)
 assert candidate['route']==replay['route'] and candidate['states']==replay['states']
 negative,nrec=run('negative-'+str(pattern),extra+(['--pattern='+str(pattern),'--negative'] if a.adapter=='megalo' else ['--strategy=0']))
 assert negative and negative['status']=='hit' and negative['damage_calls']>0 and negative['hp']<candidate['hp']
 report['verified'].append({'pattern':pattern,'candidate':record,'replay':rec,'negative':nrec})
(a.out/'suite.json').write_text(json.dumps(report,indent=2));print(json.dumps(report['verified'],indent=2))

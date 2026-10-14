"""Restore every audited repository at its pinned commit, with bounded workers."""
import argparse,concurrent.futures,json,pathlib,subprocess,time
p=argparse.ArgumentParser();p.add_argument('--audit',type=pathlib.Path,default=pathlib.Path(__file__).parents[1]/'research/source-audit.json');p.add_argument('--out',type=pathlib.Path,required=True);a=p.parse_args();a.out.mkdir(parents=True,exist_ok=True)
def run(row):
 repo=row['repository'];name=repo.removesuffix('.git').removeprefix('https://github.com/');target=a.out/name.replace('/','--');target.mkdir(exist_ok=True);start=time.monotonic();logs=[]
 try:
  for cmd in [['git','init',str(target)],['git','-C',str(target),'fetch','--depth','1',repo,row['commit']],['git','-C',str(target),'checkout','--detach','FETCH_HEAD']]:
   r=subprocess.run(cmd,capture_output=True,text=True,timeout=180);logs.append(r.stdout+r.stderr)
   if r.returncode:raise RuntimeError(logs[-1][-1000:])
  actual=subprocess.check_output(['git','-C',str(target),'rev-parse','HEAD'],text=True).strip();assert actual==row['commit'];result={'repository':name,'commit':actual,'ok':True,'path':str(target.resolve())}
 except Exception as e:result={'repository':name,'ok':False,'error':str(e)}
 result['wall_seconds']=time.monotonic()-start;(a.out/(name.replace('/','--')+'.log')).write_text('\n'.join(logs));print(json.dumps(result),flush=True);return result
with concurrent.futures.ThreadPoolExecutor(max_workers=6) as ex:r=list(ex.map(run,json.loads(a.audit.read_text())))
(a.out/'restoration.json').write_text(json.dumps(r,indent=2))

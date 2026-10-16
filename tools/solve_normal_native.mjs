/** Fresh continuous Normal campaign: ordinary keyboard inputs, unchanged C2. */
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import {fileURLToPath} from 'node:url';
import {spawnSync} from 'node:child_process';
import {createHash} from 'node:crypto';

const ROOT=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const OUT=path.resolve(process.env.NOHIT_BENCH_OUT||path.join(ROOT,'build/normal-campaign'));
const PY=process.env.NOHIT_PYTHON||'python';
const gameRoot=path.resolve(process.env.NOHIT_GAME_DIR||path.join(ROOT,'c2-sans-fight'));
const healing=process.env.NOHIT_SCRIPTED_HEALING==='1';
const fps=Number(process.env.NOHIT_FPS||60),period=1000/fps,epsilon=fps===30?1e-6:0;
if(!Number.isFinite(fps)||fps<30)throw Error('FPS must be at least 30');
fs.mkdirSync(OUT,{recursive:true});
const SHA=p=>createHash('sha256').update(fs.readFileSync(p)).digest('hex');
const source=fs.readFileSync(path.join(ROOT,'tools/real_engine_test.mjs'),'utf8');
let boot=source.slice(0,source.indexOf("if (process.argv.includes('--jcw-smoke'))"));
boot=boot.replace(/^import .*;$/gm,'').replace('const HERE = path.dirname(fileURLToPath(import.meta.url));','const HERE = path.join(repoRoot,"tools");');
boot=boot.replace('const GAME = path.join(ROOT, "c2-sans-fight");','const GAME = gameRoot;');
boot=boot.replace('vm.createContext(sandbox);',"sandbox.location.search='?mode=normal&seed=42';vm.createContext(sandbox);");
boot+='\nreturn {sandbox,rtReal,GAME};';
const AsyncFunction=Object.getPrototypeOf(async function(){}).constructor;
const helpers=path.join(ROOT,'c2-sans-fight');
const bootFS={...fs,readFileSync(p,...args){if(path.basename(p)==='jcw_adapter.js')p=path.join(helpers,'jcw_adapter.js');return fs.readFileSync(p,...args);}};
const {sandbox:c,rtReal:rt,GAME}=await new AsyncFunction('fs','path','vm','fileURLToPath','process','repoRoot','gameRoot',boot)(bootFS,path,vm,fileURLToPath,process,ROOT,gameRoot);
if(typeof c.sc?.prototype.g.Gt!=='function'&&typeof c.sc?.prototype.g.Ft==='function')
 vm.runInContext("Object.defineProperty(sc.prototype.g,'Gt',{get(){return this.Ft;}});Object.defineProperty(Object.getPrototypeOf(c2runtime),'all_global_vars',{get(){return this.Fu;}})",c);
for(const n of ['solver_state','menu_controller','attack_seed'])vm.runInContext(fs.readFileSync(path.join(helpers,n+'.js'),'utf8'),c);
const keyboard=()=>rt.types_by_index.flatMap(t=>t.instances).find(i=>Array.isArray(i.keyMap));
c.TASRunner={getKeyboardInstance:keyboard};
const capture=()=>c.NoHitSolverState.capturePhysical(rt);
const globals=()=>Object.fromEntries(rt.all_global_vars.map(v=>[v.name,v.data]));
const parameter=(inst,i)=>{let v;inst.exps.Param({set_any:x=>v=x},i);return v;};
const input=(mask,confirm)=>{const keys=keyboard().keyMap;keys.fill(false);for(const [k,b] of [[37,1],[39,2],[38,4],[40,8],[88,16]])keys[k]=!!(mask&b);keys[90]=confirm;};
const rounds=[],events=[],damage=[],ticks=[];
let active=null,won=false,failure=null,lastTick=null;
const proto=Object.getPrototypeOf(rt),trigger=proto.trigger;
proto.trigger=function(method,inst,value){
 const fn=method===c.cr.plugins_.Function.prototype.cnds.OnFunction?String(value).toLowerCase():'';
 if(fn){
  if(['runattack','tlplay','endattack','win1','win2','damageplayer'].includes(fn))events.push({tick:this.tickcount,fn,param:fn==='runattack'?parameter(inst,0):undefined});
  if(fn==='damageplayer'){const amount=Number(parameter(inst,0));damage.push({tick:this.tickcount,amount});if(!healing||!Number.isFinite(amount)||amount>=0)failure='native_damage';}
  if(fn==='win2')won=true;
  if(fn==='runattack'){
   if(active&&!active.completed)throw Error('RunAttack replaced an incomplete round');
   const name=String(parameter(inst,0)).replace(/\.csv$/,'');
   active={wave:name,number:rounds.length,initial_targets:[],rows:[],completed:false};rounds.push(active);
  }
  if(fn==='tlplay'&&active&&!active.source){
   active.source=String(parameter(inst,0));active.before=capture();
   const original=path.join(GAME,active.wave+'.csv');
   const norm=x=>x.replace(/^\uFEFF/,'').replace(/\r/g,'').trim();
   if(!fs.existsSync(original)||norm(fs.readFileSync(original,'utf8'))!==norm(active.source))throw Error('TLPlay differs from attack CSV');
   active.csv_sha256=SHA(original);
  }
  if(fn==='getheartpos'&&active?.source&&!active.entry){const h=capture();active.initial_targets.push([0,h.line,h.initial[0],h.initial[1]]);}
  if(fn==='endattack'&&active&&!active.completed){active.ended=true;active.end_tick=this.tickcount;}
 }
 return trigger.apply(this,arguments);
};
function persist(){
 const report={protocol:'continuous-normal-unchanged-c2-ordinary-keyboard',fps,seed:42,
  passed:won&&!failure&&rounds.length===24&&rounds.every(r=>r.completed)&&damage.every(e=>healing&&e.amount<0),
  scripted_healing_admitted:healing,
  won,failure,rounds,events,damage,ticks,
  runtime_sha256:SHA(path.join(GAME,'c2runtime.js')),data_sha256:SHA(path.join(GAME,'data.js')),
  solver_sha256:Object.fromEntries(fs.readdirSync(path.join(ROOT,'nohit/engine')).filter(n=>/\.(py|cpp)$/.test(n)).map(n=>[n,SHA(path.join(ROOT,'nohit/engine',n))]))};
 fs.writeFileSync(path.join(OUT,'campaign.json'),JSON.stringify(report));
 return report;
}
try{
 for(let physical=0;physical<150000&&!won&&!failure;physical++){
  let owner=active,planned=null;
  if(owner?.plan&&!owner.completed){
   if(owner.cursor>=owner.plan.actions.length)throw Error('No EndAttack at planned terminal');
   planned=owner.cursor;input(owner.plan.actions[planned],owner.plan.confirm_sequence[planned]);
  }else if(owner?.source&&!owner.completed)input(0,false);
  else{
   const model=c.NoHitMenuController.read(rt);model.dt=Math.min(period/1000,1/30);model.clockMs=NaN;
   const menu=c.NoHitMenuController.decide(model);
   if(menu.blocked){failure='menu_'+menu.reason;break;}
   input(menu.keymask,menu.confirm);
  }
  rt.tick(true,rt.last_tick_time+period+epsilon,true);
  const g=globals();let row=null;try{row=capture();}catch{}
  ticks.push({tick:rt.tickcount,dt:rt.dt,clock_start_ms:rt.last_tick_time,HP:g.HP,KR:g.KR,mode:g.SimulatorMode,
    input:keyboard().keyMap.reduce((m,v,k)=>m|(v?({37:1,39:2,38:4,40:8,88:16,90:32}[k]||0):0),0),state:row?.initial});
  if(lastTick!==null&&rt.tickcount!==lastTick+1)throw Error('Non-continuous native ticks');lastTick=rt.tickcount;
  const healthBad=healing?!(Number.isFinite(g.HP)&&g.HP>0&&Number.isFinite(g.KR)):(g.HP!==92||g.KR!==0);
  if(rounds.length&&(healthBad||g.SimulatorMode!==0)){failure='native_hp_kr_or_mode';break;}
  if(planned!==null){
   owner.cursor++;owner.rows.push(row);
   if(!owner.ended){
    if(!row)throw Error('Missing nonterminal heart');
    for(let i=0;i<11;i++)if(row.initial[i]!==owner.plan.trajectory[owner.cursor][i])throw Error(`State mismatch ${owner.wave} tick ${owner.cursor} component ${i}`);
   }
   if(owner.ended){
    if(owner.cursor!==owner.plan.actions.length)throw Error('Early EndAttack');
    owner.completed=true;
    console.log(JSON.stringify({round:owner.number,wave:owner.wave,passed:true,ticks:owner.cursor,solve_seconds:owner.plan.wall_seconds}));
    persist();
   }
  }
  if(active?.source&&!active.entry&&row&&(row.line>1||active.ended)){
   const r=active,entry={...row,initial_environment:r.before.initial_environment,initial_arena:r.before.arena,initial_target_history:r.initial_targets};
   entry.dt_schedule=[entry.initial_environment[7]];let timestamp=rt.last_tick_time;
   for(let i=1;i<40000;i++){let next=timestamp+period+epsilon;entry.dt_schedule.push(Math.min((next-timestamp)/1000,1/30));timestamp=next;}
   r.entry=entry;r.rows=[row];r.cursor=0;
   const stem=String(r.number).padStart(2,'0')+'-'+r.wave,entryPath=path.join(OUT,stem+'-entry.json'),planPath=path.join(OUT,stem+'-plan.json');
   fs.writeFileSync(entryPath,JSON.stringify(entry));
   let result=spawnSync(PY,['-m','tools.solve_csv',path.join(GAME,r.wave+'.csv'),'--entry',entryPath,'--out',planPath,
    '--search-strategy','native','--seconds',process.env.NOHIT_SECONDS||'8','--width',process.env.NOHIT_WIDTH||'3000',...(healing?['--allow-scripted-healing']:[])],{cwd:ROOT,encoding:'utf8',timeout:120000});
   if(!fs.existsSync(planPath))throw Error(result.stderr||result.stdout||'solver did not write a result');
   r.plan=JSON.parse(fs.readFileSync(planPath));r.plan_sha256=SHA(planPath);
   if(result.status!==0&&process.env.NOHIT_RETRY==='1'){
    r.first_attempt=r.plan;
    fs.writeFileSync(path.join(OUT,stem+'-first-attempt.json'),JSON.stringify(r.plan));
    result=spawnSync(PY,['-m','tools.solve_csv',path.join(GAME,r.wave+'.csv'),'--entry',entryPath,'--out',planPath,
      '--search-strategy','native','--seconds','45','--width','8192','--memory-mb','256',...(healing?['--allow-scripted-healing']:[])],{cwd:ROOT,encoding:'utf8',timeout:120000});
    r.plan=JSON.parse(fs.readFileSync(planPath));r.plan_sha256=SHA(planPath);
   }
   if(result.status!==0||r.plan.status!=='candidate_found'||!r.plan.verified){failure='unknown_'+r.wave;console.log(result.stdout);break;}
  }
  if(!active?.plan||active.completed)await new Promise(resolve=>setTimeout(resolve,1));
 }
 if(!won&&!failure)failure='native_tick_budget';
}catch(error){failure=String(error.stack||error);}
const final=persist();console.log(JSON.stringify({passed:final.passed,won,completed_rounds:rounds.filter(r=>r.completed).length,failure,damage,ticks:ticks.length}));
process.exitCode=final.passed?0:2;

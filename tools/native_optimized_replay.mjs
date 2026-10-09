/** Unmodified C2 events, fresh solver actions; DOM/audio/render stubs only. */
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import {fileURLToPath} from 'node:url';
import {spawnSync} from 'node:child_process';
import {createHash} from 'node:crypto';
const ROOT=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const out=path.resolve(process.env.NOHIT_BENCH_OUT||path.join(ROOT,'tools/optimization-results'));
fs.mkdirSync(out,{recursive:true});
const python=process.env.NOHIT_PYTHON||'python';
const gameRoot=path.resolve(process.env.NOHIT_GAME_DIR||path.join(ROOT,'c2-sans-fight'));
const healing=process.env.NOHIT_SCRIPTED_HEALING==='1';
const scriptedDamage=process.env.NOHIT_SCRIPTED_DAMAGE==='1';
const fps=Number(process.env.NOHIT_FPS||30);
if(!Number.isFinite(fps)||fps<30)throw Error('NOHIT_FPS must be at least 30');
const period=1000/fps,epsilon=fps===30?1e-6:0;
const waves=process.argv.slice(2);
if(!waves.length)waves.push('sans_bonegap1','sans_bonegap1fast','sans_bluebone','sans_platforms3','sans_platforms4hard');
const source=fs.readFileSync(path.join(ROOT,'tools/real_engine_test.mjs'),'utf8');
let boot=source.slice(0,source.indexOf("if (process.argv.includes('--jcw-smoke'))"));
boot=boot.replace(/^import .*;$/gm,'').replace('const HERE = path.dirname(fileURLToPath(import.meta.url));','const HERE = path.join(repoRoot,"tools");');
boot=boot.replace('const GAME = path.join(ROOT, "c2-sans-fight");','const GAME = gameRoot;');
boot=boot.replace('vm.createContext(sandbox);',`sandbox.location.search='?mode=single&attack='+requestedWave+'&seed=42';sandbox.location.href+='?mode=single&attack='+requestedWave+'&seed=42';vm.createContext(sandbox);`);
boot+='\nreturn {sandbox,rtReal,GAME};';
const AsyncFunction=Object.getPrototypeOf(async function(){}).constructor;
const records=[];
for(const wave of waves){
 const helpers=path.join(ROOT,'c2-sans-fight');
 const bootFS={...fs,readFileSync(p,...args){if(path.basename(p)==='jcw_adapter.js')p=path.join(helpers,'jcw_adapter.js');return fs.readFileSync(p,...args);}};
 const {sandbox:c,rtReal:rt,GAME}=await new AsyncFunction('fs','path','vm','fileURLToPath','process','repoRoot','requestedWave','gameRoot',boot)(bootFS,path,vm,fileURLToPath,process,ROOT,wave,gameRoot);
 // The Haoge export renames the same Param expression from Gt to Ft.
 // This adds an ABI name only; the original expression body still executes.
 if(typeof c.sc?.prototype.g.Gt!=='function'&&typeof c.sc?.prototype.g.Ft==='function')
  vm.runInContext("Object.defineProperty(sc.prototype.g,'Gt',{get(){return this.Ft;}});Object.defineProperty(Object.getPrototypeOf(c2runtime),'all_global_vars',{get(){return this.Fu;}})",c);
 vm.runInContext(fs.readFileSync(path.join(helpers,'solver_state.js'),'utf8'),c);
 const keyboard=()=>rt.types_by_index.flatMap(t=>t.instances).find(i=>Array.isArray(i.keyMap));
 c.TASRunner={getKeyboardInstance:keyboard};
 vm.runInContext(fs.readFileSync(path.join(helpers,'attack_seed.js'),'utf8'),c);
 const csv=fs.readFileSync(path.join(GAME,wave+'.csv'),'utf8');
 const normalized=x=>String(x).replace(/\r/g,'').replace(/^\uFEFF/,'').trim();
 const proto=Object.getPrototypeOf(rt),inner=proto.trigger;
 let started=false,before,entry,ended=false;
 const events=[],damage=[];
 let startingHP=null;
 proto.trigger=function(method,inst,value){
  if(method===c.cr.plugins_.Function.prototype.cnds.OnFunction){
   const fn=String(value).toLowerCase();
   const parameter=index=>{let result;inst.exps.Param({set_any:v=>result=v},index);return result;};
   if(fn==='tlplay'&&normalized(parameter(0))===normalized(csv)){started=true;before=c.NoHitSolverState.capturePhysical(this);}
   if(started&&process.env.NOHIT_GEOMETRY_DEBUG&&fn==='gasterblaster')events.push({tick:this.tickcount,fn,args:Array.from({length:8},(_,i)=>parameter(i))});
   if(started&&['tlplay','tlpause','tlresume','endattack','damageplayer'].includes(fn)){
    const event={tick:this.tickcount,fn};
    if(fn==='damageplayer'){event.amount=Number(parameter(0));event.kr=Number(parameter(1));damage.push(event);}
    events.push(event);if(fn==='endattack')ended=true;
   }
  }
  return inner.apply(this,arguments);
 };
 for(let tick=0;tick<3000;tick++){
  keyboard().keyMap[90]=!started&&tick%4===0;
  rt.tick(true,rt.last_tick_time+period+epsilon,true);
  if(started&&(rt.varsBySid[2569112556112449]?.data>1||ended)){entry=c.NoHitSolverState.capturePhysical(rt);entry.initial_environment=before.initial_environment;entry.initial_arena=before.arena;break;}
  await new Promise(resolve=>setTimeout(resolve,1));
 }
 if(!entry)throw Error(wave+': no original entry');
 entry.dt_schedule=[entry.initial_environment[7]];
 let timestamp=rt.last_tick_time;
 for(let i=1;i<40000;i++){const next=timestamp+period+epsilon;entry.dt_schedule.push(Math.min((next-timestamp)/1000,1/30));timestamp=next;}

 const entryPath=path.join(out,wave+'-entry.json'),planPath=path.join(out,wave+'-optimized.json');
 fs.writeFileSync(entryPath,JSON.stringify(entry));
 if(process.env.NOHIT_CAPTURE_ONLY){console.log(JSON.stringify({wave,captured:true}));continue;}
 const processStarted=performance.now();
 startingHP=entry.HP;
 const solved=spawnSync(python,['-m','tools.solve_csv',path.join(GAME,wave+'.csv'),'--entry',entryPath,'--out',planPath,'--seconds',process.env.NOHIT_SECONDS||'60','--width',process.env.NOHIT_WIDTH||'3000','--search-strategy',process.env.NOHIT_SEARCH_STRATEGY||'auto','--memory-mb',process.env.NOHIT_MEMORY_MB||'64','--workers',process.env.NOHIT_WORKERS||'8',...(healing?['--allow-scripted-healing']:[]),...(scriptedDamage?['--allow-scripted-damage']:[])],{cwd:ROOT,encoding:'utf8'});
 if(solved.status!==0){
  const failed=fs.existsSync(planPath)?JSON.parse(fs.readFileSync(planPath,'utf8')):null;
  records.push({wave,passed:false,reason:failed?.reason||'no_candidate',reached_tick:failed?.reached_tick,
    issues:failed?.issues,csv_sha256:createHash('sha256').update(fs.readFileSync(path.join(GAME,wave+'.csv'))).digest('hex')});
  fs.writeFileSync(path.join(out,'native-summary.json'),JSON.stringify(records.map(({rows,...r})=>r),null,2));
  console.log(JSON.stringify(records.at(-1)));continue;
 }
 const processSeconds=(performance.now()-processStarted)/1000;
 const plan=JSON.parse(fs.readFileSync(planPath,'utf8'));
 const expectedDamage=(plan.scripted_damage_events||[]).map(e=>({...e,tick:entry.tick+e.tick-1}));
 const admitted=e=>scriptedDamage&&expectedDamage.some(x=>x.tick===e.tick&&x.amount===e.amount&&x.kr===e.kr);
 const unexpectedDamage=()=>damage.some(e=>!Number.isFinite(e.amount)||e.amount>=0&&!admitted(e));
 const rows=[entry],mismatches=[];
 for(let tick=0;tick<plan.actions.length;tick++){
  const mask=plan.actions[tick],keys=keyboard().keyMap;keys.fill(false);
  for(const [code,bit] of [[37,1],[39,2],[38,4],[40,8],[88,16]])keys[code]=!!(mask&bit);
  keys[90]=plan.confirm_sequence[tick];rt.tick(true,rt.last_tick_time+period+epsilon,true);
  const row=c.NoHitSolverState.capturePhysical(rt);rows.push(row);
  if(tick+1<plan.actions.length)for(let column=0;column<11;column++)if(row.initial[column]!==plan.trajectory[tick+1][column])mismatches.push({tick:tick+1,column,actual:row.initial[column],expected:plan.trajectory[tick+1][column]});
  const healthBad=healing?!(Number.isFinite(row.HP)&&row.HP>0&&Number.isFinite(row.KR)):(row.HP!==startingHP||row.KR!==0);
  if(healthBad||unexpectedDamage()||mismatches.length){
   if(process.env.NOHIT_GEOMETRY_DEBUG){
    const objects=rt.types_by_index.filter(t=>[165116925986465,728293317807613].includes(t.sid)||t.instances.some(i=>i.instance_vars?.length>8&&i.x>0)).flatMap(t=>t.instances.map(i=>{
     i.update_bbox();return {sid:t.sid,uid:i.uid,x:i.x,y:i.y,width:i.width,height:i.height,angle:i.angle,vars:i.instance_vars,bquad:i.bquad,raw_quad:i.Oa,raw_polygon:i.ga};
    }));
    fs.writeFileSync(path.join(out,wave+'-collision-debug.json'),JSON.stringify({tick:tick+1,objects},null,2));
   }
   break;
  }
  if(ended&&tick+1!==plan.actions.length){mismatches.push({reason:'early_EndAttack',tick:tick+1});break;}
 }
 const passed=ended&&rows.length===plan.actions.length+1&&rows.every(r=>healing?(Number.isFinite(r.HP)&&r.HP>0&&Number.isFinite(r.KR)):(r.HP===startingHP&&r.KR===0))&&!unexpectedDamage()&&(!scriptedDamage||JSON.stringify(damage)===JSON.stringify(expectedDamage.map(e=>({tick:e.tick,fn:'damageplayer',amount:e.amount,kr:e.kr}))))&&mismatches.length===0;
 const sha=p=>createHash('sha256').update(fs.readFileSync(p)).digest('hex');
 const record={wave,passed,scripted_healing_admitted:healing,scripted_damage_admitted:scriptedDamage,expected_scripted_damage:expectedDamage,starting_HP:startingHP,health_contract:scriptedDamage?'alive, zero unexpected DamagePlayer; every script effect matched exactly in amount, KR and tick':healing?'alive, no nonnegative DamagePlayer call; literal healing admitted':'constant initial HP, KR0, no DamagePlayer call',protocol:'unchanged-c2-event-engine-with-dom-audio-render-stubs',clock:fps===30?'30hz-original-dt-clamp':fps+'hz-explicit-native-dt',checkpoint_used:false,native_search_used:false,csv_sha256:sha(path.join(GAME,wave+'.csv')),runtime_sha256:sha(path.join(GAME,'c2runtime.js')),data_sha256:sha(path.join(GAME,'data.js')),plan_sha256:sha(planPath),solver_sha256:Object.fromEntries(fs.readdirSync(path.join(ROOT,'nohit/engine')).filter(n=>/\.(py|cpp)$/.test(n)).map(n=>[n,sha(path.join(ROOT,'nohit/engine',n))])),model_wall_seconds:plan.wall_seconds,process_wall_seconds:processSeconds,search_stats:plan.search_stats,checked_nonterminal_components:Math.max(0,rows.length-2)*11,terminal_scope:'native EndAttack resets player to menu, final states recorded separately',terminal_actual:rows.at(-1).initial,terminal_model:plan.trajectory.at(-1),events,damage,mismatches,rows};
 records.push(record);fs.writeFileSync(path.join(out,wave+'-native-replay.json'),JSON.stringify(record));
 fs.writeFileSync(path.join(out,'native-summary.json'),JSON.stringify(records.map(({rows,...r})=>r),null,2));
 console.log(JSON.stringify({wave,passed,ticks:rows.length-1,solve_seconds:plan.wall_seconds,mismatches:mismatches.slice(0,3)}));
}
process.exit(records.every(r=>r.passed)?0:1);

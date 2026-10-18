/** Unmodified C2 events, fresh solver actions; DOM/audio/render stubs only. */
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import {fileURLToPath} from 'node:url';
import {spawnSync} from 'node:child_process';
import {createHash} from 'node:crypto';
const ROOT=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const out=path.resolve(process.env.NOHIT_BENCH_OUT||path.join(ROOT,'build/native-replay'));
fs.mkdirSync(out,{recursive:true});
const python=process.env.NOHIT_PYTHON||'python';
const gameRoot=path.resolve(process.env.NOHIT_GAME_DIR||path.join(ROOT,'c2-sans-fight'));
const healing=process.env.NOHIT_SCRIPTED_HEALING==='1';
const scriptedDamage=process.env.NOHIT_SCRIPTED_DAMAGE==='1';
const diagnosticPlan=process.env.NOHIT_DIAGNOSTIC_PLAN;
const terminationPolicy=process.env.NOHIT_TERMINATION_POLICY||'endattack';
const fps=Number(process.env.NOHIT_FPS||30);
if(!Number.isFinite(fps)||fps<30)throw Error('NOHIT_FPS must be at least 30');
const period=1000/fps,epsilon=fps===30?1e-6:0;
const waves=process.argv.slice(2);
if(!waves.length)waves.push('sans_bonegap1','sans_bonegap1fast','sans_bluebone','sans_platforms3','sans_platforms4hard');
const source=fs.readFileSync(path.join(ROOT,'tools/real_engine_test.mjs'),'utf8');
let boot=source.slice(0,source.indexOf("if (process.argv.includes('--jcw-smoke'))"));
const clockOrigin=process.env.NOHIT_CLOCK_ORIGIN_MS===undefined?null:Number(process.env.NOHIT_CLOCK_ORIGIN_MS);
if(clockOrigin!==null) {
 if(!Number.isFinite(clockOrigin)||clockOrigin<0)throw Error('Invalid NOHIT_CLOCK_ORIGIN_MS');
 // Declare a reproducible timestamp origin. Physics still receives the exact
 // differences of successive native binary64 timestamps, including rounding.
 boot=boot.replace('performance: { now: () => Number(process.hrtime.bigint() / 1000000n) }',
     `performance: { now: () => ${clockOrigin} }`);
}
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
 const events=[],damage=[],targetReads=[];
 let startingHP=null;
 proto.trigger=function(method,inst,value){
  if(method===c.cr.plugins_.Function.prototype.cnds.OnFunction){
   const fn=String(value).toLowerCase();
   const parameter=index=>{let result;inst.exps.Param({set_any:v=>result=v},index);return result;};
   if(fn==='tlplay'&&normalized(parameter(0))===normalized(csv)){started=true;before=c.NoHitSolverState.capturePhysical(this);}
   if(started&&fn==='getheartpos'){const point=c.NoHitSolverState.capturePhysical(this);targetReads.push([this.tickcount,this.varsBySid[2569112556112449].data,...point.initial.slice(0,2)]);}
   if(started&&process.env.NOHIT_GEOMETRY_DEBUG&&fn==='gasterblaster')events.push({tick:this.tickcount,fn,args:Array.from({length:8},(_,i)=>parameter(i))});
   if(started&&process.env.NOHIT_GEOMETRY_DEBUG&&fn==='blackscreen')events.push({tick:this.tickcount,fn,value:parameter(0),inventory:rt.types_by_index.filter(t=>[3019589746608161,3868174782291034,9590353435551898].includes(t.sid)).map(t=>({sid:t.sid,uids:t.instances.map(i=>i.uid)}))});
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
 entry.initial_target_history=targetReads.filter(([tick])=>tick===entry.tick).map(([,line,x,y])=>[0,line,x,y]);
 entry.dt_schedule=[entry.initial_environment[7]];
 let timestamp=rt.last_tick_time;
 for(let i=1;i<40000;i++){const next=timestamp+period+epsilon;entry.dt_schedule.push(Math.min((next-timestamp)/1000,1/30));timestamp=next;}

 const entryPath=path.join(out,wave+'-entry.json'),planPath=path.join(out,wave+'-optimized.json');
 fs.writeFileSync(entryPath,JSON.stringify(entry));
 if(process.env.NOHIT_CAPTURE_ONLY){console.log(JSON.stringify({wave,captured:true}));continue;}
 const processStarted=performance.now();
 startingHP=entry.HP;
 const observationArgs=['CHUNK_TICKS','PREVIEW_TICKS','PREVIEW_READS','GOAL_STYLE'].flatMap(name=>process.env['NOHIT_OBSERVATION_'+name]===undefined?[]:['--observation-'+name.toLowerCase().replaceAll('_','-'),process.env['NOHIT_OBSERVATION_'+name]]);
 if(process.env.NOHIT_OBJECTIVE)observationArgs.push('--objective',process.env.NOHIT_OBJECTIVE);
 if(process.env.NOHIT_ANALYZE_DIFFICULTY!==undefined)observationArgs.push(process.env.NOHIT_ANALYZE_DIFFICULTY==='1'?'--analyze-difficulty':'--no-analyze-difficulty');
 if(diagnosticPlan) {
  const source=JSON.parse(fs.readFileSync(diagnosticPlan,'utf8')),route=source.failure_diagnostics?.routes?.[Number(process.env.NOHIT_DIAGNOSTIC_ROUTE||0)];
  if(source.csv_sha256!==createHash('sha256').update(fs.readFileSync(path.join(GAME,wave+'.csv'))).digest('hex')||
      route?.prefix_verified!==true||route.complete!==false||JSON.stringify(route.trajectory[0])!==JSON.stringify(entry.initial))throw Error('Diagnostic prefix identity mismatch');
  fs.writeFileSync(planPath,JSON.stringify({...route,csv_sha256:source.csv_sha256,status:'diagnostic_prefix',verified:false}));
 }
 const solved=diagnosticPlan?{status:0}:spawnSync(python,['-m','tools.solve_csv',path.join(GAME,wave+'.csv'),'--entry',entryPath,'--out',planPath,'--seconds',process.env.NOHIT_SECONDS||'60','--width',process.env.NOHIT_WIDTH||'3000','--search-strategy',process.env.NOHIT_SEARCH_STRATEGY||'auto','--memory-mb',process.env.NOHIT_MEMORY_MB||'64','--workers',process.env.NOHIT_WORKERS||'8','--termination-policy',terminationPolicy,...observationArgs,...(healing?['--allow-scripted-healing']:[]),...(scriptedDamage?['--allow-scripted-damage']:[])],{cwd:ROOT,encoding:'utf8'});
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
  if(diagnosticPlan||plan.completion?.kind==='eof_invariant'||tick+1<plan.actions.length)for(let column=0;column<11;column++)if(row.initial[column]!==plan.trajectory[tick+1][column])mismatches.push({tick:tick+1,column,actual:row.initial[column],expected:plan.trajectory[tick+1][column]});
  const healthBad=healing?!(Number.isFinite(row.HP)&&row.HP>0&&Number.isFinite(row.KR)):(row.HP!==startingHP||row.KR!==0);
  if(healthBad||unexpectedDamage()||mismatches.length){
   if(process.env.NOHIT_GEOMETRY_DEBUG){
    const objects=rt.types_by_index.filter(t=>[165116925986465,728293317807613,3019589746608161,3868174782291034,5960708907117077].includes(t.sid)||t.instances.some(i=>i.instance_vars?.length>8&&i.x>0)).flatMap(t=>t.instances.map(i=>{
     i.update_bbox();return {sid:t.sid,uid:i.uid,x:i.x,y:i.y,width:i.width,height:i.height,angle:i.angle,vars:i.instance_vars,bquad:i.bquad,raw_quad:i.Oa,raw_polygon:i.ga};
    }));
    const movement=rt.types_by_index.find(t=>t.sid===5960708907117077).instances[0].behavior_insts.find(b=>b.type.name==='CustomMovement');
    const plugin=c.cr.behaviors?.CustomMovement;
    fs.writeFileSync(path.join(out,wave+'-collision-debug.json'),JSON.stringify({tick:tick+1,objects,movement:movement&&Object.fromEntries(Object.entries(movement).filter(([k,v])=>['number','boolean','string'].includes(typeof v))),moving_predicates:plugin&&Object.entries(plugin.prototype.cnds).map(([k,v])=>[k,String(v)]),},null,2));
   }
   break;
  }
  if(ended&&tick+1!==plan.actions.length){mismatches.push({reason:'early_EndAttack',tick:tick+1});break;}
 }
 const actualTargets=targetReads.map(([tick,...read])=>[tick-(entry.tick-1),...read]);
 const targetHistoryMatches=JSON.stringify(actualTargets)===JSON.stringify(plan.target_history||[]);
 let eofFacts=null,eofSafe=false;
 if(!diagnosticPlan&&plan.completion?.kind==='eof_invariant'&&!ended) {
  const boneSids=[3019589746608161,3868174782291034];
  const attackSids=new Set([3019589746608161,3868174782291034,9836012384209520,7974524067202295,8140934880742138,6503092777075739,4163262150020477,336730486351203,508841962091807,165116925986465,1226268899238104,6981383464931416]);
  for(const sid of [9590353435551898,6631597198329078,9784977049754560])for(const member of rt.types_by_index.find(t=>t.sid===sid).members)attackSids.add(member.sid);
  const inventory=Array.from(attackSids,sid=>({sid,objects:rt.types_by_index.find(t=>t.sid===sid).instances.map(o=>({uid:o.uid,x:o.x,y:o.y,width:o.width,height:o.height,angle:o.angle,vars:o.instance_vars.slice()}))}));
  const actual=rows.at(-1),proof=plan.completion.certificate,blue=inventory.flatMap(t=>t.objects.map(o=>({...o,sid:t.sid})));
  const list=rt.types_by_index.find(t=>t.sid===456555951765879).instances[0];
  const staticBlue=blue.every(o=>boneSids.includes(o.sid)&&o.vars[4]===1&&o.vars[1]===0&&o.angle===0&&[o.x,o.y,o.width,o.height].every(Number.isFinite));
  const expected=proof.terminal_details.static_blue_bones||[];
  const boxes=values=>values.map(row=>row.slice(0,4)).sort((a,b)=>JSON.stringify(a).localeCompare(JSON.stringify(b)));
  const worldMatches=JSON.stringify(boxes(blue.map(o=>[o.x,o.y,o.width,o.height])))===JSON.stringify(boxes(expected));
  const ui=actual.rpgtext||[],passiveUi=ui.length===3&&new Set(ui.map(o=>o.fields?.[0])).size===3&&ui.every(o=>o.typeSid===6163397057824361&&['HP','PlayerName','QuitMessage'].includes(o.fields?.[0])&&[1,2,3].every(i=>o.fields[i]==='')&&[4,5,7].every(i=>o.fields[i]===0));
  eofFacts={inventory,static_blue_only:staticBlue,model_geometry_matches:worldMatches,timeline_line:rt.varsBySid[2569112556112449].data,timeline_width:list.ra,wait_queue_empty:Array.isArray(rt.Hd?.fc)&&rt.Hd.fc.length===0,pending_layout:rt.ih,passive_ui_only:passiveUi,endpoint:actual.initial,arena:actual.arena,proof:proof.proof};
  eofSafe=eofFacts.timeline_line>eofFacts.timeline_width&&staticBlue&&worldMatches&&passiveUi&&eofFacts.wait_queue_empty&&rt.ih===null&&
    actual.arena.callback===''&&actual.arena.target.every((v,i)=>v===actual.initial_environment[i])&&actual.initial.slice(2,5).every(v=>v===0)&&
    actual.initial[6]===0&&actual.vpad.every(v=>v===0)&&actual.physical_keymask===0&&actual.physical_confirm===false&&JSON.stringify(actual.initial)===JSON.stringify(proof.invariant_state)&&plan.actions.slice(-2).every(v=>v===0)&&plan.confirm_sequence.slice(-2).every(v=>v===false)&&
    ['static-empty-release-fixed-point-v1','static-blue-release-fixed-point-v1'].includes(proof.proof);
 }
 const physicalPassed=targetHistoryMatches&&rows.length===plan.actions.length+1&&rows.every(r=>healing?(Number.isFinite(r.HP)&&r.HP>0&&Number.isFinite(r.KR)):(r.HP===startingHP&&r.KR===0))&&!unexpectedDamage()&&(!scriptedDamage||JSON.stringify(damage)===JSON.stringify(expectedDamage.map(e=>({tick:e.tick,fn:'damageplayer',amount:e.amount,kr:e.kr}))))&&mismatches.length===0;
 const passed=!diagnosticPlan&&physicalPassed&&(ended||eofSafe),prefixPassed=!!diagnosticPlan&&physicalPassed;
 const sha=p=>createHash('sha256').update(fs.readFileSync(p)).digest('hex');
 const record={wave,passed,target_history_matches:targetHistoryMatches,target_history:actualTargets,scripted_healing_admitted:healing,scripted_damage_admitted:scriptedDamage,expected_scripted_damage:expectedDamage,starting_HP:startingHP,health_contract:scriptedDamage?'alive, zero unexpected DamagePlayer; every script effect matched exactly in amount, KR and tick':healing?'alive, no nonnegative DamagePlayer call; literal healing admitted':'constant initial HP, KR0, no DamagePlayer call',protocol:'unchanged-c2-event-engine-with-dom-audio-render-stubs',clock:fps===30?'30hz-original-dt-clamp':fps+'hz-explicit-native-dt',checkpoint_used:false,native_search_used:false,csv_sha256:sha(path.join(GAME,wave+'.csv')),runtime_sha256:sha(path.join(GAME,'c2runtime.js')),data_sha256:sha(path.join(GAME,'data.js')),plan_sha256:sha(planPath),solver_sha256:Object.fromEntries(fs.readdirSync(path.join(ROOT,'nohit/engine')).filter(n=>/\.(py|cpp)$/.test(n)).map(n=>[n,sha(path.join(ROOT,'nohit/engine',n))])),model_wall_seconds:plan.wall_seconds,process_wall_seconds:processSeconds,search_stats:plan.search_stats,checked_nonterminal_components:Math.max(0,rows.length-2)*11,terminal_scope:'native EndAttack resets player to menu, final states recorded separately',terminal_actual:rows.at(-1).initial,terminal_model:plan.trajectory.at(-1),events,damage,mismatches,rows};
 Object.assign(record,{prefix_passed:prefixPassed,diagnostic_prefix:!!diagnosticPlan,native_endattack:ended,eof_invariant_passed:eofSafe,native_eof_facts:eofFacts,declared_clock_origin_ms:clockOrigin});
 records.push(record);fs.writeFileSync(path.join(out,wave+'-native-replay.json'),JSON.stringify(record));
 fs.writeFileSync(path.join(out,'native-summary.json'),JSON.stringify(records.map(({rows,...r})=>r),null,2));
 console.log(JSON.stringify({wave,passed,prefix_passed:prefixPassed,eof_invariant_passed:eofSafe,ticks:rows.length-1,solve_seconds:plan.wall_seconds,mismatches:mismatches.slice(0,3)}));
}
process.exit(records.every(r=>diagnosticPlan?r.prefix_passed:r.passed)?0:1);

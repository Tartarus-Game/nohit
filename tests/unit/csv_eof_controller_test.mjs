import assert from 'node:assert/strict';
import fs from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';
import {webcrypto} from 'node:crypto';

const script=fs.readFileSync(new URL('../../c2-sans-fight/csv_round_controller.js',import.meta.url),'utf8');
async function run(options={}) {
  const keys={},rt={tickcount:10,suspended:false,varsBySid:{2569112556112449:{data:2},3521916820909801:{data:0}}};
  const env=[30,200,610,400,0,1,0,1/30,750,0,0,0,0,0,30,200,610,400,30,200,610,400];
  let physical={tick:10,time:1,clock_start_ms:1000,dt:1/30,initial:[320,320,0,0,0,0,0,1,750,0,0],
    initial_environment:env,vpad:Array(14).fill(0),arena:{target:env.slice(0,4),size:[580,200],speed:0,callback:''},
    HP:92,KR:0,timeline:0,running:1,line:2,rpgtext:[],SimulatorMode:2,SingleAttack:'custom',
    initial_confirm:false,previous_confirm:false};
  const state={},step=1000/30+1e-6;
  const window={TASRunner:{getKeyboardInstance:()=>({keyMap:keys})},cr_setSuspended:value=>rt.suspended=value,
    NoHitSolverState:{capture:()=>structuredClone(physical),capturePhysical:()=>structuredClone(physical),
      captureArena:()=>structuredClone(physical.arena)}};
  const context=vm.createContext({window,URLSearchParams,crypto:webcrypto,TextEncoder,Uint8Array,DataView,ArrayBuffer,AbortController,
    fetch:async(url,request)=>{
      const p=JSON.parse(request.body),trajectory=[physical.initial.slice(),physical.initial.slice(),physical.initial.slice(),physical.initial.slice()];
      trajectory[1][4]=2;
      const completion={schema_version:1,kind:options.endattack?'endattack':'eof_invariant',tick:3,model_verified:true,native_verified:false,
        eof_tick:1,drain_tick:1,release_start_tick:2,release_tick_count:2,
        certificate:{status:'proven',proof:'static-empty-release-fixed-point-v1',policy_mask:0,policy_confirm:false,
          invariant_state:trajectory[3].slice(),static_environment:env.slice()}};
      const plan={status:'candidate_found',verified:true,csv_sha256:state.csv_sha256,
        termination_policy:p.termination_policy,
        provenance:{request_id:p.request_id,fresh_computation:true,route_cache_hit:false},control_ticks:1,
        clock_protocol:'explicit_dt_schedule',clock:{schedule_count:p.dt_schedule.length,schedule_sha256:state.request_recipe.schedule_sha256},
        actions:[2,0,0],confirm_sequence:[false,false,false],trajectory,dt_sequence:p.dt_schedule.slice(0,4),
        initial_confirm:false,previous_confirm:false,initial_arena:physical.arena,
        visualization:{frames:[{env}]},target_history:[],completion};
      options.mutatePlan?.(plan);return {ok:true,json:async()=>plan};
    }});
  vm.runInContext(script,context);
  const core=window.NoHitCsvRoundController.create({runtime:rt,clock:{logicalStepMs:step,physicsHz:30},
    query:'max_ticks=20',state,terminationPolicy:options.defaultPolicy?undefined:'eof_hazards_drained',
    captureEof:options.noObserver?undefined:()=>({physical:structuredClone(physical)})});
  core.beginSource({text:'0,HeartMode,0\n'});
  const initial=core.beforeTick();rt.tickcount=11;physical.tick=11;core.afterTick(initial);
  await state.solvePromise;
  const beforePlayback=state.status;
  if(state.status==='playing')for(let i=0;i<3;i++) {
    const token=core.beforeTick();assert(token);
    physical.tick++;rt.tickcount++;physical.initial=state.plan.trajectory[i+1].slice();
    physical.initial_confirm=state.plan.confirm_sequence[i];physical.clock_start_ms+=step;
    physical.dt=state.plan.dt_sequence[i+1];physical.vpad=Array(14).fill(0);
    if(options.tinyMismatch&&i===2)physical.initial[0]+=1e-9;
    if((options.endattack||options.unexpectedEndattack)&&i===2)core.observeFunction('endattack',{});
    core.afterTick(token);if(state.status!=='playing')break;
  }
  return {state,rt,keys,beforePlayback};
}
test('EOF executes the two public neutral frames exactly once and preserves native end flags',async()=>{
  const {state,rt}=await run();assert.equal(state.status,'completed');assert.equal(state.actionsApplied,3);
  assert.equal(state.rows.length,4);assert.equal(rt.tickcount,14);assert.equal(rt.suspended,true);
  assert.equal(state.nativeEndAttack,false);assert.equal(state.complete_in_original_game,false);
  assert.equal(state.original_replay_passed,false);assert.equal(state.safe_forever_under_release,false);
  assert.equal(state.eofTerminal.physical.tick,14);
  assert.equal(state.request.termination_policy,'eof_hazards_drained');
});
test('EndAttack default still requires the real final event',async()=>{
  const {state}=await run({endattack:true,defaultPolicy:true});assert.equal(state.status,'completed');
  assert.equal(state.nativeEndAttack,true);assert.equal(state.request.termination_policy,'endattack');
});
for(const [name,options] of [
  ['default EndAttack policy rejects EOF',{defaultPolicy:true}],
  ['one release frame',{mutatePlan:p=>p.completion.release_tick_count=1}],
  ['nonneutral release',{mutatePlan:p=>p.actions[2]=1}],
  ['Confirm in release',{mutatePlan:p=>p.confirm_sequence[2]=true}],
  ['changed certificate endpoint',{mutatePlan:p=>p.completion.certificate.invariant_state[0]++}],
  ['unsupported certificate version',{mutatePlan:p=>p.completion.schema_version=2}],
  ['claim native verification in backend',{mutatePlan:p=>p.completion.native_verified=true}],
  ['changed termination policy',{mutatePlan:p=>p.termination_policy='endattack'}],
])test(name+' fails before playback',async()=>{
  const {state,beforePlayback}=await run(options);assert.equal(beforePlayback,'failed');assert.equal(state.actionsApplied,0);
});
for(const [name,options] of [
  ['unexpected EndAttack',{unexpectedEndattack:true}],['missing native observer',{noObserver:true}],
  ['tiny final state difference',{tinyMismatch:true}],
])test(name+' rejects completed EOF',async()=>{const {state}=await run(options);assert.equal(state.status,'failed');});

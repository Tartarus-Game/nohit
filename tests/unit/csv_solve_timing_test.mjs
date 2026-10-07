import assert from 'node:assert/strict';
import fs from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';

const script=fs.readFileSync(new URL('../../c2-sans-fight/csv_round_controller.js',import.meta.url),'utf8');
function deferred() {let resolve,reject;const promise=new Promise((yes,no)=>{resolve=yes;reject=no;});return {promise,resolve,reject};}
function boot(options={}) {
    let now=1000,uuid=0;
    const advance=ms=>now+=ms,keys={},requests=[],state={};
    const rt={tickcount:10,suspended:false,varsBySid:{2569112556112449:{data:2},3521916820909801:{data:0}}};
    const env=[30,200,610,400,0,1,0,1/30,750,0,0,0,0,0,30,200,610,400,30,200,610,400];
    const physical={tick:10,time:1,clock_start_ms:1000,dt:1/30,initial:[320,320,0,0,0,0,0,1,750,0,0],
        initial_environment:env,vpad:Array(14).fill(0),arena:{target:env.slice(0,4),size:[580,200],speed:0,callback:''},
        HP:92,KR:0,timeline:0,running:1,line:2,rpgtext:[],SimulatorMode:2,SingleAttack:'custom',
        initial_confirm:false,previous_confirm:false};
    const window={TASRunner:{getKeyboardInstance:()=>({keyMap:keys})},
        cr_setSuspended(value){rt.suspended=value;if(!value)advance(23);},
        NoHitSolverState:{capture:()=>structuredClone(physical),capturePhysical:()=>structuredClone(physical),
            captureArena:()=>structuredClone(physical.arena)}};
    function candidate(payload) {
        return {status:'candidate_found',verified:true,csv_sha256:state.csv_sha256,
            provenance:{request_id:payload.request_id,fresh_computation:true,route_cache_hit:false},control_ticks:1,
            clock_protocol:'explicit_dt_schedule',clock:{schedule_count:payload.dt_schedule.length,schedule_sha256:state.request_recipe.schedule_sha256},
            actions:[0],confirm_sequence:[false],trajectory:[physical.initial.slice(),physical.initial.slice()],
            dt_sequence:payload.dt_schedule.slice(0,2),initial_confirm:false,previous_confirm:false,
            initial_arena:physical.arena,visualization:{frames:[{env}]},target_history:[]};
    }
    const context=vm.createContext({window,URLSearchParams,TextEncoder,Uint8Array,ArrayBuffer,DataView,AbortController,
        performance:{now:()=>now},crypto:{subtle:{async digest(){advance(3);return new Uint8Array(32).buffer;}},randomUUID:()=>`request-${++uuid}`},
        fetch:async(url,request)=>{
            const payload=JSON.parse(request.body);requests.push({payload,signal:request.signal});advance(11);
            await options.fetch?.({payload,request,advance});
            return {ok:!options.httpError,json:async()=>{
                advance(13);await options.json?.({advance});
                const plan=options.unknown?.(requests.length)?{status:'unknown',verified:false,reason:'budget'}:candidate(payload);
                options.mutatePlan?.(plan);return plan;
            }};
        }});
    vm.runInContext(script,context);
    const core=window.NoHitCsvRoundController.create({runtime:rt,clock:{logicalStepMs:1000/30+1e-6,physicsHz:30},
        query:'max_ticks=20',state,
        async prepare(){advance(2);await options.prepare?.();},
        onPlan(){advance(17);options.onPlan?.();},
        onStatus(value){if(value==='playing')advance(19);options.onStatus?.(value);}});
    function start() {
        core.beginSource({text:'0,HeartMode,0\n'});
        const token=core.beforeTick();rt.tickcount=11;physical.tick=11;core.afterTick(token);
        return state.solvePromise;
    }
    return {core,state,rt,keys,requests,physical,advance,start};
}
function plain(value) {return JSON.parse(JSON.stringify(value));}
function assertPartition(attempt) {
    assert.equal(attempt.total_ms,attempt.prepare_ms+attempt.fetch_json_ms+attempt.validation_ms);
    assert.equal(attempt.finished_at_ms-attempt.started_at_ms,attempt.total_ms);
}

test('full attempt includes prepare, fetch/body/JSON and candidate validation/installation',async()=>{
    const g=boot();await g.start();assert.equal(g.state.status,'playing');
    const timing=g.state.solve_timing,attempt=timing.attempts[0];
    assert.equal(timing.clock,'performance.now');assert.equal(attempt.outcome,'candidate_ready');
    assert.equal(attempt.request_id,'request-1');assert.equal(attempt.prepare_ms,8);
    assert.equal(attempt.fetch_json_ms,24);assert.equal(attempt.validation_ms,59);assert.equal(attempt.total_ms,91);
    assertPartition(attempt);assert.equal(timing.cumulative.total_ms,91);
    g.advance(5000);g.core.fail('playback failure');assert.equal(attempt.outcome,'candidate_ready');
    assert.equal(timing.cumulative.total_ms,91);assert.equal(timing.attempts.length,1);
});
test('unknown and retry retain separate attempts while excluding user idle time',async()=>{
    const g=boot({unknown:n=>n===1});await g.start();assert.equal(g.state.status,'unknown');
    const first=g.state.solve_timing.attempts[0];assert.equal(first.outcome,'unknown');assert.equal(first.total_ms,49);
    g.advance(120000);await g.core.retry({seconds:60});
    const timing=g.state.solve_timing;assert.equal(timing.attempts.length,2);
    assert.equal(timing.attempts[1].request_id,'request-2');assert.equal(timing.attempts[1].outcome,'candidate_ready');
    assert.equal(timing.cumulative.total_ms,140);assert.equal(timing.cumulative.finished_attempts,2);
    timing.attempts.forEach(assertPartition);
});
for(const [label,options,phase,requestId] of [
    ['prepare rejects',{prepare:()=>Promise.reject(Error('prepare failed'))},'prepare',null],
    ['fetch rejects',{fetch:()=>Promise.reject(Error('network failed'))},'fetch_json','request-1'],
    ['body JSON rejects',{json:()=>Promise.reject(Error('parse failed'))},'fetch_json','request-1'],
    ['HTTP error',{httpError:true},'validation','request-1'],
    ['plan validation fails',{mutatePlan:p=>p.verified=false},'validation','request-1'],
    ['installation callback throws',{onPlan:()=>{throw Error('onPlan failed');}},'validation','request-1'],
])test(label+' finalizes the correct attempt exactly once',async()=>{
    const g=boot(options);await g.start();assert.equal(g.state.status,'failed');
    const timing=g.state.solve_timing,attempt=timing.attempts[0];
    assert.equal(attempt.outcome,'failed');assert.equal(attempt.last_phase,phase);assert.equal(attempt.request_id,requestId);
    assertPartition(attempt);const old=plain(timing.cumulative);g.advance(2000);g.core.cancel();
    assert.deepEqual(plain(timing.cumulative),old);assert.equal(attempt.outcome,'failed');
});
for(const phase of ['fetch','json'])for(const late of ['resolve','reject'])test('cancel closes '+phase+' immediately; late '+late+' cannot extend totals or install a candidate',async()=>{
    const gate=deferred(),entered=deferred(),g=boot({[phase]:()=>{entered.resolve();return gate.promise;}});
    const solving=g.start();await entered.promise;g.advance(7);g.core.cancel();
    const timing=g.state.solve_timing,attempt=timing.attempts[0],total=attempt.total_ms;
    assert.equal(attempt.outcome,'aborted');assert.equal(attempt.request_id,'request-1');assert.equal(g.requests[0].signal.aborted,true);
    assertPartition(attempt);g.advance(9000);late==='resolve'?gate.resolve():gate.reject(Error('late failure'));await solving;
    assert.equal(g.state.status,'cancelled');assert.equal(g.state.plan,null);assert.equal(attempt.total_ms,total);
    assert.equal(timing.cumulative.total_ms,total);assert.equal(timing.cumulative.finished_attempts,1);
    assert.equal(attempt.late_settlement.outcome,'stale');assert.equal(attempt.late_settlement.kind,late==='resolve'?'response':'error');
});
test('a failed retry preparation cannot inherit the previous request id',async()=>{
    let prepares=0;
    const g=boot({unknown:()=>true,prepare:()=>{if(++prepares===2)throw Error('retry prepare failed');}});
    await g.start();g.advance(100000);await g.core.retry({seconds:60});
    const timing=g.state.solve_timing;assert.equal(timing.attempts[0].request_id,'request-1');
    assert.equal(timing.attempts[1].request_id,null);assert.equal(timing.attempts[1].outcome,'failed');
    assert.equal(timing.cumulative.total_ms,51);assert.equal(timing.cumulative.finished_attempts,2);
});
test('a solve status hook rejection is observed without swallowing the existing rejection',async()=>{
    const g=boot({onStatus:value=>{if(value==='solving')throw Error('status hook failed');}});
    await assert.rejects(g.start(),/status hook failed/);
    const attempt=g.state.solve_timing.attempts[0];assert.equal(attempt.outcome,'failed');
    assert.equal(attempt.request_id,null);assert.equal(attempt.last_phase,'prepare');assertPartition(attempt);
});
test('cancel during preparation records a null request id and excludes its late completion',async()=>{
    const gate=deferred(),g=boot({prepare:()=>gate.promise});const solving=g.start();
    g.advance(9);g.core.cancel();const attempt=g.state.solve_timing.attempts[0];
    assert.equal(attempt.outcome,'aborted');assert.equal(attempt.request_id,null);assert.equal(attempt.total_ms,11);
    g.advance(1000);gate.resolve();await solving;
    assert.equal(g.requests.length,0);assert.equal(attempt.total_ms,11);assert.equal(attempt.late_settlement.outcome,'stale');
});

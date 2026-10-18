import assert from 'node:assert/strict';
import fs from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';

const script=fs.readFileSync(new URL('../../c2-sans-fight/csv_round_controller.js',import.meta.url),'utf8');
function deferred() {let resolve,reject;const promise=new Promise((yes,no)=>{resolve=yes;reject=no;});return {promise,resolve,reject};}
function boot(options={}) {
    let now=1000,uuid=0;
    const advance=ms=>now+=ms,keys={},requests=[],state={},polls=[],timers=new Map(),elements=new Map(),messages=[];
    function element(tag='div') {
        return {tagName:tag.toUpperCase(),textContent:'',style:{},children:[],hidden:false,
            insertBefore(line){return this.appendChild(line);},
            appendChild(line){
                if(line.parentNode)line.parentNode.removeChild(line);
                this.children.push(line);line.parentNode=this;if(line.id)elements.set(line.id,line);return line;
            },removeChild(line){this.children=this.children.filter(child=>child!==line);line.parentNode=null;}};
    }
    const hud=element();hud.id='tas-controller-overlay';elements.set(hud.id,hud);
    const badge=element();badge.id='tas-status-badge';hud.appendChild(badge);
    const clockStatus=element();clockStatus.id='tas-clock-status';clockStatus.textContent='卡顿补偿：暂停';hud.appendChild(clockStatus);
    const rt={tickcount:10,suspended:false,varsBySid:{2569112556112449:{data:2},3521916820909801:{data:0}}};
    const env=[30,200,610,400,0,1,0,1/30,750,0,0,0,0,0,30,200,610,400,30,200,610,400];
    const physical={tick:10,time:1,clock_start_ms:1000,dt:1/30,initial:[320,320,0,0,0,0,0,1,750,0,0],
        initial_environment:env,vpad:Array(14).fill(0),arena:{target:env.slice(0,4),size:[580,200],speed:0,callback:''},
        HP:92,KR:0,timeline:0,running:1,line:2,rpgtext:[],SimulatorMode:2,SingleAttack:'custom',
        initial_confirm:false,previous_confirm:false};
    const window={TASRunner:{getKeyboardInstance:()=>({keyMap:keys})},
        ...(options.opener?{location:{origin:'http://localhost:8765'},opener:{closed:false,
            postMessage:(message,origin)=>messages.push({message,origin})}}:{}),
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
        ...(options.progress?{document:{getElementById:id=>elements.get(id)||null,createElement:tag=>element(tag)},
            setInterval:callback=>{const id=timers.size+1;timers.set(id,callback);return id;},clearInterval:id=>timers.delete(id)}:{}),
        fetch:async(url,request)=>{
            if(url.startsWith('/api/progress/')) {
                polls.push(url);const snap=await options.progress({url,advance,polls});
                return {ok:true,json:async()=>snap};
            }
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
        query:options.query||'max_ticks=20',state,
        async prepare(){advance(2);await options.prepare?.();},
        onPlan(){advance(17);options.onPlan?.();},
        onStatus(value){if(value==='playing')advance(19);options.onStatus?.(value);}});
    function start() {
        core.beginSource({text:'0,HeartMode,0\n',warnings:options.warnings});
        const token=core.beforeTick();rt.tickcount=11;physical.tick=11;core.afterTick(token);
        return state.solvePromise;
    }
    return {core,state,rt,keys,requests,physical,advance,start,polls,timers,elements,messages,
        pulse:()=>timers.values().next().value?.()};
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

test('explicit observation query options reach the solver request and reproducible recipe',async()=>{
    const g=boot({query:'max_ticks=20&observation_chunk_ticks=480&observation_preview_ticks=480&observation_preview_reads=128&observation_goal_retries=1&workers=4'});
    await g.start();assert.equal(g.state.status,'playing');
    const expected={observation_chunk_ticks:480,observation_preview_ticks:480,
        observation_preview_reads:128,observation_goal_retries:true,workers:4};
    for(const [key,value] of Object.entries(expected)) {
        assert.equal(g.requests[0].payload[key],value);
        assert.equal(g.state.request_recipe[key],value);
    }
});
test('observation options stay omitted by default and preserve an explicit disabled retry flag',async()=>{
    const basic=boot();await basic.start();
    for(const key of ['observation_chunk_ticks','observation_preview_ticks','observation_preview_reads','observation_goal_retries','workers']) {
        assert.equal(Object.hasOwn(basic.requests[0].payload,key),false);
        assert.equal(Object.hasOwn(basic.state.request_recipe,key),false);
    }
    const disabled=boot({query:'max_ticks=20&observation_goal_retries=0'});await disabled.start();
    assert.equal(disabled.requests[0].payload.observation_goal_retries,false);
    assert.equal(disabled.state.request_recipe.observation_goal_retries,false);
});

test('human-friendly mode and analysis switches survive native round handoff',async()=>{
    for(const [flag,value] of [['true',true],['false',false],['1',true],['0',false]]) {
        const g=boot({query:`max_ticks=20&objective=human_friendly&analyze_difficulty=${flag}`});await g.start();
        assert.equal(g.requests[0].payload.objective,'human_friendly');
        assert.equal(g.requests[0].payload.analyze_difficulty,value);
        assert.equal(g.state.request_recipe.analyze_difficulty,value);
    }
});

test('native HUD shows time before telemetry and keeps counting through unchanged server counters',async()=>{
    const gate=deferred(),entered=deferred(),snap={state:'running',phase:'compile',elapsed_seconds:.25,
        tick:0,ticks:100,alive_states:null,expanded_states:0,fraction:0,fraction_basis:'tick_horizon'};
    const g=boot({fetch:()=>{entered.resolve();return gate.promise;},progress:()=>snap});
    const solving=g.start();await entered.promise;
    const line=g.elements.get('csv-solve-progress');assert(line,'show the solve immediately, before the first poll');
    assert.match(line.textContent,/解算中.*已用/);
    assert.equal(g.elements.get('csv-progress-dashboard-link').href,'/?progress_id='+g.requests[0].payload.progress_id);
    await g.pulse();assert.match(line.textContent,/编译/);assert.equal(g.state.solve_progress,snap);
    g.advance(5000);await g.pulse();assert.match(line.textContent,/已用 5\.0s/);
    assert.match(line.textContent,/阶段处理中/);assert.match(line.textContent,/tick 0\/100/);
    assert.doesNotMatch(line.textContent,/%|预计剩余|ETA/);assert.equal(snap.elapsed_seconds,.25);
    gate.resolve();await solving;
});

test('a slow progress response cannot block elapsed time or apply after cancellation',async()=>{
    const gate=deferred(),entered=deferred(),poll=deferred();
    const g=boot({fetch:()=>{entered.resolve();return gate.promise;},progress:()=>poll.promise});
    const solving=g.start();await entered.promise;const pending=g.pulse();g.advance(3000);await g.pulse();
    const line=g.elements.get('csv-solve-progress');assert.match(line.textContent,/已用 3\.0s/);
    g.core.cancel();const text=line.textContent;assert.equal(g.timers.size,0);
    poll.resolve({state:'running',phase:'search',elapsed_seconds:7,tick:50,ticks:100});await pending;
    assert.equal(g.state.solve_progress,null);assert.equal(line.textContent,text);
    assert.match(line.textContent,/已取消/);gate.resolve();await solving;
});

test('terminal telemetry keeps its raw fraction without displaying percentages or ETA',async()=>{
    const gate=deferred(),entered=deferred(),snap={state:'done',phase:'search',elapsed_seconds:2,
        tick:40,ticks:100,fraction:.4,fraction_basis:'tick_horizon',expanded_states:120};
    const g=boot({fetch:()=>{entered.resolve();return gate.promise;},progress:()=>snap});
    const solving=g.start();await entered.promise;await g.pulse();
    const line=g.elements.get('csv-solve-progress');assert(line);assert.match(line.textContent,/解算已结束/);
    assert.doesNotMatch(line.textContent,/%|预计剩余|ETA/);assert.equal(snap.fraction,.4);
    assert.equal(g.state.solve_progress,snap);assert.equal(g.timers.size,0);
    gate.resolve();await solving;assert.equal(g.elements.get('csv-solve-progress'),line);
    assert.equal(g.state.solve_progress,snap);
});

test('a supplied progress identity is shared with provenance once and retries receive fresh identities',async()=>{
    const g=boot({query:'max_ticks=20&progress_id=dashboard-shared',unknown:n=>n===1,opener:true});
    await g.start();const first=g.requests[0].payload;
    assert.equal(first.progress_id,'dashboard-shared');assert.equal(first.request_id,first.progress_id);
    assert.equal(g.state.request_recipe.progress_id,first.progress_id);
    await g.core.retry({seconds:60});const second=g.requests[1].payload;
    assert.equal(second.progress_id,second.request_id);assert.notEqual(second.progress_id,first.progress_id);
    assert.equal(g.state.plan.provenance.request_id,second.progress_id);
    const statuses=g.messages.filter(row=>row.message.type==='nohit:csv-status').map(row=>row.message);
    assert.deepEqual(statuses.map(row=>[row.progress_id,row.previous_progress_id,row.status]),[
        ['dashboard-shared',null,'solving'],['dashboard-shared',null,'unknown'],
        [second.progress_id,'dashboard-shared','solving'],[second.progress_id,'dashboard-shared','playing']]);
    const results=g.messages.filter(row=>row.message.type==='nohit:csv-result');assert.equal(results.length,2);
    for(const result of results) {
        assert.equal(result.origin,'http://localhost:8765');
        const position=g.messages.indexOf(result),next=g.messages[position+1].message;
        assert.equal(next.type,'nohit:csv-status');assert.equal(next.progress_id,result.message.progress_id);
        if(result.message.result.status==='candidate_found')assert.equal(result.message.result.provenance.request_id,next.progress_id);
    }
});

test('an invalid candidate never reaches the dashboard as a verified result',async()=>{
    const g=boot({opener:true,mutatePlan:plan=>plan.provenance.request_id='foreign'});await g.start();
    assert.equal(g.state.status,'failed');assert(!g.messages.some(row=>row.message.type==='nohit:csv-result'));
    assert.equal(g.messages.at(-1).message.status,'failed');
});

test('preparation rejection notifies the dashboard using the shared identity before any request exists',async()=>{
    const g=boot({query:'max_ticks=20&progress_id=early-shared',opener:true,
        prepare:()=>Promise.reject(Error('prepare refused'))});
    await g.start();assert.equal(g.state.status,'failed');assert.equal(g.requests.length,0);
    assert.equal(g.state.solve_timing.attempts[0].request_id,null);
    const statuses=g.messages.filter(row=>row.message.type==='nohit:csv-status').map(row=>row.message);
    assert.deepEqual(statuses.map(row=>[row.progress_id,row.previous_progress_id,row.status]),[
        ['early-shared',null,'solving'],['early-shared',null,'failed']]);
    assert.match(statuses.at(-1).error,/prepare refused/);
    assert(!g.messages.some(row=>row.message.type==='nohit:csv-result'));
});

test('retry preparation rejection reserves a fresh identity and reports its failed transition',async()=>{
    let prepares=0;
    const g=boot({query:'max_ticks=20&progress_id=retry-early-shared',opener:true,unknown:()=>true,
        prepare:()=>{if(++prepares===2)throw Error('retry preparation refused');}});
    await g.start();await g.core.retry({seconds:60});assert.equal(g.state.status,'failed');
    assert.equal(g.requests.length,1);assert.equal(g.state.solve_timing.attempts[1].request_id,null);
    const statuses=g.messages.filter(row=>row.message.type==='nohit:csv-status').map(row=>row.message);
    const retryId=statuses.at(-1)?.progress_id;assert.notEqual(retryId,'retry-early-shared');
    assert.deepEqual(statuses.map(row=>[row.progress_id,row.previous_progress_id,row.status]),[
        ['retry-early-shared',null,'solving'],['retry-early-shared',null,'unknown'],
        [retryId,'retry-early-shared','solving'],[retryId,'retry-early-shared','failed']]);
    assert.match(statuses.at(-1).error,/retry preparation refused/);
});

test('native HUD collapses during playback and completion while keeping warning and counter details accessible',async()=>{
    const gate=deferred(),entered=deferred(),g=boot({warnings:[{line:2,command:'DamagePlayer',reason:'scripted_damage_disabled'}],
        fetch:()=>{entered.resolve();return gate.promise;},
        progress:()=>({state:'running',phase:'search',elapsed_seconds:1,tick:12,ticks:20,alive_states:22})});
    const solving=g.start();await entered.promise;await g.pulse();
    const panel=g.elements.get('csv-hud-details'),summary=g.elements.get('csv-hud-summary'),body=g.elements.get('csv-hud-body');
    assert(panel,'native telemetry has an accessible foldable panel');assert.equal(panel.open,true);
    assert.equal(g.elements.get('csv-source-warnings').parentNode,body);
    assert.equal(g.elements.get('csv-solve-progress').parentNode,body);
    assert.equal(g.elements.get('tas-clock-status').parentNode,body);
    panel.open=false;panel.ontoggle();g.advance(1000);await g.pulse();
    assert.equal(panel.open,false,'a telemetry refresh respects a manual collapse');
    gate.resolve();await solving;assert.equal(g.state.status,'playing');assert.equal(panel.open,false);
    assert.match(summary.textContent,/执行中.*解算.*详情/);assert.doesNotMatch(summary.textContent,/tick|前沿|警告|预算/);
    assert.match(g.elements.get('csv-source-warnings').textContent,/已禁用/);
    panel.open=true;panel.ontoggle();assert.match(summary.textContent,/收起/);
    const lateStatus={id:'late-clock-status',textContent:'后续时钟状态'};
    const overlay=g.elements.get('tas-controller-overlay');overlay.appendChild(lateStatus);panel.ontoggle();
    assert.equal(lateStatus.parentNode,body);assert.deepEqual(overlay.children,[panel]);
    const token=g.core.beforeTick();g.physical.tick++;g.rt.tickcount++;
    g.physical.dt=g.state.plan.dt_sequence[1];g.core.observeFunction('endattack');g.core.afterTick(token);
    assert.equal(g.state.status,'completed');assert.equal(panel.open,false);assert.match(summary.textContent,/已完成.*详情/);
    assert.equal(g.elements.get('tas-controller-overlay').style.left,'auto');
    assert.equal(g.elements.get('tas-controller-overlay').style.right,'8px');
});

test('native HUD uses only backend ETA evidence and shows estimating when it is unavailable',async()=>{
    const gate=deferred(),entered=deferred();let snap={state:'running',phase:'search',fraction:.8,fraction_basis:'wall_budget'};
    const g=boot({fetch:()=>{entered.resolve();return gate.promise;},progress:()=>snap});
    const solving=g.start();await entered.promise;await g.pulse();const line=g.elements.get('csv-solve-progress');
    assert.match(line.textContent,/估算中/);assert.doesNotMatch(line.textContent,/预计剩余|%/);
    snap={...snap,eta_seconds:12.3,eta_basis:'csv_literal_duration_estimate'};await g.pulse();
    assert.match(line.textContent,/预计剩余约 13秒/);assert.equal(g.state.solve_progress,snap);
    snap={...snap,eta_seconds:-2};await g.pulse();assert.match(line.textContent,/估算中/);
    snap={...snap,eta_seconds:12.3,eta_basis:'unknown'};await g.pulse();assert.match(line.textContent,/估算中/);
    gate.resolve();await solving;assert.doesNotMatch(g.elements.get('csv-hud-summary').textContent,/预计剩余|估算中/);
});

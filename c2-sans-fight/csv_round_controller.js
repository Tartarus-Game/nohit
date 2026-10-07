// One source-model witness continues an observed native round. This module
// installs no runtime hooks; Custom and Normal own their respective wrappers.
(() => {
    const ownedKeys=[37,38,39,40,65,68,83,87,88,16,90,13];
    const blocked=new Set(['solving','unknown','failed','completed','cancelled']);
    const finite=value=>typeof value==='number'&&Number.isFinite(value);
    const vector=(value,size)=>Array.isArray(value)&&value.length===size&&value.every(finite);
    function parameter(inst,index=0) {
        const result={value:null,set_any(v){this.value=v;},set_int(v){this.value=v;},set_float(v){this.value=v;},set_string(v){this.value=v;}};
        inst.exps.Param(result,index);return result.value;
    }
    async function digest(bytes) {
        const hash=await crypto.subtle.digest('SHA-256',bytes);
        return Array.from(new Uint8Array(hash),byte=>byte.toString(16).padStart(2,'0')).join('');
    }
    async function scheduleDigest(schedule) {
        const bytes=new ArrayBuffer(schedule.length*8),view=new DataView(bytes);
        schedule.forEach((value,index)=>view.setFloat64(index*8,value,true));
        return digest(bytes);
    }
    function create(options) {
        const rt=options.runtime,clock=options.clock,query=new URLSearchParams(options.query||'');
        const terminationPolicy=options.terminationPolicy||'endattack';
        if(!['endattack','eof_hazards_drained'].includes(terminationPolicy))throw Error('Invalid CSV termination policy');
        const C=options.state||{};
        Object.assign(C,{version:1,status:'waiting_source',error:null,plan:null,boundary:null,
            actionsApplied:0,rows:[],events:[],firstDamage:null,nativeEndAttack:false,endSnapshot:null,
            original_replay_passed:false,complete_in_original_game:false,safe_forever_under_release:false,
            termination_policy:terminationPolicy,completion_kind:null,eofTerminal:null});
        let requestId=0,pending=null,source=null,activeText=null,endEvent=null,abort=null,activeTiming=null;
        // Live solve telemetry lives here, in the controller both the Custom shell
        // and the Normal campaign share, so every entry shows the same numbers.
        // Hosts without timers (the Node controller harnesses) simply never poll.
        let progressTimer=null;
        function progressLine(){
            // Hosts without a DOM (controller harnesses) get no line, never an error.
            if(typeof document==='undefined'||typeof document.createElement!=='function')return null;
            let line=document.getElementById('csv-solve-progress');
            if(line)return line;
            const badge=document.getElementById('tas-status-badge');
            if(!badge||!badge.parentNode)return null;
            line=document.createElement('div');
            line.id='csv-solve-progress';
            line.className='tas-badge';
            line.style.marginTop='4px';line.style.fontVariantNumeric='tabular-nums';
            badge.parentNode.insertBefore(line,badge.nextSibling);
            return line;
        }
        function progressText(snap){
            const finite=value=>typeof value==='number'&&Number.isFinite(value);
            const count=value=>Number.isInteger(value)?value.toLocaleString('en-US'):'—';
            const phases={prepare:'准备',compile:'编译',bake:'烘焙 C-space',search:'搜索前沿',
                dialogue:'对话',completion:'终点证书',verify:'逐帧复核',visualization:'逐帧几何'};
            const elapsed=finite(snap.elapsed_seconds)?snap.elapsed_seconds.toFixed(1)+'s':'—';
            const eta=(finite(snap.fraction)&&snap.fraction>=0.02&&finite(snap.elapsed_seconds))
                ?(snap.elapsed_seconds*(1-snap.fraction)/snap.fraction).toFixed(1)+'s':'—';
            return `解算 · ${phases[snap.phase]||snap.phase||''} · ${elapsed}`
                +` · 前沿 ${count(snap.alive_states)} · 展开 ${count(snap.expanded_states)}`
                +` · ${finite(snap.states_per_second)?Math.round(snap.states_per_second).toLocaleString('en-US'):'—'} 态/秒`
                +` · tick ${Number.isInteger(snap.tick)?snap.tick:'—'}/${Number.isInteger(snap.ticks)?snap.ticks:'—'}`
                +` · 预计剩余 ${eta}`;
        }
        function stopProgressWatch(){
            if(progressTimer!==null&&typeof clearInterval==='function'){clearInterval(progressTimer);progressTimer=null;}
            try {
                if(typeof document==='undefined'||typeof document.getElementById!=='function')return;
                const line=document.getElementById('csv-solve-progress');
                if(line&&line.parentNode)line.parentNode.removeChild(line);
            } catch(error) { /* the HUD is observation; it must never break a solve */ }
        }
        function startProgressWatch(){
            if(progressTimer!==null||typeof setInterval!=='function')return;
            progressTimer=setInterval(async () => {
                const id=C.request&&C.request.progress_id;
                if(!id)return;
                try {
                    const reply=await fetch('/api/progress/'+encodeURIComponent(id));
                    if(!reply.ok)return;
                    const snap=await reply.json();
                    C.solve_progress=snap;
                    try {
                        const line=progressLine();
                        if(line)line.textContent=progressText(snap);
                    } catch(error) { /* HUD only */ }
                    if(snap.state==='done'||snap.state==='failed')stopProgressWatch();
                } catch(error) { /* observation only; the solve owns the outcome */ }
            },250);
        }
        const timingClock=typeof globalThis.performance?.now==='function'?'performance.now':'Date.now';
        const timingNow=()=>timingClock==='performance.now'?globalThis.performance.now():Date.now();
        const timingFields=['prepare_ms','fetch_json_ms','validation_ms','total_ms'];
        // Wall time of each solve invocation, not CPU time or the interval between retries.
        // The three phases partition total; server request_seconds is nested in fetch_json.
        C.solve_timing={schema_version:1,clock:timingClock,units:'milliseconds',
            scope:{prepare:'solve entry, prepare hook, CSV hash, clock schedule/hash and request construction',
                fetch_json:'request JSON serialization, fetch/server/response transfer, body read and JSON parsing',
                validation:'response checks, onPlan hook, validation and candidate installation or result handling',
                total:'solve entry through candidate ready, unknown, failure, abort or stale detection; excludes playback and retry idle'},
            attempts:[],cumulative:{finished_attempts:0,prepare_ms:0,fetch_json_ms:0,validation_ms:0,total_ms:0}};
        function beginTiming(generation) {
            const started=timingNow(),record={generation,request_id:null,outcome:null,started_at_ms:started,
                finished_at_ms:null,prepare_ms:0,fetch_json_ms:0,validation_ms:0,total_ms:null,last_phase:'prepare'};
            const timing={record,phase:'prepare',phaseStart:started};
            C.solve_timing.attempts.push(record);activeTiming=timing;return timing;
        }
        function timingPhase(timing,phase,at=timingNow()) {
            if(timing.record.outcome!==null)return;
            timing.record[timing.phase+'_ms']+=at-timing.phaseStart;
            timing.phase=phase;timing.phaseStart=at;timing.record.last_phase=phase;
        }
        function finishTiming(timing,outcome,error=null) {
            if(!timing||timing.record.outcome!==null)return;
            const at=timingNow(),record=timing.record;
            record[timing.phase+'_ms']+=at-timing.phaseStart;
            Object.assign(record,{outcome,finished_at_ms:at,total_ms:at-record.started_at_ms});
            if(error!==null)record.error=String(error);
            const totals=C.solve_timing.cumulative;totals.finished_attempts++;
            for(const key of timingFields)totals[key]+=record[key];
            if(activeTiming===timing)activeTiming=null;
        }
        function staleTiming(timing,kind,error=null) {
            if(timing.record.outcome===null)finishTiming(timing,'stale',error);
            else if(!timing.record.late_settlement) {
                const at=timingNow();
                timing.record.late_settlement={outcome:'stale',kind,observed_at_ms:at,
                    after_finish_ms:at-timing.record.finished_at_ms};
                if(error!==null)timing.record.late_settlement.error=String(error);
            }
        }
        function status(value) {C.status=value;options.onStatus?.(value,C);}
        function capture() {return window.NoHitSolverState.capturePhysical(rt);}
        function input(mask,confirm) {
            // Menus may use Cancel; candidate validation below restricts the
            // combat search to arrows plus a separate Confirm sequence.
            if(!Number.isInteger(mask)||mask<0||mask>31||typeof confirm!=='boolean')throw Error('Invalid physical control');
            const keys=window.TASRunner?.getKeyboardInstance()?.keyMap;
            if(!keys)throw Error('Original keyboard is not ready');
            for(const code of ownedKeys)keys[code]=false;
            for(const [bit,code] of [[1,37],[2,39],[4,38],[8,40],[16,88]])keys[code]=!!(mask&bit);
            keys[90]=confirm;
        }
        function release() {try{input(0,false);}catch{/* Keyboard may not exist during startup. */}}
        function stop(reason,state='failed') {
            const timing=activeTiming;
            try {
                ++requestId;abort?.abort();C.error=String(reason);status(state);release();
                window.cr_setSuspended(true);
            } finally {finishTiming(timing,state==='cancelled'?'aborted':'failed',reason);}
        }
        function boundaryKey(value) {
            return JSON.stringify([value.initial,value.initial_environment,value.vpad,value.clock_start_ms,
                value.tick,value.time,value.timeline,value.running,value.line,value.HP,value.KR,value.rpgtext,value.arena,
                value.SimulatorMode,value.SingleAttack]);
        }
        function noDamage(value) {return value.HP===92&&value.KR===0&&!C.firstDamage;}
        function record(value,mask=null,confirm=null) {
            C.rows.push({tick:value.tick,time:value.time,dt:value.dt,clock_start_ms:value.clock_start_ms,
                state:value.initial.slice(),vpad:value.vpad.slice(),HP:value.HP,KR:value.KR,
                line:value.line,T:value.timeline,running:value.running,mask,confirm});
        }
        function nativeSchedule(boundary,count) {
            if(!Number.isInteger(count)||count<1)throw Error('Invalid native clock horizon');
            const step=clock.logicalStepMs;
            if(!finite(step)||step<=0||!finite(boundary.clock_start_ms)||!finite(boundary.dt)||boundary.dt<=0||boundary.dt>1/30)
                throw Error('Native clock boundary is incomplete');
            const result=[boundary.dt];let timestamp=boundary.clock_start_ms;
            for(let i=1;i<count;i++) {
                const next=timestamp+step,dt=Math.min((next-timestamp)/1000,1/30);
                if(!finite(dt)||dt<=0)throw Error('Native timestamp no longer advances');
                result.push(dt);timestamp=next;
            }
            return result;
        }
        function sourceIsCurrent() {
            return source&&source.text===activeText&&(!options.isSourceCurrent||options.isSourceCurrent(source));
        }
        function validatePlan(plan,boundary) {
            if(plan.status!=='candidate_found'||plan.verified!==true)throw Error('Unverified CSV candidate');
            if(plan.csv_sha256!==C.csv_sha256)throw Error('Candidate CSV hash mismatch');
            if(plan.provenance?.request_id!==C.request.request_id||plan.provenance?.fresh_computation!==true||
                plan.provenance?.route_cache_hit!==false)throw Error('Candidate fresh request provenance mismatch');
            if(plan.control_ticks!==1||plan.clock_protocol!=='explicit_dt_schedule')
                throw Error('Candidate clock is not the configured native timestamp protocol');
            if(plan.clock?.schedule_count!==C.request_recipe.schedule_count||
                plan.clock?.schedule_sha256!==C.request_recipe.schedule_sha256)throw Error('Candidate full clock identity mismatch');
            const n=plan.actions?.length;
            if(!Array.isArray(plan.actions)||!plan.actions.every(mask=>Number.isInteger(mask)&&mask>=0&&mask<=15)||
                !Array.isArray(plan.confirm_sequence)||plan.confirm_sequence.length!==n||!plan.confirm_sequence.every(value=>typeof value==='boolean')||
                !Array.isArray(plan.trajectory)||plan.trajectory.length!==n+1||!plan.trajectory.every(row=>vector(row,11))||
                !Array.isArray(plan.dt_sequence)||plan.dt_sequence.length!==n+1||!plan.dt_sequence.every(dt=>finite(dt)&&dt>0&&dt<=1/30))
                throw Error('Incomplete CSV action, Confirm, trajectory or dt sequence');
            if(n+1>C.request.dt_schedule.length||plan.dt_sequence.some((dt,i)=>dt!==C.request.dt_schedule[i]))
                throw Error('Candidate dt is not a prefix of the requested clock schedule');
            const expectedSchedule=nativeSchedule(boundary,n+1);
            if(plan.dt_sequence.some((dt,i)=>dt!==expectedSchedule[i]))throw Error('Candidate dt differs from native timestamp schedule');
            if(!boundary.initial.every((value,index)=>value===plan.trajectory[0][index]))throw Error('Candidate initial player mismatch');
            if(boundary.dt!==plan.dt_sequence[0])throw Error('Captured frame0 dt mismatch');
            if(plan.initial_confirm!==boundary.initial_confirm)throw Error('Candidate initial Confirm mismatch');
            if(plan.previous_confirm!==boundary.previous_confirm)throw Error('Candidate previous Confirm mismatch');
            if(!plan.initial_arena||['target','size','speed','callback'].some(key=>
                JSON.stringify(plan.initial_arena[key])!==JSON.stringify(C.source_arena[key])))
                throw Error('Candidate initial arena continuation mismatch');
            const frame0=plan.visualization?.frames?.[0]?.env;
            if(!vector(frame0,22)||[0,1,2,3,4,5,7,8].some(i=>frame0[i]!==boundary.initial_environment[i]))
                throw Error('Candidate frame0 environment differs from the observed original boundary');
            const initialTargets=(plan.target_history||[]).filter(row=>row[0]===0);
            if(JSON.stringify(initialTargets)!==JSON.stringify(C.initial_target_history||[]))
                throw Error('Candidate initial target samples differ from the original Timeline');
            const completion=plan.completion;
            if(plan.termination_policy!==undefined&&plan.termination_policy!==terminationPolicy)
                throw Error('Candidate termination policy differs from the request');
            if(completion!==undefined) {
                if(completion.schema_version!==1||!['endattack','eof_invariant'].includes(completion.kind)||
                    completion.tick!==n||completion.model_verified!==true||completion.native_verified!==false)
                    throw Error('Invalid CSV completion certificate');
                if(completion.kind==='eof_invariant') {
                    const {eof_tick:e,drain_tick:d,release_start_tick:s,release_tick_count:r,certificate:proof}=completion;
                    if(terminationPolicy!=='eof_hazards_drained'||plan.termination_policy!==terminationPolicy||![e,d,s,r].every(Number.isInteger)||
                        e<0||d<e||s!==d+1||r<2||d+r!==n||
                        plan.actions.slice(d).some(mask=>mask!==0)||plan.confirm_sequence.slice(d).some(Boolean))
                        throw Error('Invalid EOF release bridge');
                    if(proof?.status!=='proven'||proof.proof!=='static-empty-release-fixed-point-v1'||
                        proof.policy_mask!==0||proof.policy_confirm!==false||!vector(proof.invariant_state,11)||
                        !vector(proof.static_environment,22)||
                        proof.invariant_state.some((value,k)=>value!==plan.trajectory[n][k]))
                        throw Error('Invalid EOF fixed-point certificate');
                }
            }
            C.completion_kind=completion?.kind||'endattack';
            return n;
        }
        function complete(after) {
            C.nativeEndAttack=true;C.endSnapshot=after;status('completed');release();
            if(options.onComplete)options.onComplete(C);
            else window.cr_setSuspended(true);
        }
        function completeEof(after) {
            if(endEvent||C.completion_kind!=='eof_invariant')throw Error('Unexpected native EndAttack for EOF completion');
            if(typeof options.captureEof!=='function')throw Error('Independent native EOF observation is unavailable');
            const terminal=options.captureEof(),physical=terminal.physical;
            const proof=C.plan.completion.certificate;
            if(physical?.tick!==after.tick||!vector(physical.initial,11)||
                physical.initial.some((value,k)=>value!==proof.invariant_state[k])||
                !vector(physical.initial_environment,22)||physical.initial_environment.some((value,k)=>
                    k!==7&&!(proof.static_environment[9]===0&&(k===10||k===11))&&value!==proof.static_environment[k]))
                throw Error('Native EOF endpoint differs from the model fixed point');
            C.eofTerminal=terminal;C.endSnapshot=after;
            // Recording the endpoint is distinct from the independent proof.
            // No EndAttack, menu transition, reset or runtime correction occurs.
            C.nativeEndAttack=false;status('completed');
            if(options.onComplete)options.onComplete(C);
            else window.cr_setSuspended(true);
        }
        async function solve(boundary) {
            const generation=++requestId,timing=beginTiming(generation);
            // Preserve thrown status/boundary-hook errors while still closing their observation.
            let frozen;
            try {
                C.request_generation=generation;status('solving');frozen=boundaryKey(boundary);
            } catch(error) {finishTiming(timing,'failed',error);throw error;}
            try {
                await options.prepare?.();
                if(!sourceIsCurrent())throw Error('Target CSV changed before solving');
                const hash=await digest(new TextEncoder().encode(activeText));
                if(generation!==requestId){staleTiming(timing,'prepare');return;}
                if(source.sha256!==undefined&&source.sha256!==hash)throw Error('Loaded CSV hash mismatch');
                C.csv_sha256=C.source_sha256=hash;
                const count=Number(query.get('max_ticks')||40000),schedule=nativeSchedule(boundary,count);
                const scheduleHash=await scheduleDigest(schedule);
                if(generation!==requestId){staleTiming(timing,'prepare');return;}
                abort=new AbortController();
                const payload={custom_csv:activeText,initial:boundary.initial,initial_environment:C.source_environment,
                    initial_arena:C.source_arena,initial_target_history:C.initial_target_history,
                    initial_confirm:boundary.initial_confirm,previous_confirm:boundary.previous_confirm,
                    termination_policy:terminationPolicy,
                    fps:clock.physicsHz,dt_schedule:schedule,max_ticks:count,request_id:crypto.randomUUID(),
                    seed:Number(query.get('seed')||42),seconds:Number(query.get('seconds')||30),
                    width:Number(query.get('width')||3000),max_bindings:Number(query.get('max_bindings')||1)};
                timing.record.request_id=payload.request_id;
                // Same identity for the read-only progress channel, so the HUD
                // can show the running search and the plan provenance still
                // agree on which request they describe.
                payload.progress_id=payload.request_id;
                startProgressWatch();
                C.request=payload;C.fresh_computation=true;
                C.request_recipe={generation,max_ticks:count,schedule_count:schedule.length,
                    termination_policy:terminationPolicy,
                    clock_start_ms:boundary.clock_start_ms,initial_dt:boundary.dt,logical_step_ms:clock.logicalStepMs,
                    schedule_sha256:scheduleHash,seed:payload.seed,seconds:payload.seconds,width:payload.width,max_bindings:payload.max_bindings};
                timingPhase(timing,'fetch_json');
                const response=await fetch('/api/solve-csv',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload),signal:abort.signal});
                const plan=await response.json();
                stopProgressWatch();
                if(generation!==requestId){staleTiming(timing,'response');return;}
                timingPhase(timing,'validation');
                C.plan=plan;
                if(!response.ok)throw Error(plan.error||'CSV solve request failed');
                if(!sourceIsCurrent()||(source.sha256!==undefined&&source.sha256!==hash))throw Error('Target CSV changed while solving');
                if(!rt.suspended||boundaryKey(capture())!==frozen)throw Error('Paused original boundary changed while solving');
                options.onPlan?.(C);
                if(!noDamage(capture()))throw Error('Damage was observed before playback');
                if(plan.status==='unknown'&&plan.verified===false) {
                    C.error=plan.reason||plan.status||'unknown';status('unknown');release();window.cr_setSuspended(true);
                    finishTiming(timing,'unknown');return;
                }
                const n=validatePlan(plan,boundary);
                if(C.completion_kind==='eof_invariant'&&plan.completion.drain_tick===0)
                    options.captureEof?.({requireRelease:false});
                if(n===0) {
                    if(!endEvent)throw Error('Empty candidate without native EndAttack');
                    complete(capture());finishTiming(timing,'candidate_ready');return;
                }
                if(endEvent)throw Error('Original attack ended before candidate playback');
                C.actionsApplied=0;status('playing');window.cr_setSuspended(false);
                finishTiming(timing,'candidate_ready');
            } catch(error) {
                if(generation===requestId)stop(error);
                else staleTiming(timing,'error',error);
            }
        }
        function beginSource(nextSource) {
            if(activeText!==null)throw Error('Unexpected TLPlay replaced the active CSV');
            if(!nextSource||typeof nextSource.text!=='string')throw Error('Native source text is required');
            source=nextSource;activeText=source.text;C.wave=source.wave||source.name||'custom.csv';
            C.source_text=activeText;C.source_raw_sha256=source.raw_sha256??null;
            C.source_environment=window.NoHitSolverState.capture(rt).initial_environment.slice();
            C.source_arena=window.NoHitSolverState.captureArena(rt);C.initial_target_history=[];
            pending={tick:rt.tickcount};status('waiting_start');C.events.push({tick:rt.tickcount,fn:'tlplay',sourceMatched:true});
        }
        function observeFunction(fn,inst) {
            if(activeText===null)return;
            if(pending&&fn==='getheartpos') {
                const heart=rt.types_by_index.find(t=>t.sid===5960708907117077)?.instances[0];
                C.initial_target_history.push([0,rt.varsBySid[2569112556112449]?.data,heart.x,heart.y]);
            }
            if(fn==='damageplayer') {
                const amount=Number(parameter(inst)),kr=Number(parameter(inst,1));
                if(amount>0||kr>0)C.firstDamage ||= {tick:rt.tickcount,source:'DamagePlayer',amount,kr};
            }
            if(['endattack','tlpause','tlresume','damageplayer','resetvars','tlstop'].includes(fn)) {
                const event={tick:rt.tickcount,fn};C.events.push(event);
                if(fn==='endattack')endEvent=event;
            }
        }
        function beforeTick() {
            if(!C.canAdvance())return null;
            try {
                if(C.status==='playing') {
                    const before=capture(),index=C.actionsApplied;
                    if(before.tick!==C.boundary.tick+index)throw Error('Native tick discontinuity before input');
                    if(index>=C.plan.actions.length)throw Error('Candidate exhausted before its completion boundary');
                    if(!noDamage(before))throw Error('Native damage before input');
                    const mask=C.plan.actions[index],confirm=C.plan.confirm_sequence[index];input(mask,confirm);
                    return {before,index,mask,confirm};
                }
                if(pending)input(0,false);
                return {index:-1};
            } catch(error) {stop(error);return null;}
        }
        function afterTick(token=null) {
            if(C.status==='failed'||C.status==='cancelled')return;
            try {
                if(token&&token.index>=0) {
                    const {before,index,mask,confirm}=token,after=capture();record(after,mask,confirm);C.actionsApplied=index+1;
                    if(after.tick!==before.tick+1)throw Error('Native tick was skipped or repeated');
                    if(after.dt!==C.plan.dt_sequence[index+1])throw Error('Native dt differs from candidate');
                    if(after.initial[4]!==mask||after.initial_confirm!==confirm)throw Error('Native sampled input differs from candidate');
                    if(!noDamage(after))throw Error('Native HP/KR or DamagePlayer failed');
                    if(endEvent) {
                        if(C.completion_kind==='eof_invariant')throw Error('Unexpected native EndAttack for EOF completion');
                        if(C.actionsApplied!==C.plan.actions.length)throw Error('Native EndAttack occurred before the expected final input');
                        complete(after);
                    } else {
                        const expected=C.plan.trajectory[index+1];
                        if(after.initial.some((value,k)=>C.completion_kind==='eof_invariant'?
                            value!==expected[k]:Math.abs(value-expected[k])>1e-7))throw Error('Native player differs from candidate');
                        if(C.actionsApplied===C.plan.actions.length) {
                            if(C.completion_kind==='eof_invariant')completeEof(after);
                            else throw Error('Candidate ended without native EndAttack');
                        }
                    }
                } else if(pending) {
                    const line=rt.varsBySid[2569112556112449]?.data,time=rt.varsBySid[3521916820909801]?.data;
                    if(!Number.isInteger(line)||!finite(time))throw Error('Original Timeline observation is incomplete');
                    if(line!==1||time>0||endEvent) {
                        const boundary=capture();pending=null;C.boundary=boundary;record(boundary);
                        window.cr_setSuspended(true);release();options.validateBoundary?.(boundary);
                        if(!noDamage(boundary))throw Error('Original CSV entry is already damaged');
                        nativeSchedule(boundary,1);C.solvePromise=solve(boundary);
                    }
                }
            } catch(error) {stop(error);}
        }
        C.canAdvance=()=>!blocked.has(C.status);
        C.cancel=()=>stop('cancelled_by_user','cancelled');
        C.retry=(settings={})=>{
            if(!rt.suspended||!C.boundary||C.status!=='unknown'||boundaryKey(capture())!==boundaryKey(C.boundary))
                throw Error('Retry requires the unchanged paused CSV boundary');
            const allowed=new Set(['width','seconds','max_bindings','max_ticks']);
            if(!settings||typeof settings!=='object'||Array.isArray(settings)||
                Object.entries(settings).some(([key,value])=>!allowed.has(key)||!finite(value)||value<=0||
                    (key!=='seconds'&&!Number.isInteger(value))))throw Error('Invalid retry search settings');
            for(const [key,value] of Object.entries(settings))query.set(key,String(value));
            C.error=null;return C.solvePromise=solve(C.boundary);
        };
        return {state:C,beginSource,observeFunction,beforeTick,afterTick,input,release,fail:stop,
            canAdvance:C.canAdvance,retry:C.retry,cancel:C.cancel,hasSource:()=>activeText!==null};
    }
    window.NoHitCsvRoundController={create};
})();

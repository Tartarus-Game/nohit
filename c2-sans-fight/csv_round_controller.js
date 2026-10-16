// One source-model witness continues an observed native round. This module
// installs no runtime hooks; Custom and Normal own their respective wrappers.
(() => {
    const ownedKeys=[37,38,39,40,65,68,83,87,88,16,90,13];
    const blocked=new Set(['solving','unknown','failed','completed','cancelled']);
    const sharedProgressRequests=new Map();
    const finite=value=>typeof value==='number'&&Number.isFinite(value);
    const vector=(value,size)=>Array.isArray(value)&&value.length===size&&value.every(finite);
    function hudElements() {
        if(typeof document==='undefined'||typeof document.getElementById!=='function'||typeof document.createElement!=='function')return null;
        const badge=document.getElementById('tas-status-badge');
        const hud=document.getElementById('tas-controller-overlay')||badge?.parentNode;
        if(!badge||!hud)return null;
        let panel=document.getElementById('csv-hud-details'),summary=document.getElementById('csv-hud-summary'),body=document.getElementById('csv-hud-body');
        if(!panel) {
            panel=document.createElement('details');summary=document.createElement('summary');body=document.createElement('div');
            if(typeof panel.appendChild!=='function'||typeof hud.appendChild!=='function')return null;
            panel.id='csv-hud-details';summary.id='csv-hud-summary';body.id='csv-hud-body';
            panel.appendChild(summary);panel.appendChild(body);hud.appendChild(panel);
            Object.assign(summary.style,{cursor:'pointer',whiteSpace:'nowrap',overflow:'hidden',textOverflow:'ellipsis'});
            Object.assign(body.style,{maxHeight:'min(36vh, 280px)',overflowY:'auto',marginTop:'6px',overflowWrap:'anywhere'});
            if(typeof MutationObserver==='function') {
                const observer=new MutationObserver(()=>{
                    for(const item of Array.from(hud.children))if(item!==panel)body.appendChild(item);
                });
                observer.observe(hud,{childList:true});
            }
        }
        for(const item of Array.from(hud.children||[]))if(item!==panel)body.appendChild(item);
        for(const id of ['tas-status-badge','tas-clock-status','csv-solve-progress','csv-progress-dashboard-link','csv-source-warnings','csv-budget-status','csv-edit-link']) {
            const item=document.getElementById(id);if(item&&item.parentNode!==body)body.appendChild(item);
        }
        if(hud.style&&typeof hud.style==='object')Object.assign(hud.style,{top:'8px',left:'auto',right:'8px',transform:'none',
            maxWidth:'min(420px, calc(100vw - 24px))',padding:'4px 8px',fontSize:'12px',lineHeight:'1.4',
            border:'1px solid rgba(255,255,255,.45)',background:'rgba(0,0,0,.78)'});
        return {panel,summary,body};
    }
    function etaText(snap) {
        const known=['csv_literal_duration_estimate','scalar_replay_tick_rate'].includes(snap?.eta_basis);
        if(!known||!finite(snap?.eta_seconds)||snap.eta_seconds<0)return '估算中';
        const seconds=Math.ceil(snap.eta_seconds),duration=seconds>=60?`${Math.floor(seconds/60)}分${seconds%60}秒`:`${seconds}秒`;
        return '预计剩余约 '+duration;
    }
    function describeResult(plan,budgetMode=plan.budget_selection?.mode) {
        if(plan.reason==='unsupported_mechanism') {
            const issues=Array.isArray(plan.issues)?plan.issues:[];
            const details=issues.map(issue=>{
                const line=Number.isInteger(issue?.line)&&issue.line>0?`第 ${issue.line} 行`:'脚本';
                const command=typeof issue?.command==='string'?`「${issue.command}」`:'';
                const reason=issue?.reason==='missing_endattack'?'缺少结束攻击指令':'当前求解器尚未验证此指令的原版行为';
                return `${line}${command}：${reason}`;
            });
            return {retryable:false,title:'CSV 机制尚未支持',detail:[...details,
                '增加搜索时间或加宽搜索都无法解决指令支持问题。请修改 CSV 后重新导入；当前结果不能证明无解。'].join('\n')};
        }
        const reason={wall_budget:'已达到本次搜索时间上限。',frontier_exhausted:'当前搜索保留的状态已耗尽。'}[plan.reason]
            ||'当前有限搜索尚未得到完整路线。';
        return {retryable:true,title:'有限搜索暂未找到完整候选',detail:reason+
            (budgetMode==='auto'?'自动尝试后仍未找到完整路线，可重试/查看详情；当前结果不能证明无解。':'可调整起点或搜索预算后重试；当前结果不能证明无解。')};
    }
    function showDiagnostic(badge,diagnostic) {
        const existing=typeof document!=='undefined'?document.getElementById('csv-edit-link'):null;
        if(existing) {
            existing.hidden=!diagnostic||diagnostic.retryable!==false;
            if(existing.style)existing.style.display=existing.hidden?'none':'block';
        }
        if(!badge||!diagnostic)return false;
        badge.textContent=diagnostic.title+'\n'+diagnostic.detail;
        if(badge.style)badge.style.whiteSpace='pre-line';
        if(diagnostic.retryable===false&&badge.parentNode&&typeof document.createElement==='function') {
            const link=existing||document.createElement('a');
            link.id='csv-edit-link';link.href='/#solve-form';link.textContent='返回 CSV 页面修改文件';link.hidden=false;
            if(link.style) {link.style.display='block';link.style.color='#8be0b7';link.style.marginTop='8px';}
            if(!existing)badge.parentNode.appendChild(link);
        }
        return true;
    }
    function showWarnings(warnings) {
        if(typeof document==='undefined'||typeof document.getElementById!=='function')return;
        const items=Array.isArray(warnings)?warnings:[];
        let line=document.getElementById('csv-source-warnings');
        if(!items.length) {
            if(line) {line.textContent='';line.hidden=true;if(line.style)line.style.display='none';}
            return;
        }
        if(!line) {
            const badge=document.getElementById('tas-status-badge');
            if(!badge?.parentNode||typeof document.createElement!=='function')return;
            line=document.createElement('div');line.id='csv-source-warnings';badge.parentNode.appendChild(line);
        }
        const details=items.map(item=>{
            const location=Number.isInteger(item?.line)&&item.line>0?`第 ${item.line} 行`:'脚本';
            const command=typeof item?.command==='string'?`「${item.command}」`:'';
            const reason={native_function_has_no_handler:'原游戏没有对应处理函数，执行时不产生效果',
                scripted_damage_disabled:'CSV 直接伤害/回血指令无法按无伤脚本处理，已禁用（保留延时）'}[item?.reason]||'请核对这条指令';
            return `${location}${command}：${reason}`;
        });
        line.textContent='CSV 警告（仍可继续处理）\n'+details.join('\n');line.hidden=false;
        if(line.style)Object.assign(line.style,{display:'block',color:'#ffd58b',fontSize:'12px',marginTop:'6px',whiteSpace:'pre-line',overflowWrap:'anywhere'});
    }
    function mergeWarnings(original,incoming) {
        if(!Array.isArray(incoming)||!incoming.length)return original;
        if(!original.length)return incoming;
        const key=item=>JSON.stringify([item?.line,item?.command,item?.reason]);
        const seen=new Set(original.map(key));
        const additions=incoming.filter(item=>{const value=key(item);if(seen.has(value))return false;seen.add(value);return true;});
        return additions.length?[...original,...additions]:original;
    }
    function showBudget(mode,selection) {
        if(typeof document==='undefined'||typeof document.getElementById!=='function')return;
        let line=document.getElementById('csv-budget-status');
        if(!mode) {if(line) {line.hidden=true;if(line.style)line.style.display='none';}return;}
        if(!line) {
            const badge=document.getElementById('tas-status-badge');
            if(!badge?.parentNode||typeof document.createElement!=='function')return;
            line=document.createElement('div');line.id='csv-budget-status';badge.parentNode.appendChild(line);
        }
        const profile={short:'短谱',medium:'中等长度',long:'长谱'}[selection?.profile];
        line.textContent=(mode==='auto'?'自动预算':'手动预算')+(profile?' · '+profile:'');line.hidden=false;
        if(line.style)Object.assign(line.style,{display:'block',color:'#a1acbc',fontSize:'12px',marginTop:'4px'});
    }
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
        const budgetMode=()=>query.get('budget_mode')||((query.has('width')||query.has('seconds'))?'manual':'auto');
        const terminationPolicy=options.terminationPolicy||'endattack';
        if(!['endattack','eof_hazards_drained'].includes(terminationPolicy))throw Error('Invalid CSV termination policy');
        const C=options.state||{};
        Object.assign(C,{version:1,status:'waiting_source',error:null,plan:null,issues:[],warnings:[],diagnostic:null,boundary:null,
            budget_mode:budgetMode(),budget_selection:null,
            actionsApplied:0,rows:[],events:[],firstDamage:null,nativeEndAttack:false,endSnapshot:null,
            original_replay_passed:false,complete_in_original_game:false,safe_forever_under_release:false,
            termination_policy:terminationPolicy,completion_kind:null,eofTerminal:null});
        let requestId=0,pending=null,source=null,activeText=null,endEvent=null,abort=null,activeTiming=null;
        // Live solve telemetry lives here, in the controller both the Custom shell
        // and the Normal campaign share, so every entry shows the same numbers.
        // Hosts without timers (the Node controller harnesses) simply never poll.
        let progressTimer=null,progressWatch=null,progressAttempt=null,hudStatus=null;
        function renderHud() {
            const elements=hudElements();if(!elements)return;
            const {panel,summary}=elements;
            if(hudStatus!==C.status){panel.open=!['playing','completed'].includes(C.status);hudStatus=C.status;}
            const label={waiting_source:'等待 CSV',waiting_start:'准备起点',solving:'解算中',playing:'执行中',completed:'已完成',
                unknown:'未找到完整路线',failed:'已停止',cancelled:'已取消'}[C.status]||C.status;
            const attempt=C.solve_timing?.attempts.at(-1);
            const elapsed=attempt?(attempt.total_ms??timingNow()-attempt.started_at_ms)/1000:null;
            summary.textContent=label+(elapsed!==null?` · 解算 ${elapsed.toFixed(1)}s`:'')+
                (C.status==='solving'?' · '+etaText(C.solve_progress):'')+' · '+(panel.open?'收起':'详情');
            panel.ontoggle=()=>{try{renderHud();}catch(error){/* HUD only */}};
        }
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
        function progressText(watch){
            const snap=watch.snapshot||{},state=watch.outcome||snap.state||'running';
            const count=value=>Number.isInteger(value)?value.toLocaleString('en-US'):'—';
            const phases={prepare:'准备',compile:'编译',bake:'烘焙 C-space',search:'搜索前沿',
                dialogue:'对话',completion:'终点证书',verify:'逐帧复核',visualization:'逐帧几何'};
            const elapsed=Math.max(finite(snap.elapsed_seconds)?snap.elapsed_seconds:0,
                ((watch.finishedAt??timingNow())-watch.startedAt)/1000);
            const label={done:'解算已结束',failed:'解算失败',cancelled:'解算已取消'}[state]||'解算中';
            const phase=phases[snap.phase]||snap.phase||'等待服务端阶段信息';
            const noCounters=![snap.tick,snap.alive_states,snap.expanded_states].some(Number.isInteger);
            const unchanged=watch.active&&state==='running'&&timingNow()-watch.changedAt>=2000;
            return `${label} · ${phase} · 已用 ${elapsed.toFixed(1)}s`
                +` · 前沿 ${count(snap.alive_states)} · 展开 ${count(snap.expanded_states)}`
                +` · ${finite(snap.states_per_second)?Math.round(snap.states_per_second).toLocaleString('en-US'):'—'} 态/秒`
                +` · tick ${Number.isInteger(snap.tick)?snap.tick:'—'}/${Number.isInteger(snap.ticks)?snap.ticks:'—'}`
                +(state==='running'?' · '+etaText(snap):'')
                +(noCounters?' · 阶段计数尚未上报':'')
                +(unchanged?' · 阶段处理中，等待计数更新':'')+(snap.message?' · '+snap.message:'');
        }
        function renderProgress(watch) {
            try {
                const line=progressLine();if(!line)return;
                line.hidden=false;line.textContent=progressText(watch);
                let link=document.getElementById('csv-progress-dashboard-link');
                if(!link&&line.parentNode) {
                    link=document.createElement('a');link.id='csv-progress-dashboard-link';
                    link.textContent='在 Dashboard 查看本次解算';link.target='_blank';link.rel='noopener';
                    if(link.style)Object.assign(link.style,{display:'block',fontSize:'12px',color:'#8be0b7',marginTop:'4px'});
                    line.parentNode.appendChild(link);
                }
                if(link){link.hidden=false;link.href='/?progress_id='+encodeURIComponent(watch.id);}
                renderHud();
            } catch(error) { /* HUD only */ }
        }
        function stopProgressWatch(outcome=null){
            if(progressTimer!==null&&typeof clearInterval==='function'){clearInterval(progressTimer);progressTimer=null;}
            if(!progressWatch)return;
            const watch=progressWatch;watch.active=false;watch.finishedAt=timingNow();
            if(outcome)watch.outcome=outcome;
            renderProgress(watch);progressWatch=null;
        }
        function startProgressWatch(timing){
            stopProgressWatch();
            const watch=progressWatch={id:C.request.progress_id,generation:requestId,active:true,polling:false,
                startedAt:timing.record.started_at_ms,changedAt:timingNow(),snapshot:null,fingerprint:null};
            C.solve_progress=null;renderProgress(watch);
            if(typeof setInterval!=='function')return;
            progressTimer=setInterval(async () => {
                if(progressWatch!==watch||!watch.active)return;
                renderProgress(watch);
                if(watch.polling)return;
                watch.polling=true;
                try {
                    const reply=await fetch('/api/progress/'+encodeURIComponent(watch.id));
                    if(!reply.ok)return;
                    const snap=await reply.json();
                    if(progressWatch!==watch||!watch.active||requestId!==watch.generation||
                        (snap.progress_id!==undefined&&snap.progress_id!==watch.id))return;
                    const fingerprint=JSON.stringify([snap.state,snap.phase,snap.tick,snap.ticks,snap.alive_states,
                        snap.expanded_states,snap.fraction,snap.fraction_basis,snap.message]);
                    if(fingerprint!==watch.fingerprint){watch.fingerprint=fingerprint;watch.changedAt=timingNow();}
                    C.solve_progress=watch.snapshot=snap;renderProgress(watch);
                    if(snap.state==='done'||snap.state==='failed')stopProgressWatch();
                } catch(error) { /* observation only; the solve owns the outcome */ }
                finally {watch.polling=false;}
            },250);
        }
        function nextRequestIdentity() {
            const shared=query.get('progress_id');
            if(query.has('progress_id')&&(!shared||shared.length>128))throw Error('Invalid shared progress_id');
            const previous=(shared&&sharedProgressRequests.get(shared))||C.request?.progress_id||null;
            const id=shared&&!sharedProgressRequests.has(shared)?shared:crypto.randomUUID();
            if(shared)sharedProgressRequests.set(shared,id);
            C.previous_progress_id=previous;return id;
        }
        function publish(message) {
            try {
                const origin=window.location?.origin;
                if(origin&&window.opener&&!window.opener.closed)window.opener.postMessage(message,origin);
            } catch(error) { /* An optional dashboard never owns game control. */ }
        }
        function publishStatus() {
            if(!progressAttempt||progressAttempt.generation!==C.request_generation)return;
            publish({type:'nohit:csv-status',progress_id:progressAttempt.id,previous_progress_id:progressAttempt.previous,
                status:C.status,error:C.error});
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
            try{renderHud();}catch(error){/* HUD only */}
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
        function status(value) {
            C.status=value;options.onStatus?.(value,C);
            publishStatus();
            try {showWarnings(C.warnings);}catch(error) { /* Warning display never owns native execution. */ }
            try {showBudget(C.budget_mode,C.budget_selection);}catch(error) { /* HUD only. */ }
            try {renderHud();}catch(error) { /* HUD only. */ }
        }
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
                stopProgressWatch(state==='cancelled'?'cancelled':'failed');
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
            let frozen,identity;
            try {
                C.request_generation=generation;C.issues=[];C.diagnostic=null;
                identity=nextRequestIdentity();
                progressAttempt={generation,id:identity,previous:C.previous_progress_id};
                C.budget_mode=budgetMode();C.budget_selection=null;status('solving');frozen=boundaryKey(boundary);
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
                const observationSettings={};
                for(const key of ['observation_chunk_ticks','observation_preview_ticks','observation_preview_reads','workers'])
                    if(query.has(key))observationSettings[key]=Number(query.get(key));
                if(query.has('observation_goal_retries')) {
                    const flag=query.get('observation_goal_retries');
                    observationSettings.observation_goal_retries=flag==='1'?true:flag==='0'?false:flag;
                }
                const budgetSettings={budget_mode:C.budget_mode,...(C.budget_mode==='manual'?{
                    seconds:Number(query.get('seconds')||30),width:Number(query.get('width')||3000)}:{})};
                const payload={custom_csv:activeText,initial:boundary.initial,initial_environment:C.source_environment,
                    initial_arena:C.source_arena,initial_target_history:C.initial_target_history,
                    initial_confirm:boundary.initial_confirm,previous_confirm:boundary.previous_confirm,
                    termination_policy:terminationPolicy,visualization_mode:'entry',
                    fps:clock.physicsHz,dt_schedule:schedule,max_ticks:count,request_id:identity,
                    seed:Number(query.get('seed')||42),...budgetSettings,...observationSettings};
                timing.record.request_id=payload.request_id;
                // Same identity for the read-only progress channel, so the HUD
                // can show the running search and the plan provenance still
                // agree on which request they describe.
                payload.progress_id=payload.request_id;
                C.request=payload;C.fresh_computation=true;
                C.request_recipe={generation,max_ticks:count,schedule_count:schedule.length,
                    request_id:payload.request_id,progress_id:payload.progress_id,
                    termination_policy:terminationPolicy,visualization_mode:'entry',
                    clock_start_ms:boundary.clock_start_ms,initial_dt:boundary.dt,logical_step_ms:clock.logicalStepMs,
                    schedule_sha256:scheduleHash,seed:payload.seed,...budgetSettings,...observationSettings};
                startProgressWatch(timing);
                timingPhase(timing,'fetch_json');
                const response=await fetch('/api/solve-csv',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload),signal:abort.signal});
                const plan=await response.json();
                if(generation!==requestId){staleTiming(timing,'response');return;}
                stopProgressWatch('done');
                timingPhase(timing,'validation');
                C.plan=plan;
                C.issues=Array.isArray(plan.issues)?plan.issues:[];
                C.warnings=mergeWarnings(C.warnings,plan.warnings);
                C.budget_selection=plan.budget_selection||null;
                if(!response.ok)throw Error(plan.error||'CSV solve request failed');
                if(!sourceIsCurrent()||(source.sha256!==undefined&&source.sha256!==hash))throw Error('Target CSV changed while solving');
                if(!rt.suspended||boundaryKey(capture())!==frozen)throw Error('Paused original boundary changed while solving');
                options.onPlan?.(C);
                if(!noDamage(capture()))throw Error('Damage was observed before playback');
                if(plan.status==='unknown'&&plan.verified===false) {
                    C.diagnostic=describeResult(plan,C.budget_mode);
                    publish({type:'nohit:csv-result',progress_id:payload.progress_id,result:{...plan,warnings:C.warnings}});
                    C.error=plan.reason||plan.status||'unknown';status('unknown');release();window.cr_setSuspended(true);
                    finishTiming(timing,'unknown');return;
                }
                const n=validatePlan(plan,boundary);
                publish({type:'nohit:csv-result',progress_id:payload.progress_id,result:{...plan,warnings:C.warnings}});
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
            C.warnings=Array.isArray(source.preflight?.warnings)?source.preflight.warnings:
                Array.isArray(source.warnings)?source.warnings:[];
            C.source_text=activeText;C.source_raw_sha256=source.raw_sha256??null;
            C.source_import_id=source.import_id??null;C.source_preparation=source.preparation??null;
            C.source_original_raw_sha256=source.preparation?.original_raw_sha256??null;
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
            if(C.diagnostic?.retryable===false)throw Error('当前 CSV 机制尚未支持，请先修改 CSV 后重新导入。');
            const allowed=new Set(['width','seconds','max_ticks']);
            if(!settings||typeof settings!=='object'||Array.isArray(settings)||
                Object.entries(settings).some(([key,value])=>!allowed.has(key)||!finite(value)||value<=0||
                    (key!=='seconds'&&!Number.isInteger(value))))throw Error('Invalid retry search settings');
            for(const [key,value] of Object.entries(settings))query.set(key,String(value));
            if('width' in settings||'seconds' in settings)query.set('budget_mode','manual');
            C.error=null;return C.solvePromise=solve(C.boundary);
        };
        // A new Normal round can wait for TLPlay after RunAttack. Its empty
        // warning set must replace the previous round's HUD during that wait.
        try {showWarnings(C.warnings);}catch(error) { /* HUD only. */ }
        try {showBudget(C.budget_mode,C.budget_selection);}catch(error) { /* HUD only. */ }
        try {renderHud();}catch(error) { /* HUD only. */ }
        return {state:C,beginSource,observeFunction,beforeTick,afterTick,input,release,fail:stop,
            canAdvance:C.canAdvance,retry:C.retry,cancel:C.cancel,hasSource:()=>activeText!==null};
    }
    window.NoHitCsvRoundController={create,describeResult,showDiagnostic};
})();

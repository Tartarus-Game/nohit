// Development oracle: every transition executes the shipped C2 runtime.
// Accelerated branching is candidate generation, not real-time acceptance.
(function installOracle() {
    if (!new URLSearchParams(location.search).has('oracle')) return;
    if (!window.cr?.runtime) {
        window.addEventListener('nohit-runtime-ready', installOracle, {once:true});
        return;
    }
    const O = window.EngineOracle = { ready: false, ended: false, busy: false, steps: 0 };
    O.captureDynamics = new URLSearchParams(location.search).has('diagnostics');
    O.events = [];
    const proto = cr.runtime.prototype, gameTick = proto.tick, trigger = proto.trigger;
    let rt, pending = false;
    const sid = { heart: 5960708907117077, hitbox: 728293317807613,
        platform: 1226268899238104, beam: 165116925986465 };
    function instances(id) { return rt.types_by_index.find(t => t.sid === id)?.instances || []; }
    O.observe = () => {
        const vars = Object.fromEntries(rt.all_global_vars.map(v => [v.name, v.data]));
        const h = instances(sid.heart)[0], cm = h?.behavior_insts.find(b => b.type.name === 'CustomMovement');
        const observation = { HP: vars.HP, KR: vars.KR, tick: rt.tickcount, time: rt.kahanTime.sum,
            clock_start_ms:rt.last_tick_time,
            T: rt.varsBySid[3521916820909801]?.data, running: rt.varsBySid[164016619418963]?.data,
            x: h?.x, y: h?.y, angle: h?.angle, mode: h?.instance_vars[0], dx: cm?.dx, dy: cm?.dy,
            ended: O.ended, platforms: instances(sid.platform).map(p => ({ x:p.x,y:p.y,w:p.width })),
            beams: instances(sid.beam).map(b => ({x:b.x,y:b.y,w:b.width,h:b.height,angle:b.angle})) };
        if(O.captureDynamics){
            const describe=b=>{b.update_bbox();const q=b.bquad,cm=b.behavior_insts.find(k=>k.type.name==='CustomMovement');return{
                uid:b.uid,x:b.x,y:b.y,w:b.width,h:b.height,angle:b.angle,vars:b.instance_vars.slice(),
                bbox:{...b.bbox},quad:[q.Fa,q.Ga,q.nb,q.ob,q.bb,q.cb,q.$a,q.ab],dx:cm?.dx,dy:cm?.dy};};
            const keys=window.TASRunner.getKeyboardInstance().keyMap;
            observation.dt=rt.dt;
            observation.keymask=(keys[37]?1:0)|(keys[39]?2:0)|(keys[38]?4:0)|(keys[40]?8:0)|(keys[88]||keys[16]?16:0);
            observation.heartVars=h?.instance_vars.slice();
            observation.maxFall=rt.varsBySid[963626393445968]?.data;
            observation.arena=instances(141231765387603).map(describe);
            observation.platforms=instances(sid.platform).map(describe);
            observation.blasters=instances(7974524067202295).map(describe);
            observation.beamSprites=instances(9836012384209519).map(describe);
            observation.beamHits=instances(sid.beam).map(describe);
            observation.hazards=[];
            for(const familySid of [9590353435551898,6631597198329078,9784977049754561]){
                const family=rt.types_by_index.find(t=>t.sid===familySid);if(!family)continue;
                for(const member of family.members)for(const b of member.instances){
                    const offset=member.family_var_map[family.family_index];
                    if(b.instance_vars[offset]>0)observation.hazards.push({...describe(b),typeSid:member.sid,
                        damage:b.instance_vars[offset],color:familySid===9590353435551898?b.instance_vars[offset+2]:0});
                }
            }
        }
        return observation;
    };
    O.checkpoint = () => ({ json: rt.saveToJSONString(), rng: window.__TAS_SEED?.checkpoint(),
        ended: O.ended, keys: {...window.TASRunner.getKeyboardInstance().keyMap},
        clock: { last_tick_time:rt.last_tick_time,dt:rt.dt,dt1:rt.dt1,
            kahanTime:{...rt.kahanTime},wallTime:{...rt.wallTime} } });
    O.restore = saved => {
        if (!rt.loadFromJSONString(saved.json)) throw Error('Original engine rejected checkpoint');
        if (saved.rng) window.__TAS_SEED.restore(saved.rng);
        window.TASRunner.releaseAllKeys();
        Object.assign(window.TASRunner.getKeyboardInstance().keyMap, saved.keys);
        if(saved.clock) {
            Object.assign(rt.kahanTime,saved.clock.kahanTime);
            Object.assign(rt.wallTime,saved.clock.wallTime);
            rt.last_tick_time=saved.clock.last_tick_time; rt.dt=saved.clock.dt;rt.dt1=saved.clock.dt1;
        }
        O.ended = saved.ended;
    };
    O.step = (action, frames=1, guardPx=0) => {
        if (!O.ready) throw Error('Attack initial state is not ready');
        O.busy = true;
        const before = O.observe(); let hit = false, clearanceViolation=false, rows = [];
        try {
            for (let f=0;f<frames&&!O.ended;f++) {
                if(typeof action==='number')window.TASRunner.injectMask(action);
                else window.TASRunner.injectKeys(action[0],action[1]);
                for(let micro=0;micro<4&&!O.ended;micro++) {
                    gameTick.call(rt,true,rt.last_tick_time+1000/240,true);
                    O.steps++;
                    const obs=O.observe();
                    if(obs.HP<before.HP||obs.KR>before.KR) hit=true;
                    rows.push(obs);
                    if(guardPx>0&&!O.ended&&!O.hasClearance(guardPx)){clearanceViolation=true;break;}
                }
                if(hit||clearanceViolation) break;
            }
        } finally { O.busy = false; }
        return { hit, clearanceViolation, rows, end:O.observe() };
    };
    O.draw = () => { if(rt.glwrap)rt.drawGL();else rt.draw(); };
    O.replay = async (actions=[], maxFrames=18000) => {
        if(O.replaying||O.searching)throw Error('Original engine is busy');
        O.replaying=true;O.cancelRequested=false;
        try {
        O.restore(O.initial); O.events=[];
        const rows=[O.observe()], micro_rows=[];
        let totalHits=0;
        let frame=0;
        for(;frame<maxFrames&&!O.ended&&rows[rows.length-1].HP>0&&!O.cancelRequested;frame++) {
            const run=O.step(actions[frame]||[0,0],1);
            rows.push(run.end);
            micro_rows.push(...run.rows);
            if(run.hit) totalHits++;
            if(frame%120===0) await new Promise(resolve=>setTimeout(resolve,0));
        }
        const end=O.observe();O.draw();
        return O.lastReplay={wave:new URLSearchParams(location.search).get('attack')+'.csv',
            seed:window.__TAS_SEED?.seed,clock:'original-runtime-fixed-240hz',
            status:O.cancelRequested?'cancelled':O.ended?'end_attack':end.HP<=0?'game_over':'horizon_limit',
            no_hit:O.ended&&totalHits===0&&rows[0].HP===92&&rows[0].KR===0&&micro_rows.every(r=>r.HP===92&&r.KR===0),
            total_hits:totalHits,total_microticks:micro_rows.length,micro_rows,
            realtime_accepted:false,frames:frame,rows,random:window.__TAS_SEED?.checkpoint()};
        } finally {O.replaying=false;}
    };
    function activeHazards() {
        const hb=instances(sid.hitbox)[0], h=instances(sid.heart)[0];
        if(!hb||!h) return [];
        const hazards=[];
        for(const fsid of [9590353435551898,6631597198329078,9784977049754561]) {
            const family=rt.types_by_index.find(t=>t.sid===fsid);
            if(!family) continue;
            for(const type of family.members) for(const inst of type.instances) {
                const offset=type.family_var_map[family.family_index];
                if(inst.instance_vars[offset]<=0) continue;
                const color=fsid===9590353435551898?inst.instance_vars[offset+2]:0;
                const cm=h.behavior_insts.find(b=>b.type.name==='CustomMovement');
                if(color===1&&Math.abs(cm?.dx||0)<1e-8&&Math.abs(cm?.dy||0)<1e-8) continue;
                hazards.push(inst);
            }
        }
        return hazards;
    }
    O.hasClearance = radius => {
        if(!O.ready)return false;
        const hb=instances(sid.hitbox)[0];if(!hb)return false;
        const w=hb.width,h=hb.height;
        // Query the original collider with a dilated hitbox. Offset samples
        // could miss a thin rotated beam between probe points.
        try {
            hb.width=w+2*radius;hb.height=h+2*radius;hb.set_bbox_changed();
            return !activeHazards().some(b=>rt.testOverlap(hb,b));
        } finally {hb.width=w;hb.height=h;hb.set_bbox_changed();}
    };
    O.clearance = () => {
        let margin=8;
        for(const r of [1,2,4,8])if(!O.hasClearance(r)){margin=r===1?0:r===2?1:r===4?2:4;break;}
        return margin;
    };
    O.solveRolling = async ({beam=6,depth=6,segment=8,maxFrames=3600,marginPx=1,budgetMs=60000}={}) => {
        const started=performance.now();
        O.restore(O.initial);
        const rootHP=O.observe().HP;
        const actions=[], trajectory=[O.observe()], decisions=[];
        let backtracks=0;
        const alphabet=[[0,0],[-1,0],[1,0],[0,1],[-1,1],[1,1],[0,-1],[-1,-1],[1,-1]];
        const result=O.result={status:'searching',frame:0,actions,trajectory,
            authoritative_runtime:true,realtime_accepted:false,search_limited:true,marginPx,beam,depth,segment};
        for(let frame=0;frame<maxFrames&&!O.ended;frame+=segment) {
            if(O.cancelRequested||performance.now()-started>budgetMs){result.status=O.cancelRequested?'cancelled':'budget_limit';break;}
            let root=O.checkpoint();
            let frontier=[{state:root,cost:0,path:[],last:actions[actions.length-1]||[0,0]}];
            for(let d=0;d<depth;d++) {
                let children=[];
                for(const node of frontier) for(const action of alphabet) {
                    O.restore(node.state);
                    const run=O.step(action,segment,marginPx);
                    if(run.hit||run.clearanceViolation||run.end.HP!==rootHP||run.end.KR!==0) continue;
                    const margin=O.clearance();
                    if(margin<marginPx) continue;
                    const input=action[0]||action[1]?segment:0;
                    const change=Math.abs(action[0]-node.last[0])+Math.abs(action[1]-node.last[1]);
                    const cost=node.cost+input*.04+change*.1+(8-margin)*.2;
                    children.push({state:O.checkpoint(),cost,path:node.path.concat([action]),last:action,
                        x:run.end.x,y:run.end.y,dy:run.end.dy,ended:run.end.ended});
                }
                children.sort((a,b)=>a.cost-b.cost);
                const bands=new Set();frontier=[];
                for(const child of children) {
                    const band=[Math.floor(child.x/12),Math.floor(child.y/12),Math.floor(child.dy/30),child.last.join(','),child.path[0].join(',')].join(':');
                    if(bands.has(band)) continue;
                    bands.add(band);frontier.push(child);
                    if(frontier.length>=beam) break;
                }
                if(!frontier.length||frontier.every(n=>n.ended)) break;
            }
            O.restore(root);
            let choice;
            if(!frontier.length) {
                let retry;
                while(decisions.length) {
                    const previous=decisions.pop();
                    if(previous.next<previous.choices.length){retry=previous;break;}
                }
                if(!retry||backtracks++>=200) {result.status='no_candidate';result.frame=frame;break;}
                O.restore(retry.root);root=retry.root;frame=retry.length;
                actions.length=retry.length;trajectory.length=retry.length+1;
                choice=retry.choices[retry.next++];decisions.push(retry);
            } else {
                const choices=[], seen=new Set();
                for(const node of frontier) {
                    const action=node.path[0], key=action.join(',');
                    if(!seen.has(key)){seen.add(key);choices.push(action);}
                }
                choice=choices[0];decisions.push({root,length:actions.length,choices,next:1});
            }
            const run=O.step(choice,segment);
            for(let f=0;f<Math.ceil(run.rows.length/4);f++) {
                actions.push(choice);
                trajectory.push(run.rows[Math.min(run.rows.length-1,f*4+3)]);
            }
            result.frame=actions.length;
            document.getElementById('engine-oracle-status').textContent='ORIGINAL ENGINE SEARCH · frame '+result.frame+' · HP '+run.end.HP;
            if(O.ended) result.status='candidate_found';
            await new Promise(resolve=>setTimeout(resolve,0));
        }
        if(result.status==='searching')result.status='horizon_limit';
        result.ms=performance.now()-started;result.backtracks=backtracks;result.end=O.observe();O.draw();
        return result;
    };
    // A forward time DAG reuses each expanded layer. Quantized diversity bands
    // only select a bounded frontier; they are not an equivalence relation or a
    // completeness proof. Every retained node keeps its entire engine state.
    O.solve = async ({beam=32,segment=4,maxFrames=3600,marginPx=1,budgetMs=60000,resume=false,policy='support'}={}) => {
        if(!O.ready)throw Error('Wait for the original attack to start');
        if(O.searching||O.replaying) throw Error('The original engine is already busy');
        const saved=resume?O.searchSession:null;
        if(resume&&!saved)throw Error('No budget-limited frontier to resume');
        if(saved)({beam,segment,maxFrames,marginPx,policy}=saved.options);
        if(!['support','clearance'].includes(policy))throw Error('Invalid frontier policy');
        if(![beam,segment,maxFrames,marginPx,budgetMs].every(Number.isFinite)||beam<1||segment<1||maxFrames<1||marginPx<0||marginPx>8||budgetMs<1) throw Error('Invalid search options');
        beam=Math.min(512,Math.floor(beam));segment=Math.floor(segment);maxFrames=Math.floor(maxFrames);
        O.searching=true;O.cancelRequested=false;
        const started=performance.now(), result=O.result={status:'searching',frame:0,actions:[],trajectory:[],
            authoritative_runtime:true,realtime_accepted:false,search_limited:true,method:'original-engine-time-dag',
            marginPx,margin_method:'original-inflated-hitbox-per-microtick',beam,segment,policy,
            resumed_from:saved?.frame||0,expanded:saved?.expanded||0,peakStates:saved?.peakStates||1};
        const alphabet=[[0,0],[-1,0],[1,0],[0,1],[-1,1],[1,1],[0,-1],[-1,-1],[1,-1]];
        O.restore(O.initial);const start=saved?.start||O.observe();
        let frontier=saved?.frontier||[{state:O.initial,parent:null,action:[0,0],rows:[],cost:0,margin:8,obs:start}],best=saved?.best||frontier[0];
        let nextFrame=saved?.frame||0;
        O.searchSession=null;
        try {
            outer: for(let frame=nextFrame;frame<maxFrames;frame+=segment) {
                const children=[];
                for(const node of frontier) for(const action of alphabet) {
                    if(O.cancelRequested||performance.now()-started>budgetMs) {
                        result.status=O.cancelRequested?'cancelled':'budget_limit';break outer;
                    }
                    O.restore(node.state);
                    const run=O.step(action,Math.min(segment,maxFrames-frame),marginPx);result.expanded++;
                    if(run.hit||run.clearanceViolation||run.end.HP!==start.HP||run.end.KR!==0) continue;
                    const margin=O.ended?node.margin:Math.min(node.margin,O.clearance());
                    if(margin<marginPx)continue;
                    const held=action[0]||action[1]?Math.ceil(run.rows.length/4):0;
                    const change=Math.abs(action[0]-node.action[0])+Math.abs(action[1]-node.action[1]);
                    const child={state:O.checkpoint(),parent:node,action,rows:run.rows.filter((_,i)=>i%4===3||i===run.rows.length-1),
                        cost:node.cost+held+change*.1,margin,obs:run.end};
                    if(O.ended){best=child;result.status='candidate_found';break outer;}
                    children.push(child);
                }
                if(!children.length){result.status='no_candidate';break;}
                // Safe airborne states can still be unable to land on a moving
                // board. Prefer nearby support before ranking clearance:
                // local obstacle distance alone discarded every landing route
                // in Platforms4Hard near frame264. This is a search preference,
                // never a collision test or a proof that other states are dead.
                const supportDistance=node=>{
                    const s=node.obs;
                    if(policy!=='support'||s.mode!==1||!s.platforms.length)return 0;
                    return Math.min(...s.platforms.map(p=>Math.max(p.x-s.x,s.x-p.x-p.w,0)));
                };
                children.sort((a,b)=>supportDistance(a)-supportDistance(b)||b.margin-a.margin||a.cost-b.cost);
                // Keep XY, ascent/fall velocity and key-edge alternatives before
                // they become useful. Round-robin prevents one spatial band
                // taking the whole frontier due to its lower current input cost.
                const phases=new Map();
                for(const child of children) {
                    const s=child.obs,key=[Math.floor(s.x/12),Math.floor(s.y/8),Math.floor(s.dx/30),Math.floor(s.dy/30),child.action[1]].join(':');
                    const resting=Math.abs(s.dy)<1e-8;
                    // Separate contact heights: standing on the moving board
                    // and standing on the floor have different future reachability.
                    const contact=resting?Math.floor(s.y/16):-1;
                    const phase=[s.mode,Math.round(s.angle*4/Math.PI),resting?0:s.dy<0?1:2,contact].join(':');
                    if(!phases.has(phase))phases.set(phase,new Map());
                    const bands=phases.get(phase);if(!bands.has(key))bands.set(key,[]);bands.get(key).push(child);
                }
                // Reserve representation for ascent/fall/contact modes. A
                // cheaper grounded path must not erase all early jump states.
                const groups=Array.from(phases.values(),bands=>{
                    const group=[];for(let quota=0;group.length<children.length;quota++){
                        let added=false;for(const bucket of bands.values())if(bucket[quota]){group.push(bucket[quota]);added=true;}
                        if(!added)break;
                    }return group;
                });
                frontier=[];
                for(let index=0;frontier.length<beam;index++) {
                    let added=false;
                    for(const group of groups)if(group[index]){frontier.push(group[index]);added=true;if(frontier.length===beam)break;}
                    if(!added)break;
                }
                best=frontier[0];nextFrame=Math.min(frame+segment,maxFrames);result.frame=nextFrame;result.peakStates=Math.max(result.peakStates,frontier.length);
                document.getElementById('engine-oracle-status').textContent='原版引擎搜索 · '+result.frame+' 帧 · '+frontier.length+' 状态 · '+Math.round(performance.now()-started)+' ms';
                await new Promise(resolve=>setTimeout(resolve,0));
            }
            if(result.status==='searching')result.status='horizon_limit';
            const path=[];for(let node=best;node.parent;node=node.parent)path.push(node);path.reverse();
            result.trajectory=[start];
            for(const node of path)for(const row of node.rows){result.actions.push(node.action);result.trajectory.push(row);}
            result.frame=result.actions.length;O.restore(best.state);result.end=O.observe();
            result.ms=(saved?.ms||0)+performance.now()-started;
            // Retain the entire last completed layer, not only its cheapest
            // prefix. A timeout during expansion discards that partial layer;
            // resume repeats only it and preserves every retained alternative.
            if(result.status==='budget_limit')O.searchSession={
                options:{beam,segment,maxFrames,marginPx,policy},frontier,best,start,frame:nextFrame,
                ms:result.ms,expanded:result.expanded,peakStates:result.peakStates};
            O.draw();return result;
        } finally {O.searching=false;}
    };
    // Try sustained, gravity-relative jumps before the bounded frontier.
    // A short jump can be safe locally yet hit a lingering wall stab on the
    // next slam. These policies retain the full hold without paying a beam
    // input-cost penalty at every layer. Every action uses original ticks.
    O.solveEventPolicies=async({maxFrames=3600,marginPx=1,budgetMs=60000}={})=>{
        if(!O.ready||O.searching||O.replaying)throw Error('Original engine is not ready or busy');
        if(![maxFrames,marginPx,budgetMs].every(Number.isFinite)||maxFrames<1||marginPx<0||marginPx>8||budgetMs<1)throw Error('Invalid event-policy options');
        maxFrames=Math.floor(maxFrames);
        O.searching=true;O.cancelRequested=false;
        O.searchSession=null;
        const started=performance.now(),attempts=[];
        let result;
        try{
            for(const hold of [0,8,12,16,20,24,28,32,40]){
                O.restore(O.initial);
                const start=O.observe(),actions=[],trajectory=[start];
                let remaining=0,lastAngle=null,settling=2,rejected=false;
                for(let f=0;f<maxFrames&&!O.ended;f++){
                    if(O.cancelRequested||performance.now()-started>budgetMs){
                        result={status:O.cancelRequested?'cancelled':'budget_limit'};break;
                    }
                    const s=O.observe(),v=s.dx*Math.cos(s.angle)+s.dy*Math.sin(s.angle);
                    const resting=s.mode===1&&Math.abs(v)<1e-6;
                    if(s.angle!==lastAngle||v>100){remaining=0;settling=2;}
                    // Leave two neutral frames after contact. Replaying a key
                    // edge on the exact landing frame can consume the jump
                    // just before contact under normal wall-clock jitter.
                    if(resting&&remaining===0){if(settling>0)settling--;else remaining=hold;}
                    const action=remaining>0?[-Math.round(Math.cos(s.angle)),Math.round(Math.sin(s.angle))]:[0,0];
                    if(remaining>0)remaining--;
                    lastAngle=s.angle;
                    const run=O.step(action,1,marginPx);
                    actions.push(action);trajectory.push(run.end);
                    if(run.hit||run.clearanceViolation||run.end.HP!==start.HP||run.end.KR!==0){rejected=true;break;}
                    if(f%120===0)await new Promise(resolve=>setTimeout(resolve,0));
                }
                attempts.push({hold,frames:actions.length,rejected});
                if(result)break;
                if(O.ended&&!rejected){
                    result={status:'candidate_found',frame:actions.length,actions,trajectory,end:O.observe(),hold,settleFrames:2};break;
                }
            }
            result=result||{status:'no_candidate'};
            result.frame=result.frame||0;
            Object.assign(result,{authoritative_runtime:true,realtime_accepted:false,search_limited:true,beam:1,peakStates:1,
                method:'original-engine-event-policies',marginPx,margin_method:'original-inflated-hitbox-per-microtick',
                attempts,ms:performance.now()-started});
            O.result=result;
            if(result.status!=='candidate_found')O.restore(O.initial);
            O.draw();return result;
        }finally{O.searching=false;}
    };
    O.cancel=()=>{O.cancelRequested=true;};
    function addControls() {
        // Automatic mode has one mathematical solver. Native checkpoint search
        // controls belong to historical debugging, not this workflow.
        if(new URLSearchParams(location.search).get('compute')==='canonical') return;
        const panel=document.createElement('div');
        panel.style='position:fixed;right:10px;bottom:50px;background:#141c28;color:white;padding:12px;z-index:99999;font:14px system-ui;max-width:440px';
        panel.innerHTML='<strong>原版引擎求解</strong><p>完整引擎状态分支；候选仍须实时三回合验收。</p>'+
            '<label>前沿状态数 <input id="oracle-beam" type="number" min="1" max="512" value="24" style="width:60px"></label> '+
            '<label>余量 px <input id="oracle-margin" type="number" min="0" max="8" value="1" style="width:40px"></label><br><br>'+
            '<button id="oracle-solve">求解并检查候选</button> <button id="oracle-resume" hidden>继续上次搜索</button> <button id="oracle-replay">回放已保存路线</button> <button id="oracle-cancel">取消</button><p id="oracle-detail"></p><a id="oracle-live" hidden style="color:#9ef">进入实时三回合验收</a>';
        document.body.appendChild(panel);
        const detail=panel.querySelector('#oracle-detail');
        const query=new URLSearchParams(location.search),wave=query.get('attack')+'.csv',seed=window.__TAS_SEED?.seed;
        const badge=document.getElementById('tas-status-badge');if(badge)badge.textContent='原版引擎分支模式 · 实时验收另行运行';
        for(const id of ['tas-btn-load','tas-btn-run','tas-btn-pause','tas-btn-stop','tas-toggle-autopilot']){
            const el=document.getElementById(id);if(el){el.disabled=true;if(el.type==='checkbox')el.checked=false;}
        }
        panel.querySelector('#oracle-cancel').onclick=O.cancel;
        const runSearch=async(resume)=>{
            const button=panel.querySelector('#oracle-solve'),resumeButton=panel.querySelector('#oracle-resume');
            button.disabled=true;resumeButton.disabled=true;panel.querySelector('#oracle-live').hidden=true;
            try {
                detail.textContent='执行原版引擎搜索，限时 60 秒；取消或超时均不表示死局。';
                const options={beam:Number(panel.querySelector('#oracle-beam').value),marginPx:Number(panel.querySelector('#oracle-margin').value),segment:8,budgetMs:60000,resume};
                let result=resume?null:await O.solveEventPolicies(options);
                const eventAttempt=result;
                if(!result||result.status==='no_candidate')result=await O.solve(options);
                if(eventAttempt&&eventAttempt.status==='no_candidate')result.event_policy_prepass={ms:eventAttempt.ms,attempts:eventAttempt.attempts};
                detail.textContent=result.status+' · '+result.frame+' 帧 · '+Math.round(result.ms)+' ms';
                if(result.status==='candidate_found') {
                    const check=await O.replay(result.actions);
                    if(!check.no_hit)throw Error('候选独立原版回放出现伤害，未发布');
                    const response=await fetch('/api/oracle-plan',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({wave,seed,result})});
                    const saved=await response.json();if(!response.ok)throw Error(saved.error||'保存失败');
                    await fetch('/api/acceptance',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({wave,seed,suite:'oracle-candidate-recheck',trace:check})});
                    const link=panel.querySelector('#oracle-live');query.delete('oracle');query.set('acceptance','1');query.set('continuous','1');
                    query.set('candidate',saved.candidate_id);
                    link.href=location.pathname+'?'+query.toString();link.hidden=false;
                    detail.textContent+=' · 独立原版回放 HP/KR 无变化 · 候选已保存';
                }
            }catch(e){detail.textContent=String(e);}finally{button.disabled=false;resumeButton.disabled=false;resumeButton.hidden=!O.searchSession;}
        };
        panel.querySelector('#oracle-solve').onclick=()=>runSearch(false);
        panel.querySelector('#oracle-resume').onclick=()=>runSearch(true);
        panel.querySelector('#oracle-replay').onclick=async()=>{
            try {
                const plan=await fetch('/api/tas?wave='+encodeURIComponent(wave)+(seed===undefined?'':'&seed='+seed)).then(r=>r.json());
                if(!plan.candidate_found)throw Error('尚无已保存候选');
                const result=await O.replay(plan.action_sequence);
                detail.textContent=result.status+' · HP '+result.rows[0].HP+' → '+result.rows.at(-1).HP+' · KR '+result.rows.at(-1).KR+' · 实时验收待运行';
            }catch(e){detail.textContent=String(e);}
        };
    }
    proto.trigger = function(method,inst,value) {
        const fn=method===cr.plugins_.Function.prototype.cnds.OnFunction?String(value).toLowerCase():'';
        if(O.captureDynamics&&['heartmode','heartteleport','sansslam','heartmaxfallspeed','sansslamdamage','combatzoneresize','combatzoneresizeinstant','bonestab','sinebones','gasterblaster','endattack','tlplay','getheartpos'].includes(fn)){
            const args=[];
            for(let i=0;i<8;i++){
                const ret={val:null,set_any(v){this.val=v;},set_int(v){this.val=v;},set_string(v){this.val=v;},set_float(v){this.val=v;}};
                inst.exps.Param(ret,i);args.push(ret.val);
            }
            O.events.push({tick:this.tickcount,fn,args});
        }
        if(fn==='tlplay'&&!O.ready) pending=true;
        if(fn==='endattack') O.ended=true;
        return trigger.apply(this,arguments);
    };
    proto.tick = function() {
        if(O.ready&&!O.busy) return;
        if(!O.ready&&new URLSearchParams(location.search).get('mode')==='single') {
            // Practice menus and Intro dialogue need ordinary Confirm edges.
            // No script resume, combat state edits or artificial healing.
            const kb=window.TASRunner?.getKeyboardInstance();
            if(kb)kb.keyMap[90]=!!(this.tickcount&32);
        }
        const result=gameTick.apply(this,arguments);
        if(pending&&!O.ready&&this.varsBySid[164016619418963]?.data&&this.varsBySid[3521916820909801]?.data>0) {
            rt=this; pending=false; O.ready=true; O.ended=false;
            const kb=window.TASRunner?.getKeyboardInstance();if(kb)kb.keyMap[90]=false;
            cr_setSuspended(true);
            O.initial=O.checkpoint(); O.start=O.observe();
            let p=document.createElement('pre');p.id='engine-oracle-status';
            p.textContent='ORIGINAL ENGINE ORACLE · paused at attack start · accelerated runs are candidates';
            p.style='position:fixed;bottom:0;color:white;background:#111;padding:8px;z-index:99999';
            document.body.appendChild(p);
            addControls();
            O.draw();
        }
        return result;
    };
    // Oracle preparation is accelerated too. Run the original menus, dialogue
    // and resize callbacks even when a background browser throttles animation
    // frames. Normal real-time acceptance never installs this module's hooks.
    const preparing=setInterval(()=>{
        if(O.ready){clearInterval(preparing);return;}
        const runtime=document.getElementById('c2canvas')?.c2runtime;
        if(!runtime?.running_layout||runtime.isloading)return;
        cr_setSuspended(true);
        for(let i=0;i<8&&!O.ready;i++)runtime.tick(true,runtime.last_tick_time+1000/240,true);
    },16);
})();

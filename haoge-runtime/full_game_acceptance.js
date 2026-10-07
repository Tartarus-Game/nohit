// Strict continuous normal-game observer. Prepared separately for the next
// fresh run; never writes game variables, restores checkpoints, or grants HP.
(() => {
    const query=new URLSearchParams(location.search);
    if(query.get('campaign')!=='1')return;
    const EXPECTED=['intro','bonegap1','bluebone','bonegap2','platforms1','platforms2',
        'platforms3','platforms4','platformblaster','platforms4hard','bonegap1fast','boneslideh',
        'bonegap2','spare','multi1','randomblaster1','multi2','bonestab1','bonestab2',
        'randomblaster2','boneslidev','multi3','bonestab3','final'].map(n=>'sans_'+n);
    const FIELDS=['tick','HP','KR','HitAttempts','SimulatorMode','keymask','confirm',
        'dt','clock_start_ms','previous_confirm','state'];
    const STRIDE=64,MAX_POST_BYTES=8000000-1024;
    const A=window.__FULL_GAME={status:'starting',events:[],rows:[],rounds:[],tickEvidence:[],
        evidenceVersion:3,tickEvidenceFields:FIELDS,sampleStride:STRIDE,firstDamage:null,
        winObserved:false,started:false,done:false,error:null,checkedTicks:0,tickGaps:[],clockErrors:[],
        protocolErrors:[],entrySnapshot:null,win2Snapshot:null,maxKR:0,krExcursions:[]};
    const panel=document.createElement('pre');panel.id='full-game-status';
    panel.style='position:fixed;bottom:4px;left:8px;right:8px;z-index:1000000;background:#122030;color:white;padding:10px;white-space:pre-wrap';
    document.body.appendChild(panel);
    const show=()=>{panel.textContent='整局无伤：'+A.status+' · 已结束回合 '+A.rounds.length+
        (A.firstDamage?' · 首次受伤 tick '+A.firstDamage.tick:'');};
    show();
    function install(){
        const rt=document.getElementById('c2canvas')?.c2runtime;if(!rt)return;
        const proto=rt.constructor.prototype,tick=proto.tick,trigger=proto.trigger;
        let active=null,startCount=0,runCount=0,lastTick=null,lastHits=null,win1=null,endedThisTick=null;
        let hashes=Promise.resolve();
        const digest=async bytes=>Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',bytes)),
            byte=>byte.toString(16).padStart(2,'0')).join('');
        const parameter=(inst,index)=>{
            const ret={value:null,set_any(v){this.value=v;},set_string(v){this.value=v;},set_int(v){this.value=v;},set_float(v){this.value=v;}};
            inst.exps.Param(ret,index);return ret.value;
        };
        function snapshot(){
            const g=Object.fromEntries(rt.all_global_vars.map(v=>[v.name,v.data]));
            const types=rt.types_by_index,one=sid=>types.find(t=>t.sid===sid)?.instances[0];
            const heart=one(5960708907117077),legs=one(9590658027348857),pad=one(9768267065126338)?.instance_vars;
            const zone=one(141231765387603);zone?.update_bbox();const b=zone?.bbox;
            const cm=heart?.behavior_insts.find(b=>b.type.name==='CustomMovement');
            const mask=pad?((pad[2]?1:0)|(pad[3]?2:0)|(pad[0]?4:0)|(pad[1]?8:0)|(pad[5]?16:0)):null;
            const direction=heart?((Math.round(heart.angle/(Math.PI/2))%4)+4)%4:null;
            const maxFall=rt.varsBySid[963626393445968]?.data,bounds=b?[b.left,b.top,b.right,b.bottom]:null;
            const mode=heart?.instance_vars[0],slamDamage=heart?.instance_vars[2];
            return {tick:rt.tickcount,time:rt.kahanTime.sum,clock_start_ms:rt.last_tick_time,HP:g.HP,KR:g.KR,
                SimulatorMode:g.SimulatorMode,HitAttempts:legs?.instance_vars[1],
                keymask:mask,confirm:pad?Number(!!pad[4]):null,previous_confirm:pad?Number(!!pad[11]):null,
                vpad:pad?.slice(0,14),line:rt.varsBySid[2569112556112449]?.data,
                T:rt.varsBySid[3521916820909801]?.data,running:rt.varsBySid[164016619418963]?.data,
                x:heart?.x,y:heart?.y,dx:cm?.dx,dy:cm?.dy,mode,angle:heart?.angle,dt:rt.dt,
                state:heart&&cm?[heart.x,heart.y,cm.dx,cm.dy,mask,heart.instance_vars[1],mode,direction,maxFall,slamDamage,0]:null,
                initial_environment:bounds?[...bounds,mode,direction,0,rt.dt,maxFall,0,0,0,slamDamage,0,...bounds,...bounds]:null,
                arena:zone?{target:zone.instance_vars.slice(0,4),size:[zone.width,zone.height],
                    speed:rt.varsBySid[3111584688851152]?.data,callback:rt.varsBySid[1052618449272991]?.data}:null};
        }
        A.capture=snapshot;
        const violation=(reason)=>{if(!A.protocolErrors.length)A.protocolErrors.push({tick:rt.tickcount,reason});};
        proto.trigger=function(method,inst,value){
            const fn=method===cr.plugins_.Function.prototype.cnds.OnFunction?String(value).toLowerCase():'';
            if(['runattack','startattack','endattack','win1','win2','battlemenu','sansslam','heartmode','heartteleport',
                'damageplayer','tlplay','tlpause','tlresume','getheartpos','combatzoneresize','combatzoneresizeinstant'].includes(fn)){
                const s=snapshot(),event={tick:rt.tickcount,fn,param:parameter(inst,0),HP:s.HP,KR:s.KR,
                    SimulatorMode:s.SimulatorMode,HitAttempts:s.HitAttempts,round:active?.round??A.rounds.length};
                if(fn==='getheartpos') {event.source_line=s.line;event.sampled_position=[s.x,s.y];}
                if(fn==='damageplayer')event.kr=parameter(inst,1);
                A.events.push(event);
                if(['runattack','startattack','endattack','win1','win2'].includes(fn)){
                    if(!window.NoHitBaseline.matches(s.HP,s.KR))A.firstDamage ||= {...s,source:'native_function_boundary'};
                    if(s.SimulatorMode!==0)violation('non_normal_mode_at_'+fn);
                }
                if(fn==='startattack'){
                    if(!A.entrySnapshot){
                        A.entrySnapshot={...s};
                        if(s.HitAttempts!==0)violation('opening_hit_attempts_not_zero');
                    }
                    startCount++;
                    if(active||startCount!==A.rounds.length+1)violation('unexpected_startattack');
                }
                if(fn==='runattack'){
                    runCount++;
                    if(active||event.param!==EXPECTED[A.rounds.length]||runCount!==startCount)violation('unexpected_attack_sequence');
                    active={attack:event.param,startTick:event.tick,round:A.rounds.length};
                }
                if(fn==='tlplay'&&active){
                    if(active.source)violation('unexpected_source_replacement');
                    else {
                        const source={text:String(event.param),preSnapshot:s,sha256:null};
                        active.source=source;
                        hashes=hashes.then(async()=>{source.sha256=await digest(new TextEncoder().encode(source.text));})
                            .catch(error=>violation('source_hash_failure:'+String(error)));
                    }
                }
                if(fn==='endattack'){
                    if(!active||active.attack!==EXPECTED[A.rounds.length])violation('unmatched_endattack');
                    endedThisTick={...active,endTick:event.tick};A.rounds.push(endedThisTick);active=null;
                }
                if(fn==='win1'){
                    if(win1||active||A.rounds.length!==24||runCount!==24)violation('premature_win1');
                    win1=event;
                }
                if(fn==='win2'){
                    if(!win1||A.winObserved||active||A.rounds.length!==24||startCount!==24||runCount!==24||s.HitAttempts!==23)
                        violation('invalid_win2_chain');
                    A.winObserved=true;A.win2Snapshot={...s};
                }
                if(fn==='damageplayer'&&(Number(event.param)>0||Number(parameter(inst,1))>0))
                    A.firstDamage ||= {...s,source:'native_DamagePlayer',damage:event.param};
            }
            return trigger.apply(this,arguments);
        };
        async function save(){
            await hashes;
            if(A.protocolErrors.length&&A.status==='passed'){A.status='failed_protocol';show();}
            const payload={suite:'continuous-normal-game',evidenceVersion:3,seed:window.__TAS_SEED?.seed,
                clock:window.__TAS_CLOCK?.enabled?'original-runtime-realtime-catchup-240hz':'original-runtime-realtime',
                clockProtocol:{mode:window.__TAS_CLOCK?.mode,physicsHz:window.__TAS_CLOCK?.physicsHz,
                    logicalStepMs:window.__TAS_CLOCK?.logicalStepMs},
                criterion:'normal-mode-start-to-Win2-with-no-HP-or-KR-change',
                baselineHP:window.NoHitBaseline.value,
                krPolicy:window.NoHitBaseline.criterion,
                maxKR:A.maxKR,krExcursions:A.krExcursions,
                result:{passed:A.status==='passed',status:A.status,rounds:A.rounds.length},
                firstDamage:A.firstDamage,winObserved:A.winObserved,checkedTicks:A.checkedTicks,
                tickGaps:A.tickGaps,clockErrors:A.clockErrors,protocolErrors:A.protocolErrors,
                entrySnapshot:A.entrySnapshot,win2Snapshot:A.win2Snapshot,
                tickEvidenceFields:FIELDS,tickEvidence:A.tickEvidence,sampleStride:STRIDE,
                computedPlans:window.__CAMPAIGN?.plans||[],
                rowSampling:'every-64-ticks-plus-first-and-terminal',events:A.events,rounds:A.rounds,rows:A.rows};
            try{
                let body=JSON.stringify(payload),bytes=new TextEncoder().encode(body);
                A.payloadBytes=bytes.length;
                if(bytes.length>=MAX_POST_BYTES){
                    const parts=[];
                    for(let offset=0;offset<bytes.length;offset+=2000000){
                        const part=bytes.subarray(offset,Math.min(offset+2000000,bytes.length)),sha256=await digest(part);
                        let binary='';for(let i=0;i<part.length;i+=32768)binary+=String.fromCharCode(...part.subarray(i,i+32768));
                        const response=await fetch('/api/acceptance-evidence',{method:'POST',headers:{'Content-Type':'application/json'},
                            body:JSON.stringify({evidenceVersion:3,encoding:'base64',sha256,data:btoa(binary)})});
                        const saved=await response.json();
                        if(!response.ok||saved.sha256!==sha256||saved.byte_count!==part.length||
                            saved.path!=='campaign-evidence/'+sha256+'.bin')throw Error('Evidence part storage failed or changed identity');
                        parts.push({index:parts.length,...saved});
                    }
                    body=JSON.stringify({suite:payload.suite,evidenceVersion:3,seed:payload.seed,clock:payload.clock,
                        criterion:payload.criterion,result:payload.result,storage:'json-utf8-parts-v1',
                        total_byte_count:bytes.length,total_sha256:await digest(bytes),evidenceParts:parts});
                    A.evidencePartCount=parts.length;
                }
                const response=await fetch('/api/acceptance',{method:'POST',headers:{'Content-Type':'application/json'},body});
                A.saved=await response.json();if(!response.ok)throw Error(A.saved.error);
            }catch(error){A.error=String(error);A.status='failed_save';show();}
        }
        A.save=save;
        A.stop=(reason='external_stop')=>{
            if(!A.done){A.error=String(reason);A.status='failed_driver';A.done=true;A.rows.push(snapshot());
                window.TASRunner?.releaseAllKeys();cr_setSuspended(true);}
            return A.recordPromise=save();
        };
        proto.tick=function(){
            if(window.__TAS_CLOCK?.enabled&&!window.__TAS_CLOCK.stepping)return;
            const previousTimestamp=rt.last_tick_time;
            const result=tick.apply(this,arguments);if(A.done)return result;
            const row=snapshot();
            if(!A.started&&Number.isFinite(row.x)&&Number.isInteger(row.HitAttempts)){
                A.started=true;A.status='running';
                if(!A.entrySnapshot||A.entrySnapshot.tick<row.tick-1)violation('observer_started_after_opening_tick');
            }
            if(A.started){
                // Win2 can remove battle objects when changing layouts. Its
                // same-tick native trigger snapshot directly observed them.
                if(A.win2Snapshot&&row.tick===A.win2Snapshot.tick+1){
                    if(row.HitAttempts===undefined){row.HitAttempts=A.win2Snapshot.HitAttempts;row.HitAttemptsSource='win2_event';}
                    if(row.keymask===null){row.keymask=A.win2Snapshot.keymask;row.confirm=A.win2Snapshot.confirm;}
                    if(!row.state?.every(Number.isFinite)){row.state=A.win2Snapshot.state;row.previous_confirm=A.win2Snapshot.previous_confirm;row.stateSource='win2_event';}
                }
                if(active?.source&&!active.boundary&&(row.line!==1||row.T>0))active.boundary=row;
                if(endedThisTick){
                    if(endedThisTick.source&&!endedThisTick.boundary)endedThisTick.boundary=row;
                    endedThisTick.endSnapshot=row;endedThisTick=null;
                }
                A.checkedTicks++;
                if(lastTick!==null&&row.tick!==lastTick+1)A.tickGaps.push({previous:lastTick,current:row.tick});
                lastTick=row.tick;
                const step=window.__TAS_CLOCK?.logicalStepMs,expectedTimestamp=previousTimestamp+step;
                const expectedDt=Math.min((expectedTimestamp-previousTimestamp)/1000,1/30);
                if(!window.__TAS_CLOCK?.enabled||step!==1000/240||!Number.isFinite(previousTimestamp)||
                    row.clock_start_ms!==expectedTimestamp||row.dt!==expectedDt)
                    A.clockErrors.push({tick:row.tick,dt:row.dt,clock_start_ms:row.clock_start_ms,expectedTimestamp,expectedDt});
                if(row.SimulatorMode!==0)violation('normal_mode_changed');
                if(!Number.isInteger(row.HitAttempts)||row.HitAttempts<0||row.HitAttempts>23||
                    lastHits!==null&&(row.HitAttempts<lastHits||row.HitAttempts>lastHits+1))violation('invalid_hit_attempts');
                lastHits=row.HitAttempts;
                if(!Number.isInteger(row.keymask)||row.keymask<0||row.keymask>31)violation('missing_vpad_observation');
                if(!Array.isArray(row.state)||row.state.length!==11||!row.state.every(Number.isFinite)||
                    ![0,1].includes(row.previous_confirm))violation('missing_native_state_observation');
                A.tickEvidence.push(FIELDS.map(k=>row[k]));
                if(!window.NoHitBaseline.matches(row.HP,row.KR))A.firstDamage ||= row;
                // KR is a recorded observation, not a failure condition: this
                // build's scripts inject KR 1 alongside heals and its lowest HP
                // drain bucket is KR > 10. Anything above that bound would be a
                // real HP threat, so it is reported and flagged separately.
                if(Number(row.KR)>A.maxKR)A.maxKR=Number(row.KR);
                if(Number(row.KR)>0&&A.krExcursions.length<4096)
                    A.krExcursions.push({tick:row.tick,KR:row.KR,HP:row.HP});
                if(Number(row.KR)>10)A.protocolErrors.push({tick:row.tick,reason:'KR_above_drain_bucket',KR:row.KR});
                if(A.firstDamage){A.status='failed_damage';A.done=true;}
                else if(A.protocolErrors.length){A.status='failed_protocol';A.done=true;}
                else if(A.tickGaps.length||A.clockErrors.length){A.status='failed_clock';A.done=true;}
                else if(A.winObserved){
                    A.status=row.HitAttempts===23&&row.tick===A.win2Snapshot.tick+1?'passed':'failed_protocol';A.done=true;
                }
                if(A.checkedTicks===1||row.tick%STRIDE===0||A.done)A.rows.push(row);
                if(A.done){window.TASRunner?.releaseAllKeys();cr_setSuspended(true);A.recordPromise=save();}
            }
            if(rt.tickcount%16===0||A.done)show();return result;
        };
    }
    if(window.cr?.runtime)install();else window.addEventListener('nohit-runtime-ready',install,{once:true});
})();

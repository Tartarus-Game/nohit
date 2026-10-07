// Native custom-wave evidence only. Never changes runtime state or inputs.
(() => {
    const query=new URLSearchParams(location.search);
    if(query.get('custom_acceptance')!=='1')return;
    const selected=(query.get('attack')||'custom').replace(/\.csv$/i,'');
    const A=window.__CUSTOM_WAVE={version:1,status:'waiting',started:false,done:false,
        selected,events:[],rows:[],ticks:[],lifecycles:[],firstDamage:null,errors:[],krInjections:[],
        eofObserved:false,stableTailTicks:0,terminalCertified:false};
    const S={heart:5960708907117077,zone:141231765387603,pad:9768267065126338,list:456555951765879};
    // Keep pre-fire heads/warnings and zero-damage beams: damage==0 is not extinction.
    const attackSids=[3019589746608161,3868174782291034,9836012384209520,7974524067202295,
        8140934880742138,6503092777075739,4163262150020477,336730486351203,508841962091807,165116925986465];
    const familySids=[9590353435551898,6631597198329078,9784977049754560];
    const platformSids=[1226268899238104,6981383464931416];
    const ownedKeys=[37,38,39,40,65,68,83,87,88,16,90,13];
    // Pinned to the haoge-sans gh-pages build (1742137113/haoge-sans,
    // commit a1c36cbc3204e459b0d48df4df076d6895449c18). These are the served
    // bytes of THAT build, not of the vendored jcw87 export: the two exports
    // differ in minification and in the shipped attack scripts, and this build
    // additionally ships MaxHP 142.
    const eofSourceHashes={
        'c2runtime.js':'aef964fb2e9cace38bd302a2316415e41ed304b97de154aa4b51dd61f948115d',
        'data.js':'ba62b1c55f85ccb8b7cad8affdbc1a511d774e5111e17fedce5b7c3639715a1e'};
    function install(){
        const rt=document.getElementById('c2canvas')?.c2runtime;if(!rt)return;
        const proto=rt.constructor.prototype,baseTick=proto.tick,baseTrigger=proto.trigger;
        const one=sid=>rt.types_by_index.find(t=>t.sid===sid)?.instances[0];
        const v=sid=>rt.varsBySid[sid]?.data;
        const globals=()=>Object.fromEntries(rt.all_global_vars.map(g=>[g.name,g.data]));
        const describe=(o,typeSid)=>({uid:o.uid,typeSid,x:o.x,y:o.y,width:o.width,height:o.height,
            angle:o.angle,vars:o.instance_vars?.slice(),behaviors:o.behavior_insts?.map(b=>({
                name:b.type?.name,dx:b.dx,dy:b.dy}))});
        let previous=new Map(),lastTick=null,hashPromise=Promise.resolve();
        A.releaseSnapshots=[];
        // Bind this read-only field inventory to the audited original export.
        // These are fetched source identities, not an attestation of browser bytecode.
        A.sourceReady=Promise.all(Object.entries(eofSourceHashes).map(async([name,expected])=>{
            const response=await fetch(name,{cache:'no-store'});
            if(!response.ok)throw Error('Native EOF source is unavailable: '+name);
            const raw=await response.arrayBuffer(),hash=await crypto.subtle.digest('SHA-256',raw);
            const actual=Array.from(new Uint8Array(hash),b=>b.toString(16).padStart(2,'0')).join('');
            if(actual!==expected)throw Error('Native EOF source identity mismatch: '+name);
            return [name,actual];
        })).then(entries=>A.source_sha256=Object.fromEntries(entries));
        A.sourceReady.catch(error=>A.sourceError=String(error));
        function keyboard() {
            const keys=window.TASRunner?.getKeyboardInstance()?.keyMap;
            if(!keys)throw Error('Native EOF keyboard is unavailable');
            return ownedKeys.map(code=>({code,pressed:!!keys[code]}));
        }
        function captureEof({requireRelease=true}={}) {
            if(!A.source_sha256||A.sourceError)throw Error('Native EOF source audit is unavailable');
            const types=new Map(rt.types_by_index.map(t=>[t.sid,t]));
            function type(sid) {
                const result=types.get(sid);
                if(!result||!Array.isArray(result.instances))throw Error('Native EOF type missing: '+sid);
                return result;
            }
            function family(sid) {
                const result=type(sid);
                if(!Array.isArray(result.members))throw Error('Native EOF family missing: '+sid);
                return {sid,members:result.members.map(member=>{
                    if(type(member.sid)!==member)throw Error('Native EOF family member identity mismatch');
                    return member.sid;
                })};
            }
            const families=familySids.map(family),rpg=family(8627438680975019);
            const union=new Set([...attackSids,...platformSids,...families.flatMap(f=>f.members)]);
            const attack_types=Array.from(union,sid=>({sid,count:type(sid).instances.length}));
            const rpgtext_types=rpg.members.map(sid=>({sid,count:type(sid).instances.length}));
            const list=type(S.list).instances;
            if(list.length!==1||!Number.isInteger(list[0].ra)||list[0].ra<=0)
                throw Error('Native EOF Timeline width is unavailable');
            const line=v(2569112556112449),physical=window.NoHitSolverState.capturePhysical(rt);
            function passiveUi(rows) {
                if(!Array.isArray(rows)||rows.length!==3)throw Error('Native EOF passive UI inventory differs');
                const names=new Set(),uids=new Set();
                for(const row of rows) {
                    const f=row.fields;
                    if(row.typeSid!==6163397057824361||row.familyOffset!==0||!Number.isInteger(row.uid)||row.uid<0||
                        !Array.isArray(f)||f.length!==8||!Array.isArray(row.vars)||row.vars.length!==8||
                        row.vars.some((value,i)=>value!==f[i])||!['HP','PlayerName','QuitMessage'].includes(f[0])||
                        f[1]!==''||f[2]!==''||f[3]!==''||f[4]!==0||f[5]!==0||f[7]!==0||
                        !Number.isFinite(f[6])||f[6]<0||names.has(f[0])||uids.has(row.uid))
                        throw Error('Native EOF RPGText may still trigger a callback');
                    names.add(f[0]);uids.add(row.uid);
                }
                // RPGText.xml only increments T for these source-created UI
                // objects. Empty text/callback, Interactive=0 and Timeout=0
                // exclude typing, input, destruction and callback branches.
                return rows.map(row=>[row.uid,...row.fields.slice(0,6),row.fields[7]]).sort((a,b)=>a[0]-b[0]);
            }
            const ui=passiveUi(physical.rpgtext);
            const keys=keyboard(),layout=rt.running_layout;
            function geometry(instance,sid) {
                instance.update_bbox();const b=instance.bbox;
                const values=[instance.x,instance.y,instance.width,instance.height,instance.angle,b?.left,b?.top,b?.right,b?.bottom];
                if(!values.every(Number.isFinite)||!('ga' in instance)||
                    (sid===S.heart&&!Array.isArray(instance.ga?.hr))||
                    (sid===6657741784745805&&instance.ga!==null))throw Error('Native EOF geometry is incomplete');
                return {typeSid:sid,uid:instance.uid,x:instance.x,y:instance.y,width:instance.width,height:instance.height,
                    angle:instance.angle,bbox:[b.left,b.top,b.right,b.bottom],collisions_enabled:instance.collisionsEnabled,
                    // Original Sprite/Fy uses ga; the legacy adapter's Ua
                    // alias names a different field and is not evidence.
                    collision_polygon:instance.ga?.hr?.slice()??null};
            }
            const hearts=type(S.heart).instances,borders=type(6657741784745805).instances;
            if(hearts.length!==1||borders.length!==4)throw Error('Native EOF heart/border inventory is incomplete');
            if(!Number.isInteger(line)||line<=list[0].ra)throw Error('Native Timeline has not reached EOF');
            if(attack_types.some(t=>t.count!==0)||rpgtext_types.some(t=>t.count!==(t.sid===6163397057824361?3:0)))
                throw Error('Native EOF still owns attack or dialogue entities');
            if(!Array.isArray(rt.Hd?.fc)||rt.Hd.fc.length!==0)throw Error('Native EOF wait queue is not proven empty');
            if(!('ih' in rt)||rt.ih!==null||rt.isloading!==false||
                layout?.Y!==8667945925241823||layout.name!=='BattleScreen')
                throw Error('Native EOF layout continuation is not settled');
            if(physical.SimulatorMode!==2||physical.SingleAttack!=='custom'||v(5359025861573384)!==0)
                throw Error('Native EOF is outside Custom combat');
            // A demonstration must survive a known hit through to the end of the
            // round, so demo mode records the EOF damage instead of refusing it.
            if(!window.NoHitDemo?.enabled &&
                (!window.NoHitBaseline.matches(physical.HP,physical.KR)||A.firstDamage))
                throw Error('Native EOF observed damage');
            if(requireRelease&&(!Array.isArray(physical.vpad)||physical.vpad.length!==14||physical.vpad.some(x=>x!==0)||keys.some(k=>k.pressed)))
                throw Error('Native EOF inputs are not fully released');
            if(physical.arena.callback!==''||physical.arena.target.some((x,i)=>x!==physical.initial_environment[i]))
                throw Error('Native EOF arena continuation is not settled');
            const result={schema_version:1,tick:physical.tick,capture_phase:'posttick',physical,
                timeline:{line,width:list[0].ra,width_field:'ra',list_sid:S.list},
                attack_types,attack_families:families,rpgtext_family:rpg,rpgtext_types,rpgtext_policy:'original-passive-ui-v1',
                wait_queue:{field:'Hd.fc',is_array:true,length:0,entries:[]},
                pending_layout:{field:'ih',present:true,value:null},loading:rt.isloading,
                layout:{sid:layout.Y,name:layout.name},owned_keys:keys,
                globals:{SimulatorMode:physical.SimulatorMode,SingleAttack:physical.SingleAttack},
                menu_state:{sid:5359025861573384,value:v(5359025861573384)},
                heart_geometry:geometry(hearts[0],S.heart),borders:borders.map(o=>geometry(o,6657741784745805)),
                release_snapshots:A.releaseSnapshots.slice(),callback_contract:'original-custom-empty-eof-v1',
                source_sha256:{...A.source_sha256}};
            if(requireRelease) {
                if(!A.drainSnapshot)throw Error('Independent native drain snapshot is unavailable');
                if(JSON.stringify(ui)!==JSON.stringify(passiveUi(A.drainSnapshot.physical.rpgtext)))
                    throw Error('Native EOF passive UI identity changed after drain');
                result.drain_snapshot=A.drainSnapshot;A.eofTerminal=result;
            } else A.drainSnapshot=result;
            return result;
        }
        A.captureEof=captureEof;
        function capture(){
            const g=globals(),h=one(S.heart),z=one(S.zone),pad=one(S.pad)?.instance_vars;
            const cm=h?.behavior_insts?.find(b=>b.type.name==='CustomMovement');
            z?.update_bbox();const b=z?.bbox;
            const mask=pad?((pad[2]?1:0)|(pad[3]?2:0)|(pad[0]?4:0)|(pad[1]?8:0)|(pad[5]?16:0)):null;
            const direction=h?((Math.round(h.angle/(Math.PI/2))%4)+4)%4:null;
            const types=new Map(rt.types_by_index.filter(t=>attackSids.includes(t.sid)||platformSids.includes(t.sid)).map(t=>[t.sid,t]));
            for(const sid of familySids)for(const member of rt.types_by_index.find(t=>t.sid===sid)?.members||[])
                types.set(member.sid,member);
            const pending=[];for(const t of types.values())for(const o of t.instances||[])pending.push(describe(o,t.sid));
            return {tick:rt.tickcount,time:rt.kahanTime.sum,clock_start_ms:rt.last_tick_time,dt:rt.dt,
                HP:g.HP,KR:g.KR,SimulatorMode:g.SimulatorMode,attack:g.SingleAttack,
                line:v(2569112556112449),T:v(3521916820909801),running:v(164016619418963),
                // jcw Array width is minified as ra (uc.S: size[0], Width→bh).
                // cx belongs to the unminified export and is not aliased here.
                lineCount:one(S.list)?.ra??one(S.list)?.cx,keymask:mask,confirm:pad?Number(!!pad[4]):null,
                state:h&&cm?[h.x,h.y,cm.dx,cm.dy,mask,h.instance_vars[1],h.instance_vars[0],direction,
                    v(963626393445968),h.instance_vars[2],0]:null,
                heartVars:h?.instance_vars?.slice(),arena:b?[b.left,b.top,b.right,b.bottom]:null,
                arenaTarget:z?.instance_vars?.slice(0,4),arenaVars:z?.instance_vars?.slice(),
                resizeSpeed:v(3111584688851152),endResize:v(1052618449272991),pending};
        }
        A.capture=capture;
        A.save=async()=>{
            await hashPromise;
            const payload={suite:'custom-wave-native-observation',version:1,selected:A.selected,
                csv_sha256:A.csv_sha256,csv_bytes:A.csv_bytes,sourceText:A.sourceText,
                seed:window.__TAS_SEED?.seed,result:{passed:false,status:A.status},
                audioCompatibility:window.__AUDIO_COMPAT,
                entry:A.entry,firstDamage:A.firstDamage,errors:A.errors,eofObserved:A.eofObserved,
                eofSnapshot:A.eofSnapshot,stopReason:A.stopReason,
                stableTailTicks:A.stableTailTicks,terminalCertified:false,events:A.events,rows:A.rows,
                tickFields:['tick','HP','KR','SimulatorMode','keymask','confirm','line','T','running','pendingCount'],
                ticks:A.ticks,lifecycles:A.lifecycles};
            const body=JSON.stringify(payload);
            if(new TextEncoder().encode(body).length>=7998976){A.saveError='evidence_size';return;}
            try{const r=await fetch('/api/acceptance',{method:'POST',headers:{'Content-Type':'application/json'},body});
                A.saved=await r.json();if(!r.ok)throw Error(A.saved.error||r.status);
            }catch(e){A.saveError=String(e);}
        };
        A.stop=(reason='manual_observation_end')=>{
            if(!A.done){A.done=true;A.status=A.firstDamage?'failed_damage':'incomplete';A.stopReason=reason;A.rows.push(capture());}
            return A.recordPromise=A.save();
        };
        const param=(inst,i)=>{const r={value:null,set_any(x){this.value=x;},set_int(x){this.value=x;},
            set_float(x){this.value=x;},set_string(x){this.value=x;}};inst.exps.Param(r,i);return r.value;};
        function terminalGeometry(instance,sid) {
            instance.update_bbox();const b=instance.bbox;
            return {typeSid:sid,uid:instance.uid,x:instance.x,y:instance.y,width:instance.width,height:instance.height,
                angle:instance.angle,bbox:[b.left,b.top,b.right,b.bottom],collisions_enabled:instance.collisionsEnabled,
                collision_polygon:instance.ga?.hr?.slice()??null,vars:instance.instance_vars?.slice()??[]};
        }
        function terminalSnapshot(phase) {
            const types=new Map(rt.types_by_index.map(t=>[t.sid,t]));
            const instances=sid=>{
                const rows=types.get(sid)?.instances;
                if(!Array.isArray(rows))throw Error('Missing native terminal type: '+sid);
                return rows;
            };
            const hearts=instances(S.heart),borders=instances(6657741784745805);
            if(hearts.length!==1||borders.length!==4)throw Error('Incomplete native terminal geometry');
            return {capture_phase:phase,physical:window.NoHitSolverState.capturePhysical(rt),
                platforms:platformSids.flatMap(sid=>instances(sid).map(o=>terminalGeometry(o,sid))),
                heart_geometry:terminalGeometry(hearts[0],S.heart),
                borders:borders.map(o=>terminalGeometry(o,6657741784745805))};
        }
        function terminalCaller() {
            // Ea/Ia/Wb and Fc are the original current event/action stack;
            // Ka already holds the evaluated CallFunction parameters. Merely
            // finding EndAttack in the loaded row cannot establish its caller.
            const stack=rt.Ea(),event=stack.Ia,action=event?.Fc?.[stack.Wb];
            const source_line=v(2569112556112449),loaded=one(3081225054711249),list=one(S.list);
            return {sheet:event?.sheet?.name??null,event_sid:event?.Y??null,action_sid:action?.Y??null,
                action_index:stack.Wb,action_parameters:action?.Ka?.map(x=>Array.isArray(x)?x.slice():x)??null,
                source_line,loaded_line_sid:3081225054711249,
                loaded_line:loaded?Array.from({length:loaded.ra},(_,i)=>loaded.pc(i,0,0)):null,
                raw_source_line:list?.pc(source_line-1,0,0)??null};
        }
        let movementGroup=null,pendingTerminal=null;
        function observeMovementBoundary() {
            if(movementGroup)return;
            const group=rt.Qf?.find(e=>e.Y===6451037740410459);
            if(!group||typeof group.Ya!=='function')throw Error('Original PlayerMovement group is unavailable');
            movementGroup=group;const nativeRun=group.Ya;
            group.Ya=function() {
                const event=pendingTerminal;
                if(event&&event.tick===rt.tickcount) {
                    try {
                        if(event.snapshots.before_movement)throw Error('Repeated terminal PlayerMovement boundary');
                        event.snapshots.before_movement={...terminalSnapshot('before_native_player_movement'),
                            event_sid:this.Y,sheet:this.sheet?.name,group_name:this.vh};
                    } catch(error) {event.snapshots.error=String(error);}
                    pendingTerminal=null;
                }
                return nativeRun.apply(this,arguments);
            };
        }
        proto.trigger=function(method,inst,value){
            const fn=method===cr.plugins_.Function.prototype.cnds.OnFunction?String(value).toLowerCase():'';
            let terminalEvent=null;
            if(fn==='tlplay'&&!A.started){
                const g=globals();
                if(g.SingleAttack===selected||g.SingleAttack==='custom'){
                    A.started=true;A.status='observing';A.entry=capture();A.sourceText=String(param(inst,0));
                    const bytes=new TextEncoder().encode(A.sourceText);A.csv_bytes=bytes.length;
                    hashPromise=crypto.subtle.digest('SHA-256',bytes).then(x=>A.csv_sha256=
                        Array.from(new Uint8Array(x),b=>b.toString(16).padStart(2,'0')).join(''))
                        .catch(e=>A.errors.push({reason:'hash_failure',detail:String(e)}));
                    if(!window.NoHitBaseline.matches(g.HP,g.KR))A.firstDamage={...A.entry,source:'entry'};
                }
            }
            if(A.started&&!A.done&&fn&&['tlplay','tlresume','tlpause','endattack','damageplayer','resetvars','tlstop',
                'heartteleport','heartmode','sansslam','combatzoneresize','combatzoneresizeinstant',
                'getheartpos','gasterblaster','bonestab'].includes(fn)){
                const args=Array.from({length:9},(_,i)=>param(inst,i));
                const event={tick:rt.tickcount,fn,args:fn==='tlplay'?[]:args};
                if(fn==='getheartpos') {
                    const heart=one(S.heart);
                    event.source_line=v(2569112556112449);
                    event.sampled_position=[heart.x,heart.y];
                }
                A.events.push(event);
                if(fn==='endattack') {
                    terminalEvent=event;
                    try {
                        observeMovementBoundary();
                        const caller=terminalCaller();
                        event.snapshots={schema_version:1,source:
                            caller.sheet==='Timeline'&&caller.event_sid===441595194418922&&
                            caller.action_sid===9188948149072352&&caller.action_index===0?'timeline':'other',
                            source_line:caller.source_line,caller,source_sha256:{...A.source_sha256},
                            before:terminalSnapshot('before_native_endattack')};
                        pendingTerminal=event;
                    } catch(error) {
                        event.snapshots={schema_version:1,error:String(error)};
                    }
                }
                if(fn==='damageplayer') {
                    // Positive Param(0) is real HP loss (the event sheet does
                    // `HP -= Param(0)` with no guard). Negative Param(0) is a heal
                    // and Param(1) raises KR; this build drains HP only above
                    // KR 10, so a KR of 1 is recorded, never charged as a hit.
                    const damage=Number(args[0]),kr=Number(args[1]);
                    if(damage>0) A.firstDamage ||= {...capture(),source:'DamagePlayer',args};
                    else if(Number.isFinite(kr)&&kr>0)
                        A.krInjections.push({tick:rt.tickcount,damage,kr,line:v(2569112556112449),args});
                }
            }
            const output=baseTrigger.apply(this,arguments);
            if(terminalEvent) {
                try {terminalEvent.snapshots.after=terminalSnapshot('after_native_endattack');}
                catch(error) {terminalEvent.snapshots.error=String(error);}
            }
            return output;
        };
        proto.tick=function(){
            const out=baseTick.apply(this,arguments);
            if(!A.started||A.done||lastTick===rt.tickcount)return out;
            const r=capture();
            if(lastTick!==null&&r.tick!==lastTick+1)A.errors.push({reason:'tick_gap',previous:lastTick,tick:r.tick});
            lastTick=r.tick;
            if(!window.NoHitBaseline.matches(r.HP,r.KR))A.firstDamage ||= {...r,source:'native_tick'};
            if(!r.state||!r.arena||!Number.isInteger(r.line)||!Number.isInteger(r.lineCount))
                A.errors.push({reason:'missing_native_state',tick:r.tick});
            const now=new Map(r.pending.map(o=>[o.uid,o]));
            for(const [uid,o] of now)if(!previous.has(uid))A.lifecycles.push({tick:r.tick,kind:'created',object:o});
            for(const [uid,o] of previous)if(!now.has(uid))A.lifecycles.push({tick:r.tick,kind:'destroyed',uid,typeSid:o.typeSid});
            previous=now;
            const eof=Number.isInteger(r.line)&&Number.isInteger(r.lineCount)&&r.line>r.lineCount&&r.lineCount>0;
            if(eof&&!A.eofObserved){A.eofObserved=true;A.eofSnapshot=r;A.rows.push(r);}
            const settled=r.state&&r.state[2]===0&&r.state[3]===0&&r.endResize===''&&
                r.arena&&r.arenaTarget&&r.arena.every((x,i)=>x===Number(r.arenaTarget[i]));
            A.stableTailTicks=eof&&now.size===0&&settled?A.stableTailTicks+1:0;
            A.ticks.push([r.tick,r.HP,r.KR,r.SimulatorMode,r.keymask,r.confirm,r.line,r.T,r.running,now.size]);
            if(A.ticks.length===1||r.tick%16===0)A.rows.push(r);
            if(window.__CSV_TAS?.plan?.completion?.kind==='eof_invariant') {
                A.releaseSnapshots.push({physical:window.NoHitSolverState.capturePhysical(rt),owned_keys:keyboard()});
                if(A.releaseSnapshots.length>2)A.releaseSnapshots.shift();
                if(r.tick===window.__CSV_TAS.boundary.tick+window.__CSV_TAS.plan.completion.drain_tick)
                    captureEof({requireRelease:false});
            }
            // This observer has no proof that all future native callbacks are
            // exhausted. Even an empty, stable EOF remains explicitly incomplete.
            if(eof)A.status='incomplete_eof';
            // Demo mode records the hit and keeps going: the run has to reach the
            // end of the fight for a demonstration. The hitting tick is still in
            // A.firstDamage and A.status keeps naming the outcome.
            if(A.firstDamage&&!window.NoHitDemo?.enabled){
                A.done=true;A.status='failed_damage';A.rows.push(r);A.recordPromise=A.save();}
            return out;
        };
    }
    if(window.cr?.runtime)install();else window.addEventListener('nohit-runtime-ready',install,{once:true});
})();

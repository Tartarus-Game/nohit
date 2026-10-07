// Production CSV controller, physical capture and scheduler with a native-shaped
// test runtime. This verifies ownership/timing, not original-game acceptance.
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import {createHash,webcrypto} from 'node:crypto';

function boot(options={}) {
    const text=options.text??'0,HeartMode,0\n0.1,SansText,a\n0,EndAttack\n';
    const source={text,sha256:createHash('sha256').update(text).digest('hex'),name:'test.csv'};
    const keys=Array(256).fill(false),pad=Array(14).fill(0),raf=[],inputs=[],requests=[];
    const heart={x:320,y:304,angle:Math.PI/2,instance_vars:[0,0,0],behavior_insts:[{type:{name:'CustomMovement'},dx:0,dy:0}]};
    const zone={bbox:{left:133,top:251,right:508,bottom:391},width:375,height:140,
        instance_vars:[133,251,508,391,''],update_bbox(){}};
    let c,resolveFetch,fetchGate=options.deferred?new Promise(resolve=>resolveFetch=resolve):Promise.resolve();
    class Runtime {
        trigger(method,inst,fn) {
            if(fn==='tlplay') {this.varsBySid[2569112556112449].data=1;this.varsBySid[3521916820909801].data=0;}
        }
        tick(background,stamp) {
            const dt=Math.min((stamp-this.last_tick_time)/1000,1/30);this.dt=dt;this.last_tick_time=stamp;
            for(let i=0;i<7;i++)pad[i+7]=pad[i];
            Object.assign(pad,{0:Number(!!keys[38]),1:Number(!!keys[40]),2:Number(!!keys[37]),3:Number(!!keys[39]),
                4:Number(!!(keys[90]||keys[13])),5:Number(!!(keys[88]||keys[16])),6:0});
            const driving=c.__CSV_TAS?.status==='playing';
            inputs.push({mask:pad[2]|pad[3]<<1|pad[0]<<2|pad[1]<<3|pad[5]<<4,confirm:!!pad[4],dt,driving});
            if(driving) {
                heart.x+=1;
                const index=c.__CSV_TAS.actionsApplied;
                if(index+1===(options.endAt??options.actions?.length??2)&&!options.noEnd)emit('endattack');
                options.afterInput?.({c,rt:this,heart,pad,emit,index});
            }
            this.work?.();this.work=null;this.kahanTime.sum+=dt;this.tickcount++;
        }
        draw() {}
    }
    const rt=new Runtime();
    Object.assign(rt,{tickcount:100,last_tick_time:options.startTimestamp??2000000,dt:1/30,kahanTime:{sum:5},running_layout:{},suspended:false,
        types_by_index:[{sid:5960708907117077,instances:[heart]},{sid:141231765387603,instances:[zone]},
            {sid:9768267065126338,instances:[{instance_vars:pad}]}],
        all_global_vars:[{name:'HP',data:92},{name:'KR',data:0},{name:'SimulatorMode',data:2},{name:'SingleAttack',data:'custom'}],
        varsBySid:{963626393445968:{data:750},3521916820909801:{data:0},164016619418963:{data:1},2569112556112449:{data:1},
            3111584688851152:{data:30},1052618449272991:{data:''}}});
    c={console:{log(){},warn(){}},URL,URLSearchParams,TextEncoder,Uint8Array,crypto:webcrypto,AbortController,
        location:{search:'?csvtas=1&seed=42'+(options.query||'')},
        document:{hidden:false,addEventListener(){},getElementById:id=>id==='c2canvas'?{c2runtime:rt}:null},
        c2runtime:rt,cr:{runtime:Runtime,plugins_:{Function:{prototype:{cnds:{OnFunction(){}}}}}},
        TASRunner:{getKeyboardInstance:()=>({keyMap:keys}),isTickHooked:()=>true,releaseAllKeys:()=>keys.fill(false)},
        __CSV_SOURCE:source,__CSV_SOURCE_READY:Promise.resolve(source),
        performance:{now:()=>0},requestAnimationFrame:callback=>raf.push(callback),
        cr_setSuspended(value){rt.suspended=value;if(!value)rt.last_tick_time=999999;},
        fetch:async(url,request)=>{
            const body=JSON.parse(request.body);requests.push({url,body});await fetchGate;
            const boundary=c.__CSV_TAS.boundary,actions=options.actions||[2,4],confirms=options.confirms||[false,true];
            const plan={status:'candidate_found',verified:true,planner:'bounded-frontier-with-dialogue',csv_sha256:source.sha256,
                actions,confirm_sequence:confirms,trajectory:[boundary.initial,...actions.map((mask,i)=>{const s=boundary.initial.slice();s[0]+=i+1;s[4]=mask;return s;})],
                initial_confirm:boundary.initial_confirm,previous_confirm:boundary.previous_confirm,
                provenance:{request_id:body.request_id,fresh_computation:true,route_cache_hit:false},
                clock:{schedule_count:body.dt_schedule.length,
                    schedule_sha256:createHash('sha256').update(Buffer.from(new Float64Array(body.dt_schedule).buffer)).digest('hex')},
                control_ticks:1,physics_hz:body.fps===30?30:null,
                control_hz:body.fps===30?30:null,clock_protocol:'explicit_dt_schedule',
                initial_arena:body.initial_arena??{target:[133,251,508,391],size:[375,140],speed:30,callback:''},
                dt_sequence:body.dt_schedule.slice(0,actions.length+1),
                visualization:{frames:[{env:boundary.initial_environment.slice(),bounds:boundary.initial_environment.slice(0,4)}]}};
            options.plan?.(plan);
            return {ok:true,json:async()=>plan};
        }};
    c.window=c;vm.createContext(c);
    for(const file of ['solver_state','lag_compensation','csv_round_controller','csv_tas_runner'])
        vm.runInContext(fs.readFileSync(new URL('../c2-sans-fight/'+file+'.js',import.meta.url),'utf8'),c);
    function emit(fn,value='',second=0) {rt.trigger(c.cr.plugins_.Function.prototype.cnds.OnFunction,{exps:{Param(result,i){result.set_any(i===0?value:second);}}},fn);}
    function step(work) {rt.work=work;c.__TAS_CLOCK.stepping=true;try{rt.tick(true,rt.last_tick_time+c.__TAS_CLOCK.logicalStepMs,true);}finally{c.__TAS_CLOCK.stepping=false;}}
    function start() {emit('tlplay',source.text);step(()=>{rt.varsBySid[2569112556112449].data=2;rt.varsBySid[3521916820909801].data=rt.dt;});return c.__CSV_TAS.solvePromise;}
    return {c,rt,keys,pad,heart,zone,inputs,requests,source,emit,step,start,resolveFetch,
        frame(now){assert(raf.length);raf.shift()(now);}};
}

test('physical capture preserves old API but reads all committed VPad latches',()=>{
    const g=boot();g.pad.fill(1);g.keys.fill(false);
    const old=g.c.NoHitSolverState.capture(g.rt),physical=g.c.NoHitSolverState.capturePhysical(g.rt);
    assert.equal(old.initial[4],0);assert.equal(physical.initial[4],31);assert.equal(physical.physical_keymask,0);
    assert.equal(physical.initial_confirm,true);assert.equal(physical.previous_confirm,true);assert.equal(physical.vpad.length,14);
});

test('physical capture includes a detached snapshot of the current arena continuation',()=>{
    const g=boot(),physical=g.c.NoHitSolverState.capturePhysical(g.rt);
    const expected={target:[133,251,508,391],size:[375,140],speed:30,callback:''};
    assert.deepEqual(JSON.parse(JSON.stringify(physical.arena)),expected);
    g.zone.instance_vars[0]=999;g.zone.width=999;
    g.rt.varsBySid[3111584688851152].data=999;
    g.rt.varsBySid[1052618449272991].data='TLResume';
    assert.deepEqual(JSON.parse(JSON.stringify(physical.arena)),expected);
});

test('the ordinary custom prelude waits for the inherited arena target before pressing Confirm',()=>{
    const g=boot();g.zone.instance_vars[0]=134;
    const began=g.rt.tickcount;g.step();
    assert.equal(g.rt.tickcount,began+1);assert.equal(g.keys[90],false);assert.equal(g.pad[4],0);
    assert.equal(g.requests.length,0);
    g.zone.bbox.left=134;g.step();
    assert.equal(g.keys[90],true);assert.equal(g.pad[4],1);
});

for(const idleBeforeRow0 of [false,true])for(const [label,history,expected] of [
    ['matching native sample',[[0,2,320,304]],'playing'],
    ['post-teleport replacement',[[0,2,321,304]],'failed'],
    ['missing native sample',[],'failed'],
])test('row0 GetHeartPos '+label+' is checked before playback'+(idleBeforeRow0?' after a TLPlay-only tick':''),async()=>{
    const g=boot({text:'0,HeartMode,0\n0,GetHeartPos,x,y\n0,HeartTeleport,321,304\n0.1,EndAttack\n',
        plan:plan=>plan.target_history=history});
    g.emit('tlplay',g.source.text);
    if(idleBeforeRow0)g.step(); // TLPlay loads Line1/T0; source execution may start later.
    g.step(()=>{
        g.rt.varsBySid[2569112556112449].data=2;
        g.emit('getheartpos','x','y');
        g.heart.x=321;
        g.rt.varsBySid[2569112556112449].data=4;
        g.rt.varsBySid[3521916820909801].data=1/30;
    });
    await g.c.__CSV_TAS.solvePromise;
    assert.equal(g.c.__CSV_TAS.boundary.initial[0],321);
    assert.equal(g.c.__CSV_TAS.status,expected);
    if(expected==='failed') {
        assert.equal(g.rt.suspended,true);assert.equal(g.inputs.filter(row=>row.driving).length,0);
    }
});

test('only target TLPlay and its first committed Timeline tick become frame0',async()=>{
    const g=boot();g.emit('tlplay','preparation');g.step();assert.equal(g.requests.length,0);
    g.emit('tlplay',g.source.text);g.step();assert.equal(g.c.__CSV_TAS.boundary,null); // only Line1/T0
    g.step(()=>{g.rt.varsBySid[2569112556112449].data=4;g.rt.varsBySid[164016619418963].data=0;});
    await g.c.__CSV_TAS.solvePromise;
    assert.equal(g.c.__CSV_TAS.boundary.tick,103);assert.equal(g.c.__CSV_TAS.boundary.running,0);
    assert.equal(g.requests[0].body.custom_csv,g.source.text);assert.equal(g.requests[0].body.fps,30);
    assert.equal(g.requests[0].body.initial.length,11);assert.equal(g.c.__CSV_TAS.actionsApplied,0);
});

test('row0 resize sends the environment before target TLPlay and keeps the observed player boundary',async()=>{
    const g=boot(),before=g.c.NoHitSolverState.capture(g.rt).initial_environment.slice();
    g.emit('tlplay',g.source.text);
    g.step(()=>{
        Object.assign(g.zone.bbox,{left:134,top:250,right:507,bottom:392});
        g.heart.x=321;
        g.rt.varsBySid[2569112556112449].data=2;
        g.rt.varsBySid[3521916820909801].data=1/30;
    });
    await g.c.__CSV_TAS.solvePromise;
    assert.deepEqual(Array.from(g.requests[0].body.initial_environment),Array.from(before));
    assert.deepEqual(Array.from(g.c.__CSV_TAS.boundary.initial_environment.slice(0,4)),[134,250,507,392]);
    assert.equal(g.requests[0].body.initial[0],321);
    assert.equal(g.c.__CSV_TAS.status,'playing');
});

test('arena capture preserves native targets, dimensions and callback without deriving or rounding them',()=>{
    const g=boot(),expected={target:[32.00000000000001,240.25,608.75,384.875],
        size:[575.9999999999999,143.99999999999997],speed:30.125,callback:'AfterResize'};
    g.zone.instance_vars.splice(0,4,...expected.target);
    [g.zone.width,g.zone.height]=expected.size;
    g.rt.varsBySid[3111584688851152].data=expected.speed;
    g.rt.varsBySid[1052618449272991].data=expected.callback;
    const actual=g.c.NoHitSolverState.captureArena(g.rt);
    assert.deepEqual(JSON.parse(JSON.stringify(actual)),expected);
    assert.notEqual(actual.size[0],g.zone.bbox.right-g.zone.bbox.left);
    g.zone.instance_vars[0]=999;g.zone.width=999;
    assert.deepEqual(JSON.parse(JSON.stringify(actual)),expected);
});

test('row0 forwards the complete pre-TLPlay arena even when automatic entry changes it',async()=>{
    const g=boot(),expected={target:[32.00000000000001,240.25,608.75,384.875],
        size:[575.9999999999999,143.99999999999997],speed:30.125,callback:'AfterResize'};
    g.zone.instance_vars.splice(0,4,...expected.target);
    [g.zone.width,g.zone.height]=expected.size;
    g.rt.varsBySid[3111584688851152].data=expected.speed;
    g.rt.varsBySid[1052618449272991].data=expected.callback;
    g.emit('tlplay',g.source.text);
    g.step(()=>{
        g.zone.instance_vars.splice(0,4,100,200,500,400);
        g.zone.width=574;g.zone.height=142;
        g.rt.varsBySid[3111584688851152].data=60;
        g.rt.varsBySid[1052618449272991].data='';
        g.rt.varsBySid[2569112556112449].data=2;
        g.rt.varsBySid[3521916820909801].data=1/30;
    });
    await g.c.__CSV_TAS.solvePromise;
    assert.deepEqual(g.requests[0].body.initial_arena,expected);
    assert.deepEqual(JSON.parse(JSON.stringify(g.c.__CSV_TAS.source_arena)),expected);
    assert.equal(g.c.__CSV_TAS.status,'playing');
});

for(const [label,mutate] of [
    ['target',arena=>arena.target[0]+=1],['size',arena=>arena.size[0]+=1],
    ['speed',arena=>arena.speed+=1],['callback',arena=>arena.callback='UnexpectedCallback'],
])test('a candidate with changed initial arena '+label+' is rejected before native playback',async()=>{
    const g=boot({plan:plan=>mutate(plan.initial_arena)});await g.start();
    assert.equal(g.c.__CSV_TAS.status,'failed');assert.equal(g.rt.suspended,true);
    assert.equal(g.inputs.filter(row=>row.driving).length,0);
});

test('a candidate missing its initial arena is rejected before native playback',async()=>{
    const g=boot({plan:plan=>delete plan.initial_arena});await g.start();
    assert.equal(g.c.__CSV_TAS.status,'failed');assert.equal(g.rt.suspended,true);
    assert.equal(g.inputs.filter(row=>row.driving).length,0);
});

test('a plan rebuilt one resize tick ahead is rejected before native playback',async()=>{
    const g=boot({plan:plan=>{plan.visualization.frames[0].env[0]+=1;plan.visualization.frames[0].bounds[0]+=1;}});
    await g.start();
    assert.equal(g.c.__CSV_TAS.status,'failed');assert.equal(g.rt.suspended,true);
    assert.equal(g.inputs.filter(row=>row.driving).length,0);
});

test('fetch pauses the same runtime; actions and Confirm each reach one actual next tick',async()=>{
    const g=boot({deferred:true});const promise=g.start(),entryTick=g.rt.tickcount,stamp=g.rt.last_tick_time;
    assert.equal(g.rt.suspended,true);g.step();assert.equal(g.rt.tickcount,entryTick);
    g.resolveFetch();await promise;assert.equal(g.c.__CSV_TAS.status,'playing');assert.equal(g.rt.last_tick_time,stamp);
    g.step();assert.equal(g.c.__CSV_TAS.actionsApplied,1);assert.equal(g.keys[39],true);assert.equal(g.pad[4],0);
    g.step();assert.equal(g.c.__CSV_TAS.status,'completed');assert.equal(g.c.__CSV_TAS.nativeEndAttack,true);
    assert.equal(g.rt.suspended,true);assert.equal(g.keys.some(Boolean),false);g.step();assert.equal(g.rt.tickcount,entryTick+2);
    assert.deepEqual(g.inputs.filter(row=>row.driving).map(row=>[row.mask,row.confirm]),[[2,false],[4,true]]);
    assert.equal(g.c.__CSV_TAS.original_replay_passed,false);
});

test('held Confirm and a later release are preserved, not synthesized from frame rate',async()=>{
    const g=boot({actions:[0,0,0,0],confirms:[true,true,false,true]});await g.start();
    for(let i=0;i<4;i++)g.step();assert.equal(g.c.__CSV_TAS.status,'completed');
    assert.deepEqual(g.inputs.filter(row=>row.driving).map(row=>row.confirm),[true,true,false,true]);
    assert.equal(g.keys[90],false);assert.equal(g.keys[13],false);
});

test('unknown remains paused and publishes no playback even after attempted native ticks',async()=>{
    const g=boot({plan:plan=>{plan.status='unknown';plan.verified=false;plan.reason='wall_budget';}});await g.start();
    const tick=g.rt.tickcount;assert.equal(g.c.__CSV_TAS.status,'unknown');g.rt.suspended=false;g.step();
    assert.equal(g.rt.tickcount,tick);assert.equal(g.c.__CSV_TAS.actionsApplied,0);assert.equal(g.keys.some(Boolean),false);
});

test('candidate extending beyond the requested clock never resumes the native runtime',async()=>{
    const g=boot({query:'&max_ticks=2',plan:plan=>{
        // All three samples are valid at the original 30 Hz native clamp,
        // but the request authorized only frame zero and one input tick.
        plan.dt_sequence=[1/30,1/30,1/30];
    }});
    await g.start();
    assert.equal(g.requests[0].body.dt_schedule.length,2);
    assert.equal(g.c.__CSV_TAS.plan.actions.length,2);
    assert.equal(g.c.__CSV_TAS.plan.clock.schedule_count,2);
    assert.equal(g.c.__CSV_TAS.status,'failed');
    assert.match(g.c.__CSV_TAS.error,/request.*clock|clock.*request/i);
    assert.equal(g.rt.suspended,true);assert.equal(g.keys.some(Boolean),false);
    g.step();assert.equal(g.inputs.filter(row=>row.driving).length,0);
});

test('candidate consuming exactly the requested clock still completes in the native runtime',async()=>{
    const g=boot({query:'&max_ticks=3'});await g.start();
    assert.equal(g.c.__CSV_TAS.status,'playing');
    assert.deepEqual(Array.from(g.c.__CSV_TAS.plan.dt_sequence),g.requests[0].body.dt_schedule);
    g.step();g.step();assert.equal(g.c.__CSV_TAS.status,'completed');
    assert.equal(g.inputs.filter(row=>row.driving).length,2);
});

for(const [name,mutate] of [
    ['hash',p=>p.csv_sha256='wrong'],['initial',p=>p.trajectory[0]=Array(11).fill(0)],
    ['dt',p=>p.dt_sequence[1]=1/60],['Confirm',p=>p.confirm_sequence=[false]],['Cancel',p=>p.actions[0]=16],
    ['initial Confirm',p=>delete p.initial_confirm],
    ['request identity',p=>p.provenance.request_id='stale'],
    ['fresh computation',p=>p.provenance.fresh_computation=false],
    ['cached route',p=>p.provenance.route_cache_hit=true],
    ['full clock hash',p=>p.clock.schedule_sha256='wrong'],
    ['full clock length',p=>p.clock.schedule_count--],
])test('malformed '+name+' plan never resumes the native runtime',async()=>{
    const g=boot({plan:mutate});await g.start();assert.equal(g.c.__CSV_TAS.status,'failed');assert.equal(g.rt.suspended,true);
    assert.equal(g.inputs.filter(row=>row.driving).length,0);
});

test('changed paused boundary invalidates a delayed response',async()=>{
    const g=boot({deferred:true});const promise=g.start();g.heart.x++;g.resolveFetch();await promise;
    assert.equal(g.c.__CSV_TAS.status,'failed');assert.match(g.c.__CSV_TAS.error,/boundary changed/);
});

for(const [field,value] of [['SimulatorMode',0],['SingleAttack','sans_intro']])
test('changing only paused '+field+' invalidates a delayed response',async()=>{
    const g=boot({deferred:true});const promise=g.start();
    const before=JSON.parse(JSON.stringify(g.c.NoHitSolverState.capturePhysical(g.rt)));
    g.rt.all_global_vars.find(variable=>variable.name===field).data=value;
    const after=JSON.parse(JSON.stringify(g.c.NoHitSolverState.capturePhysical(g.rt)));
    assert.notEqual(after[field],before[field]);delete before[field];delete after[field];
    assert.deepEqual(after,before);
    g.resolveFetch();await promise;
    assert.equal(g.c.__CSV_TAS.status,'failed');assert.match(g.c.__CSV_TAS.error,/boundary changed/);
    assert.equal(g.rt.suspended,true);assert.equal(g.keys.some(Boolean),false);
    g.step();assert.equal(g.inputs.filter(row=>row.driving).length,0);
});

for(const [field,value] of [['SimulatorMode',0],['SingleAttack','sans_intro']])
test('changing only paused '+field+' rejects an unknown retry before another request',async()=>{
    const g=boot({plan:plan=>{plan.status='unknown';plan.verified=false;plan.reason='wall_budget';}});
    await g.start();const tick=g.rt.tickcount;
    assert.equal(g.c.__CSV_TAS.status,'unknown');
    g.rt.all_global_vars.find(variable=>variable.name===field).data=value;
    assert.throws(()=>g.c.__CSV_TAS.retry({seconds:60}),/unchanged paused CSV boundary/);
    assert.equal(g.requests.length,1);assert.equal(g.rt.suspended,true);
    assert.equal(g.c.__CSV_TAS.status,'unknown');assert.equal(g.keys.some(Boolean),false);
    g.step();assert.equal(g.rt.tickcount,tick);
});

for(const [name,mutate] of [
    ['target',g=>g.zone.instance_vars[0]+=1],
    ['size',g=>g.zone.width+=1],
    ['speed',g=>g.rt.varsBySid[3111584688851152].data+=1],
    ['callback',g=>g.rt.varsBySid[1052618449272991].data='TLResume'],
])test('changing only paused arena '+name+' invalidates a delayed response',async()=>{
    const g=boot({deferred:true});const promise=g.start();
    const frozen=JSON.stringify(g.c.NoHitSolverState.capture(g.rt));
    mutate(g);
    assert.equal(JSON.stringify(g.c.NoHitSolverState.capture(g.rt)),frozen);
    g.resolveFetch();await promise;
    assert.equal(g.c.__CSV_TAS.status,'failed');assert.match(g.c.__CSV_TAS.error,/boundary changed/);
    assert.equal(g.rt.suspended,true);assert.equal(g.inputs.filter(row=>row.driving).length,0);
    assert.equal(g.keys.some(Boolean),false);
});

for(const previous of [false,true])test('changed candidate previous Confirm '+previous+' is rejected',async()=>{
    const g=boot({plan:plan=>plan.previous_confirm=!previous});g.pad[4]=Number(previous);
    await g.start();
    assert.equal(g.c.__CSV_TAS.boundary.previous_confirm,previous);
    assert.equal(g.c.__CSV_TAS.status,'failed');assert.match(g.c.__CSV_TAS.error,/previous Confirm mismatch/);
    assert.equal(g.rt.suspended,true);assert.equal(g.inputs.filter(row=>row.driving).length,0);
});

test('a candidate missing previous Confirm is rejected',async()=>{
    const g=boot({plan:plan=>delete plan.previous_confirm});await g.start();
    assert.equal(g.c.__CSV_TAS.status,'failed');assert.match(g.c.__CSV_TAS.error,/previous Confirm mismatch/);
    assert.equal(g.rt.suspended,true);assert.equal(g.inputs.filter(row=>row.driving).length,0);
});

test('cancel invalidates in-flight response and clears both Confirm aliases',async()=>{
    const g=boot({deferred:true});const promise=g.start();g.keys[90]=g.keys[13]=true;g.c.__CSV_TAS.cancel();g.resolveFetch();await promise;
    assert.equal(g.c.__CSV_TAS.status,'cancelled');assert.equal(g.keys.some(Boolean),false);assert.equal(g.rt.suspended,true);
});

for(const [name,options,reason] of [
    ['dt',{afterInput:({rt})=>rt.dt=1/60},/dt differs/],
    ['sampled input',{afterInput:({pad})=>pad[5]=1},/sampled input/],
    ['tick gap',{afterInput:({rt})=>rt.tickcount++},/skipped or repeated/],
    ['player drift',{afterInput:({heart})=>heart.y+=1},/player differs/],
    ['early EndAttack',{endAt:1},/before the expected/],
    ['restored damage',{afterInput:({rt,emit})=>{rt.all_global_vars[0].data=91;emit('damageplayer',1);rt.all_global_vars[0].data=92;}},/HP\/KR or DamagePlayer/],
])test(name+' fails permanently at the first native step',async()=>{
    const g=boot(options);await g.start();g.step();assert.equal(g.c.__CSV_TAS.status,'failed');assert.match(g.c.__CSV_TAS.error,reason);
    const tick=g.rt.tickcount;g.step();assert.equal(g.rt.tickcount,tick);assert.equal(g.rt.suspended,true);
});

test('plan exhaustion without EndAttack stops before any neutral extra tick',async()=>{
    const g=boot({noEnd:true});await g.start();g.step();g.step();assert.equal(g.c.__CSV_TAS.status,'failed');
    assert.match(g.c.__CSV_TAS.error,/without native EndAttack/);assert.equal(g.inputs.filter(row=>row.driving).length,2);
});

test('native-clamped 30Hz scheduler keeps exact dt through catch-up and solve pause',async()=>{
    const g=boot();g.emit('tlplay',g.source.text);g.rt.work=()=>g.rt.varsBySid[2569112556112449].data=2;
    g.frame(0);g.frame(100);await g.c.__CSV_TAS.solvePromise;
    assert.equal(g.rt.tickcount,101);g.frame(10000);g.frame(10000+1000/30);
    assert.equal(g.c.__CSV_TAS.status,'completed');assert.equal(g.rt.tickcount,103);
    assert(g.inputs.every(row=>row.dt===1/30));assert.equal(g.c.__TAS_CLOCK.stats.logicalSteps,3);
    assert.equal(g.c.__TAS_CLOCK.clock.stepMs,1000/30);assert.equal(g.c.__TAS_CLOCK.logicalStepMs,1000/30+1e-6);
});

test('60Hz native timestamp schedule remains nonuniform and continuous across a solve pause',async()=>{
    const text='0,HeartMode,0\n0,HeartTeleport,320,304\n0.016666666666666666,HeartMode,0\n0.05,HeartMode,0\n0.016666666666666666,EndAttack\n';
    const g=boot({query:'&fps=60',startTimestamp:0,deferred:true,text,
        actions:[2,4,1,8,0],confirms:[false,true,false,true,false]});
    const promise=g.start(),timestamp=g.rt.last_tick_time,tick=g.rt.tickcount;
    assert.equal(g.c.__TAS_CLOCK.mode,'fixed-native-timestamps');
    assert.equal(g.c.__TAS_CLOCK.physicsHz,60);
    assert.equal(g.c.__TAS_CLOCK.logicalStepMs,1000/60);
    assert.equal(g.rt.suspended,true);g.frame(10000);
    assert.equal(g.rt.tickcount,tick);assert.equal(g.rt.last_tick_time,timestamp);
    g.resolveFetch();await promise;
    assert.equal(g.c.__CSV_TAS.status,'playing');assert.equal(g.rt.last_tick_time,timestamp);
    const body=g.requests[0].body;
    assert.equal(body.custom_csv,text);assert.equal(body.fps,60);assert.equal(body.max_ticks,40000);
    assert.equal(body.dt_schedule.length,40000);assert.equal(body.dt_schedule[0],g.c.__CSV_TAS.boundary.dt);
    assert.equal(g.c.__CSV_TAS.plan.physics_hz,null);assert.equal(g.c.__CSV_TAS.plan.control_hz,null);
    g.frame(20000);g.frame(20000+5*1000/60);
    assert.equal(g.c.__CSV_TAS.status,'completed');assert.equal(g.rt.tickcount,tick+5);
    const observed=g.inputs.map(row=>row.dt);
    assert.equal(observed.length,6);assert(new Set(observed).size>1);
    assert(observed.some(dt=>dt!==1/60));
    assert.deepEqual(observed,body.dt_schedule.slice(0,6));
    assert.deepEqual(observed,Array.from(g.c.__CSV_TAS.plan.dt_sequence));
    assert.deepEqual(g.inputs.filter(row=>row.driving).map(row=>[row.mask,row.confirm]),
        [[2,false],[4,true],[1,false],[8,true],[0,false]]);
});

test('60Hz candidates rounded to uniform 1/60 are rejected before playback',async()=>{
    const g=boot({query:'&fps=60',startTimestamp:0,plan:plan=>plan.dt_sequence.fill(1/60)});
    await g.start();
    assert.equal(g.c.__CSV_TAS.status,'failed');assert.equal(g.rt.suspended,true);
    assert.equal(g.inputs.filter(row=>row.driving).length,0);
});

test('60Hz native input ticks still require exact dt rather than nominal fps',async()=>{
    const g=boot({query:'&fps=60',startTimestamp:0,actions:[2,4,1],confirms:[false,false,false],
        afterInput:({rt,index})=>{if(index===1)rt.dt=1/60;}});
    await g.start();g.step();assert.equal(g.c.__CSV_TAS.status,'playing');
    g.step();assert.equal(g.c.__CSV_TAS.status,'failed');assert.match(g.c.__CSV_TAS.error,/dt differs/);
    const stopped=g.rt.tickcount;g.step();assert.equal(g.rt.tickcount,stopped);assert.equal(g.rt.suspended,true);
});

test('an explicit 60Hz maximum tick count bounds the requested native schedule',async()=>{
    const g=boot({query:'&fps=60&max_ticks=7',startTimestamp:0});await g.start();
    assert.equal(g.c.__CSV_TAS.status,'playing');
    assert.equal(g.requests[0].body.max_ticks,7);assert.equal(g.requests[0].body.dt_schedule.length,7);
});

test('shared round exports the complete fresh request and exact future clock recipe',async()=>{
    const g=boot({query:'&fps=60&max_ticks=7',startTimestamp:0});await g.start();
    const state=g.c.__CSV_TAS,request=g.requests[0].body,recipe=state.request_recipe;
    assert.equal(state.version,1); // Preserve the standalone native evidence schema.
    assert.deepEqual(JSON.parse(JSON.stringify(state.request)),request);
    assert.equal(state.request_generation,1);assert.equal(state.fresh_computation,true);
    assert.match(request.request_id,/^[0-9a-f-]{36}$/);
    assert.equal(recipe.schedule_count,7);assert.equal(recipe.max_ticks,7);
    assert.equal(recipe.clock_start_ms,state.boundary.clock_start_ms);
    assert.equal(recipe.initial_dt,state.boundary.dt);assert.equal(recipe.logical_step_ms,1000/60);
    const expected=createHash('sha256').update(Buffer.from(new Float64Array(request.dt_schedule).buffer)).digest('hex');
    assert.equal(recipe.schedule_sha256,expected);
    assert.equal(state.source_sha256,g.source.sha256);assert.equal(state.source_text,g.source.text);
    g.step();g.step();assert.equal(state.status,'completed');
    assert.equal(state.endSnapshot.tick,state.boundary.tick+2);
    assert.equal(state.endSnapshot.dt,state.plan.dt_sequence[2]);
});

test('page visibility cannot resume a stopped campaign or CSV round',()=>{
    const html=fs.readFileSync(new URL('../c2-sans-fight/index.html',import.meta.url),'utf8');
    const body=html.match(/function onVisibilityChanged\(\) \{([\s\S]*?)\n\s*\};/)[1];
    for(const owner of ['__CAMPAIGN','__CSV_TAS']) {
        const calls=[],context={window:{[owner]:{canAdvance:()=>false}},document:{hidden:false},cr_setSuspended:value=>calls.push(value)};
        vm.runInNewContext('(function(){'+body+'})()',context);
        assert.deepEqual(calls,[true]);
    }
    const calls=[];
    vm.runInNewContext('(function(){'+body+'})()',{
        window:{__CAMPAIGN:{canAdvance:()=>true}},document:{hidden:false},cr_setSuspended:value=>calls.push(value)});
    assert.deepEqual(calls,[false]);
});

test('campaign ownership conflict is rejected before the source can run',()=>{
    const g=boot({query:'&campaign=1'});assert.equal(g.c.__CSV_TAS.status,'failed');assert.equal(g.rt.suspended,true);
    assert.match(g.c.__CSV_TAS.error,/cannot share control/);
});

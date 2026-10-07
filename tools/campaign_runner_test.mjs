// Production Normal shell and shared round core; native acceptance is separate.
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import {createHash,webcrypto} from 'node:crypto';

function boot(options={}) {
    const keys=Array(256).fill(false),pad=Array(14).fill(0),requests=[],inputs=[],queued=[];
    const heart={x:320,y:304,angle:Math.PI/2,instance_vars:[0,0,0],behavior_insts:[{type:{name:'CustomMovement'},dx:0,dy:0}]};
    const zone={bbox:{left:133,top:251,right:508,bottom:391},width:375,height:140,
        instance_vars:[133,251,508,391,''],update_bbox(){}};
    let c,resolveFetch;
    const gate=options.deferred?new Promise(resolve=>resolveFetch=resolve):Promise.resolve();
    class Runtime {
        trigger(method,inst,fn) {
            if(fn==='tlplay') {this.varsBySid[2569112556112449].data=1;this.varsBySid[3521916820909801].data=0;}
        }
        tick(background,stamp) {
            this.dt=Math.min((stamp-this.last_tick_time)/1000,1/30);this.last_tick_time=stamp;
            for(let i=0;i<7;i++)pad[i+7]=pad[i];
            Object.assign(pad,{0:Number(!!keys[38]),1:Number(!!keys[40]),2:Number(!!keys[37]),3:Number(!!keys[39]),
                4:Number(!!(keys[90]||keys[13])),5:Number(!!(keys[88]||keys[16])),6:0});
            const driving=c.__CAMPAIGN?.status==='playing',index=c.__CAMPAIGN?.round?.actionsApplied;
            inputs.push({mask:pad[2]|pad[3]<<1|pad[0]<<2|pad[1]<<3|pad[5]<<4,confirm:!!pad[4],driving,dt:this.dt});
            if(driving) {
                heart.x+=1;
                if(index+1===(options.endAt??4)&&!options.noEnd)emit('endattack');
                options.afterInput?.({c,rt:this,heart,pad,index,emit});
            }
            this.work?.();this.work=null;this.kahanTime.sum+=this.dt;this.tickcount++;
        }
    }
    const rt=new Runtime(),stamp=2000000,dt=((stamp+1000/240)-stamp)/1000;
    Object.assign(rt,{tickcount:100,last_tick_time:stamp,dt,kahanTime:{sum:5},running_layout:{},suspended:false,
        types_by_index:[{sid:5960708907117077,instances:[heart]},{sid:141231765387603,instances:[zone]},
            {sid:9768267065126338,instances:[{instance_vars:pad}]}],
        all_global_vars:[{name:'HP',data:92},{name:'KR',data:0},{name:'SimulatorMode',data:0},{name:'SingleAttack',data:''}],
        varsBySid:{963626393445968:{data:750},3521916820909801:{data:0},164016619418963:{data:1},2569112556112449:{data:1},
            3111584688851152:{data:30},1052618449272991:{data:''}}});
    c={console,URL,URLSearchParams,TextEncoder,Uint8Array,Float64Array,DataView,crypto:webcrypto,AbortController,
        queueMicrotask:options.deferRetries?callback=>queued.push(callback):queueMicrotask,
        location:{search:'?campaign=1&compensate=1&seed=42&max_ticks=20'+(options.query||'')},
        document:{getElementById:id=>id==='c2canvas'?{c2runtime:rt}:null},c2runtime:rt,
        cr:{runtime:Runtime,plugins_:{Function:{prototype:{cnds:{OnFunction(){}}}}}},
        __TAS_CLOCK:{enabled:true,stepping:true,mode:'fixed-240hz-realtime-catchup',physicsHz:240,logicalStepMs:1000/240},
        __FULL_GAME:{done:false},TASRunner:{getKeyboardInstance:()=>({keyMap:keys}),releaseAllKeys:()=>keys.fill(false)},
        NoHitMenuController:{step(){c.menuCalls++;return options.menu||{keymask:16,confirm:true};}},menuCalls:0,
        cr_setSuspended(value){rt.suspended=value;},
        fetch:async(url,request)=>{
            const body=JSON.parse(request.body);requests.push({url,body});await gate;
            const boundary=c.__CAMPAIGN.round.boundary,actions=[2,4,1,0],confirm_sequence=[true,true,false,true];
            const plan={status:'candidate_found',verified:true,planner:'bounded-frontier-with-dialogue',
                csv_sha256:createHash('sha256').update(body.custom_csv).digest('hex'),actions,confirm_sequence,
                trajectory:[boundary.initial,...actions.map((mask,i)=>{const row=boundary.initial.slice();row[0]+=i+1;row[4]=mask;return row;})],
                initial_confirm:boundary.initial_confirm,previous_confirm:boundary.previous_confirm,
                initial_arena:body.initial_arena,target_history:body.initial_target_history,
                control_ticks:1,clock_protocol:'explicit_dt_schedule',dt_sequence:body.dt_schedule.slice(0,5),
                clock:{schedule_count:body.dt_schedule.length,
                    schedule_sha256:createHash('sha256').update(Buffer.from(new Float64Array(body.dt_schedule).buffer)).digest('hex')},
                visualization:{frames:[{env:boundary.initial_environment.slice()}]},
                provenance:{request_id:body.request_id,fresh_computation:true,route_cache_hit:false,implementation_sha256:{}}};
            options.reply?.(plan,body,requests.length);
            return {ok:true,json:async()=>plan};
        }};
    c.window=c;vm.createContext(c);
    for(const name of ['solver_state','csv_round_controller','full_game_runner'])
        vm.runInContext(fs.readFileSync(new URL('../c2-sans-fight/'+name+'.js',import.meta.url),'utf8'),c);
    function emit(fn,value='',second=0) {rt.trigger(c.cr.plugins_.Function.prototype.cnds.OnFunction,{exps:{Param(result,i){result.set_any(i?second:value);}}},fn);}
    function step(work) {rt.work=work;rt.tick(true,rt.last_tick_time+1000/240,true);}
    function start(name='sans_intro',text='0,SansText,a,\n0,EndAttack\n',work=null) {
        emit('runattack',name);emit('tlplay',text);
        step(()=>{rt.varsBySid[2569112556112449].data=3;rt.varsBySid[164016619418963].data=0;work?.();});
        return c.__CAMPAIGN.solvePromise;
    }
    return {c,rt,keys,pad,heart,zone,requests,inputs,queued,step,emit,start,resolveFetch};
}

async function settleSolves(g) {
    let current;
    do {
        current=g.c.__CAMPAIGN.solvePromise;await current;await Promise.resolve();
    } while(current!==g.c.__CAMPAIGN.solvePromise);
}

test('Intro paused source frame0 is captured and both inputs are replayed until last EndAttack',async()=>{
    const g=boot();await g.start();
    assert.equal(g.c.__CAMPAIGN.status,'playing',g.c.__CAMPAIGN.error);assert.equal(g.requests[0].url,'/api/solve-csv');
    assert.equal(g.c.__CAMPAIGN.boundary.captured.running,0);assert.equal(g.c.__CAMPAIGN.boundary.captured.timeline,0);
    assert.equal(g.c.__CAMPAIGN.round.actionsApplied,0);assert.equal(g.c.menuCalls,0);
    for(let i=0;i<4;i++)g.step();
    assert.equal(g.c.__CAMPAIGN.status,'waiting');assert.equal(g.rt.suspended,false);
    assert.deepEqual(g.inputs.filter(row=>row.driving).map(row=>[row.mask,row.confirm]),[[2,true],[4,true],[1,false],[0,true]]);
    assert.equal(g.c.menuCalls,0);g.step();assert.equal(g.c.menuCalls,1);
    assert.equal(g.inputs.at(-1).mask,16);assert.equal(g.inputs.at(-1).confirm,true);
    await g.start('sans_bonegap1','0,HeartMode,0\n1,EndAttack\n');
    assert.equal(g.requests.length,2);assert.equal(g.c.__CAMPAIGN.plans.length,2);
    assert.equal(g.c.__CAMPAIGN.round.actionsApplied,0);
    assert.notEqual(g.requests[0].body.request_id,g.requests[1].body.request_id);
});

test('TLPlay-only ticks wait, while RunAttack and frame0 in one native tick are captured',async()=>{
    const g=boot();g.emit('runattack','sans_intro');g.emit('tlplay','0,SansText,a,\n0,EndAttack\n');
    g.step();assert.equal(g.c.__CAMPAIGN.boundary,null);assert.equal(g.requests.length,0);
    g.step(()=>{g.rt.varsBySid[2569112556112449].data=3;g.rt.varsBySid[164016619418963].data=0;});
    await g.c.__CAMPAIGN.solvePromise;assert.equal(g.c.__CAMPAIGN.status,'playing');
    const h=boot();h.step(()=>{h.emit('runattack','sans_intro');h.emit('tlplay','0,EndAttack\n');h.rt.varsBySid[2569112556112449].data=2;});
    await h.c.__CAMPAIGN.solvePromise;assert.equal(h.c.__CAMPAIGN.boundary.captured.tick,101);
});

test('pre-source arena and early GetHeartPos remain separate from post-frame0 player',async()=>{
    const g=boot();await g.start('sans_intro','0,GetHeartPos,x,y\n0,EndAttack\n',()=>{
        g.rt.varsBySid[2569112556112449].data=1;g.emit('getheartpos','x','y');
        g.heart.x=321;g.zone.bbox.left=134;g.zone.width=374;g.rt.varsBySid[2569112556112449].data=3;
    });
    assert.equal(g.requests[0].body.initial_environment[0],133);assert.equal(g.requests[0].body.initial[0],321);
    assert.equal(g.requests[0].body.initial_arena.size[0],375);
    assert.deepEqual(g.requests[0].body.initial_target_history,[[0,1,320,304]]);
    assert.equal(g.c.__CAMPAIGN.status,'playing',g.c.__CAMPAIGN.error);
});

for(const [name,opts] of [
    ['early EndAttack',{endAt:2}],['missing EndAttack',{noEnd:true}],
    ['native player mismatch',{afterInput:({heart,index})=>{if(index===0)heart.y++;}}],
    ['native damage',{afterInput:({rt,index})=>{if(index===0)rt.all_global_vars[0].data--;}}],
    ['wrong previous Confirm',{reply:p=>p.previous_confirm=!p.previous_confirm}],
    ['wrong exact dt',{reply:p=>p.dt_sequence[1]+=1e-18}],
    ['wrong fresh request',{reply:p=>p.provenance.request_id='stale'}],
])test(name+' stops, releases aliases and cannot give menu control',async()=>{
    const g=boot(opts);await g.start();for(let i=0;i<5;i++)g.step();
    assert.equal(g.rt.suspended,true);assert.equal(g.c.__CAMPAIGN.canAdvance(),false);
    assert.equal(g.c.menuCalls,0);assert.equal(g.keys.some(Boolean),false);
    const expected={
        'early EndAttack':/before the expected final input/,'missing EndAttack':/without native EndAttack/,
        'native player mismatch':/player differs/,'native damage':/HP\/KR/,
        'wrong previous Confirm':/previous Confirm/,'wrong exact dt':/Candidate dt/,
        'wrong fresh request':/provenance/,
    };
    assert.match(g.c.__CAMPAIGN.error,expected[name]);
});

test('unknown can retry only the unchanged same boundary with a new request identity',async()=>{
    const g=boot({reply:(p,b,n)=>{if(n===1){p.status='unknown';p.verified=false;p.reason='wall_budget';}}});
    await g.start();assert.equal(g.c.__CAMPAIGN.status,'unknown');assert.equal(g.rt.suspended,true);
    const tick=g.rt.tickcount;g.step();assert.equal(g.rt.tickcount,tick);
    assert.throws(()=>g.c.__CAMPAIGN.retry({initial:[1]}),/search settings/);
    await g.c.__CAMPAIGN.retry({width:100});assert.equal(g.c.__CAMPAIGN.status,'playing');
    assert.equal(g.requests[1].body.width,100);
    assert.deepEqual(g.requests[1].body.initial,g.requests[0].body.initial);
    assert.equal(g.c.__CAMPAIGN.plans.length,2);assert.notEqual(g.requests[0].body.request_id,g.requests[1].body.request_id);
});

test('manual retry settings apply only to the current round',async()=>{
    const g=boot({query:'&width=200',reply:(p,b,n)=>{if(n===1){p.status='unknown';p.verified=false;}}});
    await g.start();await g.c.__CAMPAIGN.retry({width:1000,seconds:60});
    for(let i=0;i<4;i++)g.step();
    await g.start('sans_bonegap1');
    assert.deepEqual(g.requests.map(r=>r.body.width),[200,1000,200]);
    assert.deepEqual(g.requests.map(r=>r.body.seconds),[30,60,30]);
    assert.equal(g.c.__CAMPAIGN.status,'playing');
});

test('configured widths automatically retry unknown on the same boundary and retain every attempt',async()=>{
    const g=boot({query:'&width=200&retry_widths=1000,3000',
        reply:(p,b,n)=>{if(n===1){p.status='unknown';p.verified=false;p.reason='wall_budget';}}});
    await g.start();await settleSolves(g);
    assert.equal(g.c.__CAMPAIGN.status,'playing',g.c.__CAMPAIGN.error||'automatic retry should find the second candidate');
    assert.deepEqual(g.requests.map(r=>r.body.width),[200,1000]);
    const plans=Array.from(g.c.__CAMPAIGN.plans);
    assert.deepEqual(plans.map(p=>p.plan.status),['unknown','candidate_found']);
    assert.deepEqual(plans.map(p=>p.request_generation),[1,2]);
    assert.equal(new Set(g.requests.map(r=>r.body.request_id)).size,2);
    assert.deepEqual(plans[0].captured,plans[1].captured);
    const [first,second]=g.requests.map(r=>({...r.body}));
    delete first.width;delete second.width;delete first.request_id;delete second.request_id;
    assert.deepEqual(first,second);assert.equal(g.rt.tickcount,101);
    for(let i=0;i<4;i++)g.step();
    assert.equal(g.c.__CAMPAIGN.status,'waiting');
    assert.equal(plans[1].actionsApplied,4);
    await g.start('sans_bonegap1');await settleSolves(g);
    assert.deepEqual(g.requests.map(r=>r.body.width),[200,1000,200]);
});

for(const [name,mutate] of [
    ['failed response',p=>{p.status='failed';p.verified=false;p.reason='unsupported';}],
    ['unverified candidate',p=>{p.verified=false;}],
    ['unknown claiming verification',p=>{p.status='unknown';}],
])test(name+' cannot trigger an automatic retry',async()=>{
    const g=boot({query:'&retry_widths=1000,3000',reply:mutate});
    await g.start();await settleSolves(g);
    assert.equal(g.requests.length,1);assert.equal(g.c.__CAMPAIGN.status,'failed');
    assert.equal(g.rt.suspended,true);assert.equal(g.keys.some(Boolean),false);
});

test('DamagePlayer during a paused solve prevents an unknown response from being retried',async()=>{
    const g=boot({query:'&retry_widths=1000,3000',reply:p=>{
        g.emit('damageplayer',1);p.status='unknown';p.verified=false;
    }});
    await g.start();await settleSolves(g);
    assert.equal(g.requests.length,1);assert.equal(g.c.__CAMPAIGN.status,'failed');
    assert.equal(g.rt.suspended,true);assert.equal(g.keys.some(Boolean),false);
});

test('automatic retries deduplicate widths, exhaust in order and stay paused on unknown',async()=>{
    const g=boot({query:'&width=200&retry_widths=1000,1000,3000',reply:p=>{
        p.status='unknown';p.verified=false;p.reason='frontier_exhausted';
    }});
    await g.start();await settleSolves(g);
    assert.deepEqual(g.requests.map(r=>r.body.width),[200,1000,3000]);
    assert.deepEqual(Array.from(g.c.__CAMPAIGN.plans,p=>p.request_generation),[1,2,3]);
    assert.equal(g.c.__CAMPAIGN.status,'unknown');assert.equal(g.c.__CAMPAIGN.error,null);
    assert.equal(g.rt.suspended,true);assert.equal(g.keys.some(Boolean),false);
    g.step();assert.equal(g.rt.tickcount,101);assert.equal(g.requests.length,3);
});

test('each new round starts from the original width and gets its own automatic retry sequence',async()=>{
    const g=boot({query:'&width=200&retry_widths=1000',reply:(p,b)=>{
        if(b.width===200){p.status='unknown';p.verified=false;}
    }});
    await g.start();await settleSolves(g);for(let i=0;i<4;i++)g.step();
    await g.start('sans_bonegap1');await settleSolves(g);
    assert.equal(g.c.__CAMPAIGN.status,'playing');
    assert.deepEqual(g.requests.map(r=>r.body.width),[200,1000,200,1000]);
    assert.deepEqual(Array.from(g.c.__CAMPAIGN.plans,p=>[p.round,p.request_generation]),[[0,1],[0,2],[1,1],[1,2]]);
});

for(const [name,stop] of [
    ['cancel',g=>g.c.__CAMPAIGN.cancel()],
    ['observer completion',g=>{g.c.__FULL_GAME.done=true;}],
    ['observer damage',g=>{g.c.__FULL_GAME.firstDamage={tick:g.rt.tickcount};}],
])test(name+' blocks a queued automatic retry',async()=>{
    const g=boot({query:'&retry_widths=1000',deferRetries:true,reply:p=>{p.status='unknown';p.verified=false;}});
    await g.start();assert.equal(g.queued.length,1);
    stop(g);g.queued.shift()();await settleSolves(g);
    assert.equal(g.requests.length,1);assert.equal(g.c.__CAMPAIGN.plans.length,1);
    assert.equal(g.rt.suspended,true);assert.equal(g.keys.some(Boolean),false);
    g.step();assert.equal(g.rt.tickcount,101);
});

test('a changed native boundary blocks a queued retry before any new request',async()=>{
    const g=boot({query:'&retry_widths=1000',deferRetries:true,reply:p=>{p.status='unknown';p.verified=false;}});
    await g.start();g.heart.x++;g.queued.shift()();await settleSolves(g);
    assert.equal(g.requests.length,1);assert.equal(g.c.__CAMPAIGN.status,'stopped');
    assert.match(g.c.__CAMPAIGN.error,/unchanged paused CSV boundary/);
    assert.equal(g.rt.suspended,true);
});

test('a manual retry supersedes an already queued automatic attempt',async()=>{
    const g=boot({query:'&width=200&retry_widths=1000',deferRetries:true,
        reply:(p,b,n)=>{if(n===1){p.status='unknown';p.verified=false;}}});
    await g.start();await g.c.__CAMPAIGN.retry({width:500});
    g.queued.shift()();await settleSolves(g);
    assert.equal(g.c.__CAMPAIGN.status,'playing');
    assert.deepEqual(g.requests.map(r=>r.body.width),[200,500]);
});

test('a malformed candidate on an automatic retry stops before later widths',async()=>{
    const g=boot({query:'&retry_widths=1000,3000',reply:(p,b,n)=>{
        if(n===1){p.status='unknown';p.verified=false;}else p.dt_sequence[1]=1/30;
    }});
    await g.start();await settleSolves(g);
    assert.equal(g.c.__CAMPAIGN.status,'failed');assert.equal(g.requests.length,2);
    assert.equal(g.rt.suspended,true);
});

test('native playback damage never starts a configured retry',async()=>{
    const g=boot({query:'&retry_widths=1000,3000',afterInput:({emit})=>emit('damageplayer',1)});
    await g.start();g.step();await settleSolves(g);
    assert.equal(g.c.__CAMPAIGN.status,'failed');assert.equal(g.requests.length,1);
    assert.equal(g.rt.suspended,true);assert.equal(g.keys.some(Boolean),false);
});

for(const value of ['', '0', '-1', '1.5', '1e3', '+1', '1000,', '1000, 3000', 'NaN', '9007199254740992'])
test('invalid retry_widths '+JSON.stringify(value)+' is rejected before play',()=>{
    const g=boot({query:'&retry_widths='+encodeURIComponent(value)});
    assert.equal(g.c.__CAMPAIGN.status,'stopped');assert.match(g.c.__CAMPAIGN.error,/retry_widths/);
    assert.equal(g.rt.suspended,true);assert.equal(g.requests.length,0);
});

test('cancellation rejects a late response',async()=>{
    const g=boot({deferred:true});const promise=g.start();
    await new Promise(resolve=>setTimeout(resolve,10));g.c.__CAMPAIGN.cancel();g.resolveFetch();await promise;
    assert.equal(g.c.__CAMPAIGN.status,'cancelled');assert.equal(g.c.__CAMPAIGN.plans.length,0);
    const tick=g.rt.tickcount;g.step();assert.equal(g.rt.tickcount,tick);
});

test('menu failure and independent observer completion stop physical advance',()=>{
    const g=boot({menu:{blocked:true,reason:'unsafe'}});g.step();assert.equal(g.c.__CAMPAIGN.status,'stopped');
    assert.equal(g.rt.tickcount,100);
    const h=boot();h.c.__FULL_GAME.done=true;h.step();assert.equal(h.rt.tickcount,100);
});

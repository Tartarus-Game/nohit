import {test} from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import {createHash,webcrypto} from 'node:crypto';

const source=fs.readFileSync(new URL('../c2-sans-fight/full_game_acceptance.js',import.meta.url),'utf8');
const names=['intro','bonegap1','bluebone','bonegap2','platforms1','platforms2','platforms3','platforms4',
    'platformblaster','platforms4hard','bonegap1fast','boneslideh','bonegap2','spare','multi1','randomblaster1',
    'multi2','bonestab1','bonestab2','randomblaster2','boneslidev','multi3','bonestab3','final'];
function boot(options={}){
    class Runtime{tick(){const next=this.last_tick_time+1000/240;
        this.dt=this.forcedDt??Math.min((next-this.last_tick_time)/1000,1/30);this.last_tick_time=next;
        this.work?.();this.work=null;this.tickcount++;}trigger(){}}
    const rt=new Runtime(),pad={instance_vars:Array(14).fill(0)},legs={instance_vars:[0,0,0,0,0,0]};
    const heart={x:320,y:320,angle:0,instance_vars:[0,0,0],behavior_insts:[{type:{name:'CustomMovement'},dx:0,dy:0}]};
    const zone={bbox:{left:32,top:240,right:608,bottom:384},width:576,height:144,
        instance_vars:[33,251,608,391],update_bbox(){}};
    Object.assign(rt,{tickcount:0,kahanTime:{sum:0},dt:1/240,last_tick_time:0,
        all_global_vars:[{name:'SimulatorMode',data:0},{name:'HP',data:92},{name:'KR',data:0}],
        types_by_index:[{sid:5960708907117077,instances:[heart]},{sid:9590658027348857,instances:[legs]},
            {sid:9768267065126338,instances:[pad]},{sid:141231765387603,instances:[zone]}],
        varsBySid:{3521916820909801:{data:0},164016619418963:{data:0},2569112556112449:{data:1},
            963626393445968:{data:750},3111584688851152:{data:480},1052618449272991:{data:''}}});
    const requests=[];
    const c={URLSearchParams,TextEncoder,Uint8Array,crypto:webcrypto,btoa:s=>Buffer.from(s,'binary').toString('base64'),
        location:{search:'?campaign=1&mode=normal&compensate=1'},
        document:{createElement(){return {};},body:{appendChild(){}},getElementById(){return {c2runtime:rt};}},
        cr:{runtime:Runtime,plugins_:{Function:{prototype:{cnds:{OnFunction(){}}}}}},
        __TAS_CLOCK:{enabled:true,stepping:true,mode:'fixed-240hz-realtime-catchup',physicsHz:240,logicalStepMs:1000/240},
        __TAS_SEED:{seed:42},__CAMPAIGN:{plans:[]},TASRunner:{releaseAllKeys(){}},
        cr_setSuspended(v){rt.suspended=v;},fetch:async(url,request)=>{requests.push({url,...request});
            if(url==='/api/acceptance-evidence'){
                const body=JSON.parse(request.body),raw=Buffer.from(body.data,'base64');
                assert.equal(createHash('sha256').update(raw).digest('hex'),body.sha256);
                return {ok:!options.partError,json:async()=>({path:'campaign-evidence/'+body.sha256+'.bin',
                    sha256:body.sha256,byte_count:raw.length})};
            }
            return {ok:true,json:async()=>({trace:'fixture'})};}};
    c.window=c;vm.createContext(c);vm.runInContext(source,c);
    const emit=(fn,param='',second=0)=>rt.trigger(c.cr.plugins_.Function.prototype.cnds.OnFunction,
        {exps:{Param(ret,index){ret.set_any(index?second:param);}}},fn);
    const step=fn=>{rt.work=fn;rt.tick();};
    const begin=(i=0)=>step(()=>{legs.instance_vars[1]=i;emit('startattack');emit('runattack','sans_'+names[i]);});
    const complete=()=>{
        for(let i=0;i<24;i++){begin(i);step(()=>emit('endattack'));}
        step(()=>emit('win1'));step();step();step(()=>emit('win2'));
    };
    return {c,rt,pad,legs,heart,zone,requests,emit,step,begin,complete};
}

test('real observer requires all 24 rounds and allows dialogue ticks between Win1 and Win2',async()=>{
    const b=boot();b.complete();await b.c.__FULL_GAME.recordPromise;
    const a=b.c.__FULL_GAME;
    assert.equal(a.status,'passed');assert.equal(a.rounds.length,24);
    assert.equal(a.tickEvidence.length,a.checkedTicks);
    assert.equal(a.tickEvidence[0][3],0);assert.equal(a.tickEvidence.at(-1)[3],23);
    assert.equal(a.rows.at(-1).tick,a.win2Snapshot.tick+1);
    assert.equal(b.requests.length,1);
});

test('a direct Win2 with zero original rounds permanently fails',()=>{
    const b=boot();b.step(()=>b.emit('win2'));
    assert.equal(b.c.__FULL_GAME.status,'failed_protocol');
});

test('Win2 may remove battle objects after its observed terminal snapshot',()=>{
    const b=boot();
    for(let i=0;i<24;i++){b.begin(i);b.step(()=>b.emit('endattack'));}
    b.step(()=>b.emit('win1'));
    b.step(()=>{b.emit('win2');b.rt.types_by_index=[];});
    assert.equal(b.c.__FULL_GAME.status,'passed');
    assert.equal(b.c.__FULL_GAME.rows.at(-1).HitAttemptsSource,'win2_event');
    assert.equal(b.c.__FULL_GAME.tickEvidence.at(-1)[3],23);
});

test('damage at the opening function boundary survives same-tick healing',()=>{
    const b=boot();
    b.step(()=>{b.rt.all_global_vars[1].data=91;b.emit('startattack');b.emit('runattack','sans_intro');b.rt.all_global_vars[1].data=92;});
    assert.equal(b.c.__FULL_GAME.status,'failed_damage');
    assert.equal(b.c.__FULL_GAME.firstDamage.source,'native_function_boundary');
});

test('changing SimulatorMode after a valid opening fails on that same tick',()=>{
    const b=boot();b.begin();b.step(()=>{b.rt.all_global_vars[0].data=2;});
    assert.equal(b.c.__FULL_GAME.status,'failed_protocol');
    assert.equal(b.c.__FULL_GAME.tickEvidence.at(-1)[4],2);
});

test('HP loss and a DamagePlayer call cannot be hidden by later healing',()=>{
    const b=boot();b.begin();b.step(()=>b.emit('damageplayer',1,10));
    assert.equal(b.c.__FULL_GAME.status,'failed_damage');
    b.step(()=>{b.rt.all_global_vars[1].data=92;b.emit('win2');});
    assert.equal(b.c.__FULL_GAME.status,'failed_damage');
});

test('VPad Cancel and Confirm are recorded separately in the per-tick evidence',()=>{
    const b=boot();b.pad.instance_vars[2]=1;b.pad.instance_vars[5]=1;b.pad.instance_vars[4]=1;b.begin();
    assert.equal(b.c.__FULL_GAME.tickEvidence[0][5],17);
    assert.equal(b.c.__FULL_GAME.tickEvidence[0][6],1);
});

test('a skipped native tick and an altered physics dt fail before victory',()=>{
    const b=boot();b.begin();b.rt.tickcount++;b.step();
    assert.equal(b.c.__FULL_GAME.status,'failed_clock');
    const c=boot();c.begin();c.rt.forcedDt=1/60;c.step();
    assert.equal(c.c.__FULL_GAME.status,'failed_clock');
});

test('160000 full native tick records survive lossless storage under each POST limit',async()=>{
    const b=boot();b.complete();await b.c.__FULL_GAME.recordPromise;b.requests.length=0;
    const a=b.c.__FULL_GAME;
    a.tickEvidence=Array.from({length:160000},(_,i)=>[i,92,0,23,0,31,1,0.00416666666666697,
        i*1000/240,0,[320.0000000000001,304.123456789,150,-150,31,0,1,3,750,0,0]]);
    a.checkedTicks=a.tickEvidence.length;
    await a.save();
    const manifest=JSON.parse(b.requests.at(-1).body);
    assert.equal(manifest.storage,'json-utf8-parts-v1');assert(a.payloadBytes>8000000);
    assert(b.requests.every(request=>new TextEncoder().encode(request.body).length<8000000));
    const partBodies=b.requests.slice(0,-1).map(request=>JSON.parse(request.body));
    assert.equal(partBodies.length,manifest.evidenceParts.length);
    const raw=Buffer.concat(partBodies.map(part=>Buffer.from(part.data,'base64')));
    assert.equal(raw.length,manifest.total_byte_count);
    assert.equal(createHash('sha256').update(raw).digest('hex'),manifest.total_sha256);
    const restored=JSON.parse(raw.toString('utf8'));
    assert.deepEqual(restored.tickEvidence,a.tickEvidence);
    assert.deepEqual(restored.events,JSON.parse(JSON.stringify(a.events)));
    assert.equal(restored.checkedTicks,160000);assert.equal(a.status,'passed');
});

test('a single oversized event is preserved across byte parts without trimming',async()=>{
    const b=boot();b.c.__FULL_GAME.events.push({fn:'test-padding',tick:0,param:'证'.repeat(2700000)});b.complete();
    await b.c.__FULL_GAME.recordPromise;
    assert.equal(b.c.__FULL_GAME.status,'passed');
    const bytes=Buffer.concat(b.requests.filter(r=>r.url==='/api/acceptance-evidence')
        .map(r=>Buffer.from(JSON.parse(r.body).data,'base64')));
    assert.equal(JSON.parse(bytes.toString('utf8')).events[0].param,'证'.repeat(2700000));
    assert(b.requests.every(request=>new TextEncoder().encode(request.body).length<8000000));
});

test('a failed evidence part upload never publishes a success manifest',async()=>{
    const b=boot({partError:true});b.c.__FULL_GAME.events.push({fn:'padding',param:'x'.repeat(8000000)});b.complete();
    await b.c.__FULL_GAME.recordPromise;
    assert.equal(b.c.__FULL_GAME.status,'failed_save');assert.equal(b.rt.suspended,true);
    assert(b.requests.every(request=>request.url==='/api/acceptance-evidence'));
});

test('source, target reads and committed boundary are observed independently of campaign plans',async()=>{
    const b=boot(),text='0,GetHeartPos,x,y\n0,HeartTeleport,321,320\n1,EndAttack\n';
    b.begin();b.emit('tlplay',text);b.step();
    assert.equal(b.c.__FULL_GAME.rounds.length,0);
    b.step(()=>{
        b.rt.varsBySid[2569112556112449].data=1;b.emit('getheartpos','x','y');
        b.heart.x=321;b.zone.bbox.left=33;b.rt.varsBySid[2569112556112449].data=3;
    });
    b.step(()=>b.emit('endattack'));await b.c.__FULL_GAME.save();
    const round=b.c.__FULL_GAME.rounds[0],event=b.c.__FULL_GAME.events.find(e=>e.fn==='getheartpos');
    assert.equal(round.source.text,text);assert.equal(round.source.sha256,createHash('sha256').update(text).digest('hex'));
    assert.equal(round.source.preSnapshot.initial_environment[0],32);assert.equal(round.source.preSnapshot.arena.target[0],33);
    assert.equal(round.boundary.tick,3);assert.equal(round.boundary.state[0],321);
    assert.deepEqual(Array.from(event.sampled_position),[320,320]);assert.equal(event.source_line,1);
    assert.equal(round.endSnapshot.tick,round.endTick+1);
});

test('nonuniform 240Hz native dt and complete player state are retained every tick',()=>{
    const b=boot();b.begin();for(let i=0;i<6;i++)b.step();
    const a=b.c.__FULL_GAME,field=name=>a.tickEvidenceFields.indexOf(name);
    assert.equal(a.evidenceVersion,3);assert.equal(a.status,'running');
    assert(new Set(a.tickEvidence.map(row=>row[field('dt')])).size>1);
    for(const row of a.tickEvidence){assert.equal(row[field('state')].length,11);assert(Number.isFinite(row[field('clock_start_ms')]))}
});

test('a one-ULP native dt error is preserved and fails the independent clock check',()=>{
    const b=boot();b.begin();
    const timestamp=b.rt.last_tick_time,next=timestamp+1000/240,expected=(next-timestamp)/1000;
    const bits=new DataView(new ArrayBuffer(8));bits.setFloat64(0,expected,true);
    bits.setBigUint64(0,bits.getBigUint64(0,true)+1n,true);b.rt.forcedDt=bits.getFloat64(0,true);
    b.step();assert.equal(b.c.__FULL_GAME.status,'failed_clock');
    assert.equal(b.c.__FULL_GAME.clockErrors[0].dt,b.rt.forcedDt);
    assert.equal(b.c.__FULL_GAME.clockErrors[0].expectedDt,expected);
});

test('CSV round evidence keeps Confirm, future clock recipe, trajectory and fresh provenance',async()=>{
    const b=boot(),round={wave:'sans_intro',captured:{tick:3,previous_confirm:true},
        source_environment:[32,240,608,384],source_arena:{size:[576,144]},
        plan:{actions:[1,2],confirm_sequence:[true,false],dt_sequence:[1/240,1/240,1/240],
            trajectory:[[1],[2],[3]],request_clock:{count:40000,stepMs:1000/240},computation:{fresh:true,request_id:'unique'}}};
    b.c.__CAMPAIGN.plans.push(round);b.complete();await b.c.__FULL_GAME.recordPromise;
    const saved=JSON.parse(b.requests.at(-1).body);
    assert.deepEqual(saved.computedPlans,[round]);
});

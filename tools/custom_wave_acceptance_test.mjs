import {test} from 'node:test';
import assert from 'node:assert/strict';
import {webcrypto} from 'node:crypto';
import fs from 'node:fs';
import vm from 'node:vm';
const source=fs.readFileSync(new URL('../c2-sans-fight/custom_wave_acceptance.js',import.meta.url),'utf8');
function boot(selected='custom'){
    class Runtime{tick(){this.work?.();this.work=null;this.tickcount++;}trigger(){}}
    const rt=new Runtime(),head={sid:7974524067202295,instances:[]};
    const heart={uid:1,x:320,y:320,angle:0,instance_vars:[0,0,0],behavior_insts:[{type:{name:'CustomMovement'},dx:0,dy:0}]};
    const zone={uid:2,instance_vars:[0,0,640,480],bbox:{left:0,top:0,right:640,bottom:480},update_bbox(){}};
    Object.assign(rt,{tickcount:0,kahanTime:{sum:0},dt:1/240,last_tick_time:0,
        all_global_vars:[{name:'SingleAttack',data:selected},{name:'SimulatorMode',data:2},{name:'HP',data:92},{name:'KR',data:0}],
        types_by_index:[{sid:5960708907117077,instances:[heart]},
            {sid:141231765387603,instances:[zone]},{sid:9768267065126338,instances:[{instance_vars:[0,0,0,0,0,0]}]},
            {sid:456555951765879,instances:[{ra:2}]},head],
        varsBySid:Object.fromEntries([[2569112556112449,1],[3521916820909801,0],[164016619418963,1],
            [963626393445968,750],[3111584688851152,480],[1052618449272991,'']].map(([k,data])=>[k,{data}]))});
    const requests=[];
    const c={URLSearchParams,TextEncoder,Uint8Array,crypto:webcrypto,location:{search:'?custom_acceptance=1&attack=sans_realhell_extreme'},
        document:{getElementById(){return {c2runtime:rt};}},cr:{runtime:Runtime,plugins_:{Function:{prototype:{cnds:{OnFunction(){}}}}}},
        fetch:async(url,r)=>{requests.push(JSON.parse(r.body));return {ok:true,json:async()=>({trace:'stub'})};}};
    c.window=c;vm.createContext(c);vm.runInContext(source,c);
    const emit=(fn,p='',p2=0)=>rt.trigger(c.cr.plugins_.Function.prototype.cnds.OnFunction,
        {exps:{Param(r,i){r.set_any(i===0?p:i===1?p2:0);}}},fn);
    const step=fn=>{rt.work=fn;rt.tick();};
    return {rt,c,head,heart,requests,emit,step,start(){step(()=>emit('tlplay','0,HeartTeleport,320,320\n'));}};
}
test('custom and named URL attacks capture the native opening and CSV hash',async()=>{
    for(const selected of ['custom','sans_realhell_extreme']){
        const b=boot(selected);b.start();await b.c.__CUSTOM_WAVE.stop();
        const a=b.c.__CUSTOM_WAVE;assert.equal(a.started,true);assert.equal(a.entry.tick,0);
        assert.equal(a.csv_sha256.length,64);assert.equal(a.rows[0].state.length,11);
        assert.equal(a.rows[0].lineCount,2);
        assert.equal(b.requests[0].result.passed,false);assert.equal(a.status,'incomplete');
    }
});
test('EOF with a zero-damage preheating laser is never counted as a stable empty tail',()=>{
    const b=boot();b.start();b.head.instances=[{uid:9,x:0,y:0,instance_vars:[0,0],behavior_insts:[]}];
    b.rt.varsBySid[2569112556112449].data=3;
    for(let i=0;i<300;i++)b.step();
    const a=b.c.__CUSTOM_WAVE;assert.equal(a.eofObserved,true);assert.equal(a.stableTailTicks,0);
    assert.equal(a.status,'incomplete_eof');assert.equal(a.terminalCertified,false);
    b.head.instances=[];b.step();assert.equal(a.stableTailTicks,1);
    assert.equal(a.lifecycles.at(-1).kind,'destroyed');assert.equal(a.status,'incomplete_eof');
});
test('first-tick damage and same-tick DamagePlayer restoration fail permanently',async()=>{
    for(const restored of [false,true]){
        const b=boot();b.step(()=>{b.emit('tlplay','x');
            if(restored)b.emit('damageplayer',1);else b.rt.all_global_vars[2].data=91;});
        const a=b.c.__CUSTOM_WAVE;await a.recordPromise;
        assert.equal(a.status,'failed_damage');assert.equal(b.requests[0].result.passed,false);
        b.rt.all_global_vars[2].data=92;b.step();assert.equal(a.status,'failed_damage');
    }
});
test('unrelated TLPlay does not select the custom observation',()=>{
    const b=boot('sans_intro');b.start();assert.equal(b.c.__CUSTOM_WAVE.started,false);
});

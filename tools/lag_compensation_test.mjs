// Production scheduler + production TAS runner; the runtime records the inputs
// each physics step receives. Original-game acceptance is tested separately.
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

async function boot({compensate=true,nativeResumeRebases=false}={}) {
    const rows=[], raf=[];
    const keyboard={keyMap:new Array(256).fill(false)};
    class Runtime {
        tick(background, timestamp) {
            const dt=(timestamp-this.last_tick_time)/1000;
            this.last_tick_time=timestamp;
            rows.push([keyboard.keyMap[37],keyboard.keyMap[38],keyboard.keyMap[39],keyboard.keyMap[40]]);
            this.kahanTime.sum+=dt;
        }
        draw() {}
    }
    const rt=new Runtime();
    Object.assign(rt,{kahanTime:{sum:100},last_tick_time:0,types_by_index:[],all_global_vars:[],running_layout:{},suspended:false});
    const context={
        console:{log(){},warn(){}},URL,URLSearchParams,
        location:{search:compensate?'?compensate=1':'',href:'http://localhost/game/'},
        document:{readyState:'loading',hidden:false,addEventListener(name,callback){if(name==='visibilitychange')this.onVisibility=callback;},getElementById(){return null;}},
        c2runtime:rt,C2_KEYBOARD_INSTANCE:keyboard,cr:{runtime:Runtime},
        setInterval(){return 1;},clearInterval(){},performance:{now:()=>0},
        requestAnimationFrame(callback){raf.push(callback);},cr_setSuspended(value){rt.suspended=value;if(!value&&nativeResumeRebases)rt.last_tick_time=999999.7;},
        fetch:async()=>({ok:true,json:async()=>({planner:'canonical-adaptive-dag',candidate_found:true,
            action_sequence:[[1,0],[0,1],[-1,0],[0,0],[1,1],[0,0]],trajectory:[],physics_mode:'c2',stats:{}})}),
    };
    context.window=context;
    vm.createContext(context);
    // Actual startup order: compensation wraps first, runner hook installs later.
    for(const name of ['lag_compensation','tas_runner']) {
        vm.runInContext(fs.readFileSync(new URL(`../c2-sans-fight/${name}.js`,import.meta.url),'utf8'),context);
    }
    await context.TASRunner.fetchOptimalRoute('sans_bonegap1.csv');
    await context.TASRunner.startPlayback();
    return {context,rt,rows,frame(now){assert.ok(raf.length);raf.shift()(now);}};
}

test('catch-up delivers every short press and release to the production runner',async()=>{
    const regular=await boot(), stalled=await boot();
    regular.frame(0); stalled.frame(0);
    for(let i=1;i<=24;i++)regular.frame(i*1000/240);
    stalled.frame(100);
    assert.deepEqual(stalled.rows,regular.rows);
    assert.equal(stalled.rows.length,24);
    assert.deepEqual(stalled.rows.slice(4,8),Array.from({length:4},()=>[false,true,false,false]));
    assert.deepEqual(stalled.rows.slice(8,12),Array.from({length:4},()=>[true,false,false,false]));
    assert.equal(stalled.rt.kahanTime.sum,regular.rt.kahanTime.sum);
});

test('batch limits retain all debt and eventually reproduce the unstalled inputs',async()=>{
    const regular=await boot(), stalled=await boot();
    regular.frame(0);stalled.frame(0);
    for(let i=1;i<=240;i++)regular.frame(i*1000/240);
    stalled.frame(1000);
    assert.equal(stalled.rows.length,48);
    assert.ok(stalled.context.__TAS_CLOCK.clock.debtMs>799);
    for(let i=0;i<4;i++)stalled.frame(1000);
    assert.deepEqual(stalled.rows,regular.rows);
    assert.ok(stalled.context.__TAS_CLOCK.clock.debtMs<1e-6);
});

test('hidden interval is paused even when the browser emits no hidden RAF',async()=>{
    const game=await boot();
    game.frame(0);game.frame(20);
    game.context.document.hidden=true;
    // Browser suppresses RAF while hidden: only a visibility event is delivered.
    game.context.document.onVisibility?.();
    game.context.document.hidden=false;
    game.context.document.onVisibility?.();
    game.frame(10000);
    assert.equal(game.rows.length,4);
    game.frame(10000+1000/240);
    assert.equal(game.rows.length,5);
});

test('native self-scheduled ticks cannot consume inputs outside the driver',async()=>{
    const game=await boot();
    game.rt.tick(false,400,true);
    assert.equal(game.rows.length,0);
    assert.equal(game.context.TASRunner.getState().firstObserved,null);
    assert.equal(game.context.C2_KEYBOARD_INSTANCE.keyMap.some(Boolean),false);
});

test('paused runtime resumes without a wall-time jump and keeps existing debt',async()=>{
    const game=await boot();game.frame(0);game.frame(1000);
    game.rt.suspended=true;game.frame(1001);
    const debt=game.context.__TAS_CLOCK.clock.debtMs;
    game.rt.suspended=false;game.frame(10000);
    assert.equal(game.context.__TAS_CLOCK.clock.debtMs,debt);
    game.frame(10000);assert.equal(game.rows.length,96);
});

test('native resume cannot change the exact logical timestamp used by a baked candidate',async()=>{
    const game=await boot({nativeResumeRebases:true});game.frame(0);game.frame(100);
    const timestamp=game.rt.last_tick_time,time=game.rt.kahanTime.sum;
    game.context.cr_setSuspended(true);
    game.context.cr_setSuspended(false);
    assert.equal(game.rt.last_tick_time,timestamp);
    game.frame(20000);game.frame(20000+1000/240);
    assert.equal(game.rt.last_tick_time,timestamp+1000/240);
    assert.equal(game.rt.kahanTime.sum,time+((timestamp+1000/240)-timestamp)/1000);
});

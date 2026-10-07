// Production scheduler against the native timestamp-difference/clamp rule.
// This does not substitute a fixed dt or constitute original-game acceptance.
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

const source=fs.readFileSync(new URL('../c2-sans-fight/lag_compensation.js',import.meta.url),'utf8');

function boot({fps, start=900.125, rebase=9876543.12345}={}) {
    const frames=[],rows=[];
    let nativeWriting=false,dt=0,dtWrites=0,canAdvance=true;
    class Runtime {
        tick(background,timestamp) {
            assert.equal(background,true);
            const previous=this.last_tick_time;
            const delta=(timestamp-previous)/1000;
            nativeWriting=true;
            try {this.dt=Math.min(1/30,delta);} finally {nativeWriting=false;}
            this.last_tick_time=timestamp;
            rows.push({previous,timestamp,delta,dt:this.dt});
        }
        draw() {}
    }
    const rt=new Runtime();
    Object.assign(rt,{last_tick_time:start,running_layout:{},suspended:false});
    Object.defineProperty(rt,'dt',{get:()=>dt,set:value=>{
        assert.equal(nativeWriting,true,'scheduler must never assign runtime.dt');
        dt=value;dtWrites++;
    }});
    const context={URLSearchParams,location:{search:'?csvtas=1'+(fps===undefined?'':'&fps='+fps)},
        c2runtime:rt,cr:{runtime:Runtime},performance:{now:()=>0},
        document:{hidden:false,addEventListener(name,fn){if(name==='visibilitychange')this.visibility=fn;},getElementById(){return null;}},
        requestAnimationFrame(fn){frames.push(fn);},
        cr_setSuspended(value){rt.suspended=value;if(!value)rt.last_tick_time=rebase;},
        TASRunner:{isTickHooked:()=>true,releaseAllKeys(){}},
        __CSV_TAS:{canAdvance:()=>canAdvance}};
    context.window=context;
    vm.runInNewContext(source,context);
    return {context,rt,rows,frame(now){assert.ok(frames.length);frames.shift()(now);},
        block(){canAdvance=false;},writes:()=>dtWrites};
}

function expected(start,hz,count) {
    const result=[];
    const step=1000/hz+(hz===30?1e-6:0);
    let timestamp=start;
    for(let i=0;i<count;i++) {
        const previous=timestamp;
        timestamp=previous+step;
        const delta=(timestamp-previous)/1000;
        result.push({previous,timestamp,delta,dt:Math.min(1/30,delta)});
    }
    return result;
}

test('csv clock defaults to the existing native-clamped 30 Hz protocol',()=>{
    const game=boot();game.frame(0);
    for(let i=1;i<=30;i++)game.frame(i*1000/30);
    assert.equal(game.context.__TAS_CLOCK.mode,'fixed-30hz-native-clamp');
    assert.equal(game.context.__TAS_CLOCK.physicsHz,30);
    assert.equal(game.context.__TAS_CLOCK.logicalStepMs,1000/30+1e-6);
    assert.deepEqual(game.rows,expected(900.125,30,30));
    assert.ok(game.rows.every(row=>row.delta>1/30&&row.dt===1/30));
    assert.equal(game.writes(),30);
});

for(const hz of [60,120,240]) {
    test(`${hz} Hz emits exact accumulating timestamps and naturally nonuniform binary64 dt`,()=>{
        const game=boot({fps:hz});game.frame(0);
        for(let i=1;i<=40;i++)game.frame(i*1000/hz);
        assert.equal(game.context.__TAS_CLOCK.mode,'fixed-native-timestamps');
        assert.equal(game.context.__TAS_CLOCK.physicsHz,hz);
        assert.equal(game.context.__TAS_CLOCK.logicalStepMs,1000/hz);
        assert.equal(game.context.__TAS_CLOCK.clock.stepMs,1000/hz);
        assert.deepEqual(game.rows,expected(900.125,hz,40));
        assert.ok(new Set(game.rows.map(row=>row.dt)).size>1,'crossing a binary exponent boundary must preserve unequal dt');
        assert.ok(game.rows.some(row=>row.dt!==1/hz),'a nominal constant dt must not replace timestamp subtraction');
        assert.equal(game.writes(),40);
    });

    test(`${hz} Hz pause/resume preserves phase even when native resume rebases its clock`,()=>{
        const game=boot({fps:hz});game.frame(0);
        // Stop before crossing the 2^10 timestamp precision boundary.
        game.frame(2.25*1000/hz);
        assert.equal(game.rows.length,2);
        const timestamp=game.rt.last_tick_time,debt=game.context.__TAS_CLOCK.clock.debtMs;
        game.context.cr_setSuspended(true);
        game.frame(5000);
        game.context.cr_setSuspended(false);
        assert.equal(game.rt.last_tick_time,timestamp);
        assert.equal(game.context.__TAS_CLOCK.clock.debtMs,debt);
        game.frame(10000);
        assert.equal(game.rows.length,2);
        for(let i=1;i<=38;i++)game.frame(10000+i*1000/hz);
        assert.deepEqual(game.rows,expected(900.125,hz,40));
        assert.equal(game.writes(),40);
    });

    test(`${hz} Hz catch-up retains every native dt and physical step`,()=>{
        const game=boot({fps:hz});game.frame(0);game.frame(1000);
        for(let i=0;i<Math.ceil(hz/48);i++)game.frame(1000);
        assert.deepEqual(game.rows,expected(900.125,hz,hz));
        assert.ok(game.context.__TAS_CLOCK.clock.debtMs<1e-6);
        assert.equal(game.context.__TAS_CLOCK.stats.droppedSteps,0);
        game.block();game.frame(2000);
        assert.equal(game.rows.length,hz);
        game.rt.tick(false,999999,true);
        assert.equal(game.rows.length,hz);
    });
}

for(const fps of [0,59,NaN])test(`unsupported csv fps ${fps} stops without consuming native ticks`,()=>{
    const game=boot({fps});game.frame(0);game.frame(1000);
    assert.match(game.context.__TAS_CLOCK.error,/fps/i);
    assert.equal(game.rows.length,0);
    assert.equal(game.writes(),0);
});

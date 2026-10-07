// Read a real API response from stdin; exercise production runner hook ordering.
// No browser, original runtime, or native checkpoint is used.
import fs from 'node:fs';
import vm from 'node:vm';
import assert from 'node:assert/strict';
const plan=JSON.parse(fs.readFileSync(0,'utf8'));
const keyboard={keyMap:new Array(256).fill(false)};
const consumed=[];
class Runtime {
    tick() {
        const k=keyboard.keyMap;
        consumed.push((k[37]?1:0)|(k[39]?2:0)|(k[38]?4:0)|(k[40]?8:0)|(k[16]?16:0));
    }
}
const rt=new Runtime();
Object.assign(rt,{kahanTime:{sum:100},types_by_index:[],all_global_vars:[]});
const context={console:{log(){},warn(){}},URL,URLSearchParams,
    location:{search:'',href:'http://localhost/game/'},
    document:{readyState:'loading',addEventListener(){},getElementById(){return null;}},
    c2runtime:rt,C2_KEYBOARD_INSTANCE:keyboard,cr:{runtime:Runtime},
    setInterval(){return 1;},clearInterval(){}};
context.window=context;vm.createContext(context);
vm.runInContext(fs.readFileSync(new URL('../c2-sans-fight/tas_runner.js',import.meta.url),'utf8'),context);
const runner=context.TASRunner;
await runner.loadCalculatedPlan(plan,'sans_eof.csv');
assert.equal(consumed.length,0); // Installation is at the observed post-tick boundary.
for(let i=0;i<plan.action_sequence.length+1;i++) {
    // Even a large game-time jump must not skip a physical-tick witness edge.
    rt.kahanTime.sum+=i%3===0?.1:1/240;
    rt.tick();
}
assert.deepEqual(consumed.slice(0,-1),plan.action_sequence);
assert.equal(consumed.at(-1),0);
assert.equal(runner.getState().isPlaying,false);
process.stdout.write(JSON.stringify({consumed,controlTicks:runner.getState().controlTicks}));

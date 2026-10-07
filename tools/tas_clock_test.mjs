// Exercises the production runner and actual key injection with a clock stub.
// This is an integration regression test, not original-game acceptance.
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

async function boot(actions, protocol = {}) {
    class Runtime { tick() {} }
    const rt = new Runtime();
    rt.kahanTime = {sum: 100};
    rt.types_by_index = [];
    rt.all_global_vars = [];
    const keyboard = {keyMap: new Array(256).fill(false)};
    const context = {
        console: {log(){}, warn(){}}, URL, URLSearchParams,
        location: {search: '', href: 'http://localhost/game/'},
        document: {readyState: 'loading', addEventListener(){}, getElementById(){return null;}},
        c2runtime: rt, C2_KEYBOARD_INSTANCE: keyboard,
        cr: {runtime: Runtime}, setInterval(){return 1;}, clearInterval(){},
        fetch: async () => ({ok: true, json: async () => ({
            planner: 'canonical-adaptive-dag', candidate_found: true,
            action_sequence: actions, trajectory: [], physics_mode: 'c2', stats: {},
            ...protocol,
        })}),
    };
    context.window = context;
    vm.createContext(context);
    vm.runInContext(fs.readFileSync(new URL('../c2-sans-fight/tas_runner.js', import.meta.url),'utf8'), context);
    const runner = context.TASRunner;
    await runner.fetchOptimalRoute('sans_bonegap1.csv');
    await runner.startPlayback();
    return {runner, keyboard, at(time){rt.kahanTime.sum=time;rt.tick();}};
}

test('variable duration ticks follow game time and hold keys within a control frame', async () => {
    const {runner,keyboard,at}=await boot([[1,0],[0,1],[-1,0],[0,0]]);
    at(100); assert.equal(keyboard.keyMap[39],true);
    at(100+1/240); assert.equal(keyboard.keyMap[39],true);
    at(100+1/60); assert.equal(keyboard.keyMap[38],true);
    at(100+3/60); // only four ticks elapsed, but three control frames elapsed
    assert.equal(runner.getState().currentFrame,3);
    assert.equal(keyboard.keyMap.some(Boolean),false);
});

test('a long frame that skips beyond the last action releases all keys', async () => {
    const {runner,keyboard,at}=await boot([[1,1],[1,1]]);
    at(100); assert.equal(keyboard.keyMap[39],true);
    at(100.1);
    assert.equal(keyboard.keyMap.some(Boolean),false);
    assert.equal(runner.getState().isPlaying,false);
});

test('starting a second round reanchors the game clock', async () => {
    const {runner,keyboard,at}=await boot([[1,0],[-1,0]]);
    at(100); at(100+2/60);
    await runner.startPlayback();
    at(200);
    assert.equal(runner.getState().currentFrame,0);
    assert.equal(keyboard.keyMap[39],true);
});

test('one-tick controls are consumed exactly once even when elapsed time jumps', async () => {
    const {runner,keyboard,at}=await boot([2,4,1,0], {
        planner:'canonical-dag-dp',control_ticks:1,control_hz:240,physics_hz:240,
    });
    at(100); assert.equal(keyboard.keyMap[39],true);
    at(100+1/240); assert.equal(keyboard.keyMap[38],true);
    at(100+0.1); assert.equal(keyboard.keyMap[37],true);
    assert.equal(runner.getState().currentFrame,2);
    at(100+0.1); assert.equal(keyboard.keyMap.some(Boolean),false);
    at(100+0.1); assert.equal(runner.getState().isPlaying,false);
});

test('installing a one-tick campaign plan preserves its input cadence', async () => {
    const {runner,keyboard,at}=await boot([[0,0]]);
    await runner.loadCalculatedPlan({planner:'canonical-dag-dp',candidate_found:true,
        action_sequence:[2,1,0],control_ticks:1,control_hz:240,physics_hz:240},'sans_intro.csv');
    at(200); assert.equal(keyboard.keyMap[39],true);
    at(200+1/240); assert.equal(keyboard.keyMap[37],true);
    assert.equal(runner.getState().controlTicks,1);
    assert.throws(()=>runner.loadCalculatedPlan({planner:'canonical-dag-dp',candidate_found:true,
        action_sequence:[0],control_ticks:1,control_hz:60,physics_hz:240},'sans_intro.csv'),/240 Hz/);
});

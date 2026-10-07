import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';

const context={window:{}};
vm.runInNewContext(readFileSync(new URL('../c2-sans-fight/menu_controller.js',import.meta.url),'utf8'),context);
const C=context.window.NoHitMenuController;
const buttons=[
    {sid:9343233059165768,x:32,action:'MenuFight'},
    {sid:9683599283524679,x:185,action:'MenuAct'},
    {sid:9790445263738264,x:345,action:'MenuItem'},
    {sid:3900276529955833,x:500,action:'MenuMercy'},
];
function runtime(menu=2,confirm=0,bone=null) {
    const point=32+110*.145454540848732;
    return {types_by_index:[
        {sid:5960708907117077,instances:[{x:point,y:453,instance_vars:[0,0,0]}]},
        {sid:9768267065126338,instances:[{instance_vars:[0,0,0,0,confirm,0]}]},
        ...buttons.map((b,i)=>({sid:b.sid,instances:[{x:b.x,y:432,width:110,height:42,instance_vars:[i,b.action]}]})),
        {sid:5246535965326995,instances:bone?[bone]:[]},
        {sid:761861833921609,instances:[]},
        {sid:1630849692866887,instances:menu===3?[{x:64,y:272,instance_vars:[0,'* Sans','MenuFightEnemy']}]:[]},
        {sid:4243712716812677,instances:menu===0?[{instance_vars:[0]}]:[]},
    ],varsBySid:{5359025861573384:{data:menu},9909730646709937:{data:0},
        2101703704976127:{data:0},9606556173175612:{data:0}}};
}
const leftBone=timer=>({x:0,y:270,width:14,height:44,instance_vars:[1,0,timer,0]});

test('actual step(rt) boundary reads exported sids and only returns normal keys',()=>{
    const rt=runtime(),before=JSON.stringify(rt);
    const choice=C.step(rt);
    assert.equal(choice.confirm,true);
    assert.equal(choice.keymask,0);
    assert.equal(choice.reason,'enter_enemy_during_safe_window');
    assert.equal(JSON.stringify(rt),before,'controller must not mutate native state');
});

test('enemy-selection boundary releases prior Confirm then creates a fresh edge',()=>{
    assert.equal(C.step(runtime(3,1)).confirm,false);
    assert.equal(C.step(runtime(3,0)).confirm,true);
    assert.equal(C.step(runtime(0,1)).confirm,false);
    assert.equal(C.step(runtime(0,0)).confirm,true);
});

test('a bone entering enemy cursor during release step postpones menu entry',()=>{
    // Its next positions are near60; polygon extends to~72 at y284.
    const rt=runtime(2,0,leftBone(.300));
    const choice=C.step(rt);
    assert.equal(choice.confirm,false);
    assert.equal(choice.blocked,false);
});

test('clear enemy cursor permits an immediate normal Confirm despite active bones',()=>{
    assert.equal(C.step(runtime(2,0,leftBone(.01))).confirm,true);
});

test('bottom bone near selected button triggers ordinary navigation to a safe button',()=>{
    const rt=runtime(2,0,leftBone(.30));
    rt.types_by_index.find(t=>t.sid===761861833921609).instances.push({x:41,y:440,width:14,height:44,instance_vars:[1,0,1,0]});
    const choice=C.step(rt);
    assert.equal(choice.confirm,false);
    assert.ok([1,2].includes(choice.keymask));
});

test('source menu-bone forecast uses current timer slowdown, not constant velocity',()=>{
    const m=C.read(runtime(2,0,leftBone(.4)));
    const expectedTimer=.4+1/240;
    C.advance(m);
    assert.ok(m.bones[0].x>64);
    assert.equal(m.bones[0].timer,expectedTimer-(1/240)*.72);
});

test('bottom spawn advances newborn through native sequential movement blocks',()=>{
    const m=C.read(runtime());m.bottomOn=1;m.bottomTimer=.599;
    C.advance(m);
    assert.equal(m.bones.length,2);
    assert.equal(m.bones[0].y,478.75);
    assert.equal(m.bottomAlternate,1);
});

test('menu geometry includes touching original polygon edge',()=>{
    const b={x:0,y:0,w:14,h:44,damage:1};
    const right=b.w*.857142984867096;
    assert.equal(C.collides(right+2,10,b),true);
    assert.equal(C.collides(right+2+1e-9,10,b),false);
});

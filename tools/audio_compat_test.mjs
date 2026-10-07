import {test} from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
const source=fs.readFileSync(new URL('../c2-sans-fight/audio_compat.js',import.meta.url),'utf8');
function boot(search='?custom_acceptance=1',maximum=16){
    const rates=new WeakMap(),calls=[];
    class Media{constructor(){this.src='music.ogg';rates.set(this,1);}}
    Object.defineProperty(Media.prototype,'playbackRate',{configurable:true,enumerable:true,
        get(){return rates.get(this);},set(value){calls.push(value);
            if(value===7){const e=Error('security');e.name='SecurityError';throw e;}
            if(value<1/16||value>maximum){const e=Error('unsupported');e.name='NotSupportedError';throw e;}
            rates.set(this,value);}});
    const original=Object.getOwnPropertyDescriptor(Media.prototype,'playbackRate');
    const c={URLSearchParams,location:{search},HTMLMediaElement:Media,
        document:{getElementById(){return {c2runtime:{tickcount:42}};}}};
    c.window=c;vm.createContext(c);vm.runInContext(source,c);
    return {c,Media,calls,original};
}
test('normal mode has no prototype changes without opt-in',()=>{
    const b=boot('?mode=normal&campaign=1');
    assert.equal(Object.getOwnPropertyDescriptor(b.Media.prototype,'playbackRate').set,b.original.set);
    assert.equal(b.c.__AUDIO_COMPAT,undefined);
});
test('supported rates use the unmodified native setter with no deviation',()=>{
    const b=boot(),m=new b.Media();m.playbackRate=1.4;
    assert.equal(m.playbackRate,1.4);assert.deepEqual(b.calls,[1.4]);
    assert.equal(b.c.__AUDIO_COMPAT.cosmeticDeviation,false);
    assert.equal(Object.getOwnPropertyDescriptor(b.Media.prototype,'playbackRate').get,b.original.get);
});
test('requested 20 falls back to native-accepted 16 and records the cosmetic change',()=>{
    const b=boot(),m=new b.Media();m.playbackRate=20;m.playbackRate=20;
    assert.equal(m.playbackRate,16);
    const a=b.c.__AUDIO_COMPAT;assert.equal(a.cosmeticDeviation,true);assert.equal(a.events.length,1);
    assert.equal(a.events[0].requested,20);assert.equal(a.events[0].actual,16);
    assert.equal(a.events[0].attempts,2);assert.equal(a.events[0].firstTick,42);
});
test('explicit opt-in works and unsupported fallback may use normal playback',()=>{
    const b=boot('?audio_compat=1',4),m=new b.Media();m.playbackRate=20;
    assert.equal(m.playbackRate,1);assert.equal(b.c.__AUDIO_COMPAT.events[0].actual,1);
});
test('unrelated exceptions and nonpositive values are not swallowed',()=>{
    const b=boot(),m=new b.Media();
    assert.throws(()=>m.playbackRate=7,{name:'SecurityError'});
    assert.throws(()=>m.playbackRate=-1,{name:'NotSupportedError'});
    assert.equal(b.c.__AUDIO_COMPAT.events.length,0);
});

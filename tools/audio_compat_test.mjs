import {test} from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
const source=fs.readFileSync(new URL('../c2-sans-fight/audio_compat.js',import.meta.url),'utf8');
function boot(search='?custom_acceptance=1',maximum=16){
    const rates=new WeakMap(),calls=[],volumes=new WeakMap(),muted=new WeakMap();
    class Media{
        constructor(){this.src='music.ogg';rates.set(this,1);volumes.set(this,1);muted.set(this,false);}
        play(){this.played={muted:this.muted,volume:this.volume};return this.playResult;}
    }
    for(const [property,values] of [['volume',volumes],['muted',muted]])
        Object.defineProperty(Media.prototype,property,{configurable:true,
            get(){return values.get(this);},set(value){values.set(this,value);}});
    class AudioNode{
        constructor(context){this.context=context;this.edges=[];}
        connect(destination,...args){this.edges.push({destination,args});return destination;}
        disconnect(...args){this.disconnected=args;}
        start(){this.started=true;}
    }
    class AudioContext{
        constructor(){this.destination=new AudioNode(this);this.state='running';this.currentTime=12;this.gains=[];}
        createGain(){const node=new AudioNode(this);node.gain={value:1};this.gains.push(node);return node;}
        createBufferSource(){return new AudioNode(this);}
    }
    Object.defineProperty(Media.prototype,'playbackRate',{configurable:true,enumerable:true,
        get(){return rates.get(this);},set(value){calls.push(value);
            if(value===7){const e=Error('security');e.name='SecurityError';throw e;}
            if(value<1/16||value>maximum){const e=Error('unsupported');e.name='NotSupportedError';throw e;}
            rates.set(this,value);}});
    const original=Object.getOwnPropertyDescriptor(Media.prototype,'playbackRate');
    const play=Media.prototype.play,connect=AudioNode.prototype.connect;
    const c={URLSearchParams,location:{search},HTMLMediaElement:Media,Audio:Media,AudioNode,AudioContext,
        document:{getElementById(){return {c2runtime:{tickcount:42}};}}};
    c.window=c;vm.createContext(c);vm.runInContext(source,c);
    return {c,Media,calls,original,play,connect};
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

for(const flag of ['csvtas=1','campaign=1','mute=1']){
    test(`${flag} silences new media before native play and preserves completion`,()=>{
        const {c}=boot('?'+flag),media=new c.Audio(),result=Promise.resolve();
        let ended=0;const onended=()=>ended++;
        media.onended=onended;media.playResult=result;
        assert.equal(media.play(),result);
        assert.deepEqual(media.played,{muted:true,volume:0});
        media.muted=false;media.volume=1;
        assert.equal(media.muted,true);assert.equal(media.volume,0);
        assert.equal(media.onended,onended);media.onended();assert.equal(ended,1);
    });
    test(`${flag} routes native WebAudio through zero gain without suspending it`,()=>{
        const {c}=boot('?'+flag),context=new c.AudioContext(),source=context.createBufferSource();
        let ended=0;const onended=()=>ended++;
        source.onended=onended;
        assert.equal(source.connect(context.destination,0,0),context.destination);
        const master=context.gains[0];
        assert.equal(master.gain.value,0);
        assert.equal(master.edges[0].destination,context.destination);
        assert.equal(source.edges[0].destination,master);
        assert.deepEqual(source.edges[0].args,[0,0]);
        source.start();assert.equal(source.started,true);
        assert.equal(context.state,'running');assert.equal(context.currentTime,12);
        assert.equal(source.onended,onended);source.onended();assert.equal(ended,1);
        source.disconnect(context.destination,0,0);
        assert.deepEqual(source.disconnected,[master,0,0]);
        const second=context.createBufferSource();second.connect(context.destination);
        assert.equal(context.gains.length,1);assert.equal(second.edges[0].destination,master);
    });
}

for(const search of ['', '?audio_compat=1', '?campaign=1&mute=0']){
    test(`manual audio remains native for ${search||'no query'}`,()=>{
        const {c,play,connect}=boot(search),media=new c.Audio(),context=new c.AudioContext();
        assert.equal(c.__AUDIO_OUTPUT_GUARD,undefined);
        assert.equal(c.HTMLMediaElement.prototype.play,play);
        assert.equal(c.AudioNode.prototype.connect,connect);
        media.play();assert.deepEqual(media.played,{muted:false,volume:1});
        const source=context.createBufferSource();source.connect(context.destination);
        assert.equal(source.edges[0].destination,context.destination);assert.equal(context.gains.length,0);
    });
}

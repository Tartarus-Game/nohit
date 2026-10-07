// Opt-in cosmetic compatibility for custom CSV audio rates rejected by Chromium.
// Native game code, CSV commands, logical clock, physics and inputs are untouched.
(() => {
    const query=new URLSearchParams(location.search);
    if(query.get('custom_acceptance')!=='1'&&query.get('audio_compat')!=='1')return;
    if(window.__AUDIO_COMPAT?.status==='installed')return;
    const A=window.__AUDIO_COMPAT={status:'unavailable',scope:'audio_output_only',
        cosmeticDeviation:false,events:[]};
    const proto=window.HTMLMediaElement?.prototype;
    const descriptor=proto&&Object.getOwnPropertyDescriptor(proto,'playbackRate');
    if(!descriptor?.set||!descriptor.get||!descriptor.configurable){
        A.reason='native_playback_rate_descriptor_unavailable';return;
    }
    const seen=new WeakMap();
    const tick=()=>document.getElementById('c2canvas')?.c2runtime?.tickcount??null;
    Object.defineProperty(proto,'playbackRate',{...descriptor,set(value){
        try{return descriptor.set.call(this,value);}
        catch(error){
            // Never hide arbitrary native errors or invalid/nonpositive values.
            if(error?.name!=='NotSupportedError'||typeof value!=='number'||!Number.isFinite(value)||value<=0)throw error;
            const bounded=Math.min(16,Math.max(1/16,value));
            let succeeded=false;
            for(const fallback of [...new Set([bounded,1])]){
                if(fallback===value)continue;
                try{descriptor.set.call(this,fallback);succeeded=true;break;}
                catch(next){if(next?.name!=='NotSupportedError')throw next;}
            }
            if(!succeeded)throw error;
            const actual=descriptor.get.call(this),nativeTick=tick();
            let entry=seen.get(this);
            if(!entry||entry.requested!==value||entry.actual!==actual){
                entry={requested:value,actual,reason:'native_NotSupportedError',
                    source:this.currentSrc||this.src||'',firstTick:nativeTick,lastTick:nativeTick,attempts:0};
                A.events.push(entry);seen.set(this,entry);
            }
            entry.attempts++;entry.lastTick=nativeTick;A.cosmeticDeviation=true;
        }
    }});
    A.status='installed';
})();

// Automated runs keep native audio playback and callbacks, with silent output.
(() => {
    const query=new URLSearchParams(location.search);
    if(query.get('mute')==='0'||!(query.get('mute')==='1'||
        query.get('csvtas')==='1'||query.get('campaign')==='1'))return;
    if(window.__AUDIO_OUTPUT_GUARD)return;
    const guard=window.__AUDIO_OUTPUT_GUARD={status:'installed',scope:'audio_output_only',
        media:false,webAudio:false};
    const media=window.HTMLMediaElement?.prototype;
    if(media&&typeof media.play==='function'){
        // The runtime may change volume/muted again while playback is running.
        for(const [property,value] of [['muted',true],['volume',0]]){
            const descriptor=Object.getOwnPropertyDescriptor(media,property);
            if(descriptor?.set&&descriptor.configurable)
                Object.defineProperty(media,property,{...descriptor,set(){
                    return descriptor.set.call(this,value);
                }});
        }
        const play=media.play;
        media.play=function(...args){
            this.muted=true;this.volume=0;
            return play.apply(this,args);
        };
        guard.media=true;
    }
    const node=window.AudioNode?.prototype;
    if(node&&typeof node.connect==='function'){
        const connect=node.connect,disconnect=node.disconnect,masters=new WeakMap();
        const masterFor=context=>{
            let master=masters.get(context);
            if(!master){
                master=context.createGain();master.gain.value=0;
                connect.call(master,context.destination);masters.set(context,master);
            }
            return master;
        };
        node.connect=function(destination,...args){
            if(destination===this.context?.destination){
                connect.call(this,masterFor(this.context),...args);
                return destination;
            }
            return connect.call(this,destination,...args);
        };
        if(typeof disconnect==='function')node.disconnect=function(destination,...args){
            if(destination===this.context?.destination&&masters.has(this.context))
                return disconnect.call(this,masters.get(this.context),...args);
            return disconnect.apply(this,arguments);
        };
        guard.webAudio=true;
    }
})();

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

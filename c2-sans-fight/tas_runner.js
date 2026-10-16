// Native keyboard discovery, clock gate and status surface for CSV controllers.
(() => {
    const managedKeys=[37,38,39,40,65,68,83,87,88,16,90,13];
    let keyboard=null,tickHooked=false;
    function runtime() {
        return window.c2runtime||document.getElementById('c2canvas')?.c2runtime;
    }
    function getKeyboardInstance() {
        if(keyboard?.keyMap)return keyboard;
        if(window.C2_KEYBOARD_INSTANCE?.keyMap)return keyboard=window.C2_KEYBOARD_INSTANCE;
        for(const type of runtime()?.types_by_index||[]) {
            for(const instance of type.instances||[]) {
                if(Array.isArray(instance.keyMap)) {
                    window.C2_KEYBOARD_INSTANCE=keyboard=instance;
                    return keyboard;
                }
            }
        }
        return null;
    }
    function releaseAllKeys() {
        const keys=getKeyboardInstance()?.keyMap;
        if(keys)for(const code of managedKeys)keys[code]=false;
    }
    function showStatus() {
        if(document.getElementById('tas-controller-overlay'))return;
        const hud=document.createElement('div');
        hud.id='tas-controller-overlay';
        hud.style='position:fixed;top:8px;left:50%;transform:translateX(-50%);z-index:999999;'+
            'max-width:calc(100vw - 24px);padding:10px 16px;background:rgba(0,0,0,.94);'+
            'border:1px solid #fff;color:#fff;font:13px/1.5 system-ui,sans-serif';
        const badge=document.createElement('div');
        badge.id='tas-status-badge';
        badge.className='tas-badge';
        badge.textContent='CSV';
        hud.appendChild(badge);
        document.body.appendChild(hud);
    }
    function install() {
        const rt=runtime();
        if(!rt)return;
        const proto=rt.constructor.prototype;
        if(!proto.__nohitNativeTickWrapped) {
            const tick=proto.tick;
            proto.tick=function() {
                if(window.__TAS_CLOCK?.enabled&&!window.__TAS_CLOCK.stepping)return;
                return tick.apply(this,arguments);
            };
            proto.__nohitNativeTickWrapped=true;
        }
        tickHooked=true;
    }
    // The API name remains part of the native evidence/source contract.
    window.TASRunner={getKeyboardInstance,releaseAllKeys,isTickHooked:()=>tickHooked};
    if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',showStatus,{once:true});
    else showStatus();
    if(window.cr?.runtime)install();
    else window.addEventListener('nohit-runtime-ready',install,{once:true});
})();

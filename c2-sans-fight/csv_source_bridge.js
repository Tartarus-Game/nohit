// Supply unchanged user CSV bytes through the original AJAX custom-file path.
(() => {
    const query = new URLSearchParams(location.search);
    if (query.get('csvtas') !== '1') return;
    const id = query.get('csv_source');
    const B = window.__CSV_SOURCE_BRIDGE = {status:'loading',error:null};
    const fail = error => {
        B.error=String(error);B.status='failed';
        window.__CSV_TAS?.cancel?.(B.error);
        if (window.cr?.runtime) window.cr_setSuspended(true);
        const badge=document.getElementById('tas-status-badge');
        if(badge) badge.textContent='CSV 加载停止 · '+B.error;
    };
    window.__CSV_SOURCE_READY = (async () => {
        if (!/^[0-9a-f]{64}$/.test(id || '')) throw Error('Registered csv_source is required');
        const response=await fetch('/api/csv-source/'+id);
        const source=await response.json();
        if(!response.ok) throw Error(source.error || 'CSV source unavailable');
        const bytes=new TextEncoder().encode(source.text);
        const digest=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',bytes)),
            value=>value.toString(16).padStart(2,'0')).join('');
        if(digest!==source.sha256 || source.id!==id || source.raw_sha256!==id ||
            source.url!=='/api/csv-source/'+id+'.csv') throw Error('CSV source identity mismatch');
        window.__CSV_SOURCE=Object.freeze(source);B.status='ready';
        return source;
    })();
    window.__CSV_SOURCE_READY.catch(fail);
    function install() {
        const rt=document.getElementById('c2canvas')?.c2runtime;
        if(!rt) return;
        const proto=rt.constructor.prototype,trigger=proto.trigger,tick=proto.tick;
        let menuReady=false,requested=false,loaded=false,entered=false,source=null;
        window.__CSV_SOURCE_READY.then(value=>source=value).catch(()=>{});
        proto.trigger=function(method,inst,value) {
            const result=trigger.apply(this,arguments);
            if(method===cr.plugins_.Function.prototype.cnds.OnFunction &&
                String(value).toLowerCase()==='attackloadfinished') menuReady=true;
            if(requested && !entered && inst?.rc==='custom') {
                if(method===tc.prototype.c.Zg) {
                    if(inst.zd!==source.text) fail(Error('Native CSV response text mismatch'));
                    else loaded=true;
                } else if(method===tc.prototype.c.Ti) fail(Error('Native CSV request failed'));
            }
            return result;
        };
        proto.tick=function() {
            if(window.__TAS_CLOCK?.enabled && !window.__TAS_CLOCK.stepping) return;
            const result=tick.apply(this,arguments);
            if(B.error || entered || !menuReady || !source) return result;
            const ajax=rt.types_by_index.find(type=>type.sid===1871150019731238)?.instances[0];
            if(!ajax) return result;
            if(!requested) {
                requested=true;B.status='native_loading';
                try {
                    window.c2_callFunction('MenuModeCustom',[]);
                    // tc.St is Request URL in the checked-in jcw87 export.
                    // Its native On completed(custom) handler populates AttackList.
                    tc.prototype.e.St.call(ajax,'custom',source.url);
                } catch(error) {fail(error);}
            } else if(loaded) {
                try {
                    entered=true;
                    window.c2_callFunction('MenuCustomRun',[]);
                    B.status='entered';
                } catch(error) {fail(error);}
            }
            return result;
        };
    }
    if(window.cr?.runtime) install();
    else window.addEventListener('nohit-runtime-ready',install,{once:true});
})();

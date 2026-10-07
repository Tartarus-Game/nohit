// Custom-mode shell for the shared native CSV round controller.
(() => {
    const query=new URLSearchParams(location.search);
    if(query.get('csvtas')!=='1')return;
    const C=window.__CSV_TAS={status:'waiting_source',error:null};
    C.canAdvance=()=>C.status==='waiting_source'; // Available before runtime-ready.
    // The live solve line is owned by the shared round controller, so the Custom
    // shell and the Normal campaign both show it from one implementation.
    function show(value,state) {
        const badge=document.getElementById('tas-status-badge');
        if(value==='completed'&&state.completion_kind==='eof_invariant') {
            if(badge)badge.textContent='EOF 无伤执行完成，等待独立验收';
            return;
        }
        if(badge)badge.textContent=({waiting_source:'等待 CSV 加载',waiting_start:'等待原版起点',solving:'正在解算 CSV',
            playing:'执行 CSV 输入',completed:'已观察到原版 EndAttack',unknown:'有限搜索未找到完整候选',
            failed:'CSV 执行已停止',cancelled:'CSV 执行已取消'}[value]||value)+(state.error?' · '+state.error:'');
    }
    function parameter(inst) {
        const ret={value:null,set_any(v){this.value=v;},set_int(v){this.value=v;},set_float(v){this.value=v;},set_string(v){this.value=v;}};
        inst.exps.Param(ret,0);return ret.value;
    }
    function install() {
        const rt=window.c2runtime||document.getElementById('c2canvas')?.c2runtime;
        if(!rt||!window.cr?.runtime)return;
        const core=window.NoHitCsvRoundController.create({runtime:rt,clock:window.__TAS_CLOCK,query,state:C,onStatus:show,
            terminationPolicy:'eof_hazards_drained',
            prepare:()=>window.__CUSTOM_WAVE?.sourceReady,
            captureEof:settings=>{
                if(!window.__CUSTOM_WAVE?.captureEof)throw Error('Native EOF observer is required');
                return window.__CUSTOM_WAVE.captureEof(settings);
            },
            isSourceCurrent:source=>source===window.__CSV_SOURCE,
            validateBoundary:boundary=>{
                if(boundary.SimulatorMode!==2||boundary.SingleAttack!=='custom')throw Error('Target CSV is not running in the original custom mode');
            }});
        if(query.has('oracle')||query.get('campaign')==='1') {core.fail('csvtas cannot share control with oracle or campaign');return;}
        if(!['fixed-30hz-native-clamp','fixed-native-timestamps'].includes(window.__TAS_CLOCK?.mode)) {core.fail('CSV TAS requires the native timestamp clock');return;}
        const proto=rt.constructor.prototype,baseTick=proto.tick,baseTrigger=proto.trigger;
        proto.trigger=function(method,inst,value) {
            const fn=method===cr.plugins_.Function.prototype.cnds.OnFunction?String(value).toLowerCase():'';
            try {
                if(fn==='tlplay') {
                    const text=String(parameter(inst)),source=window.__CSV_SOURCE;
                    if(core.hasSource())core.fail('Unexpected TLPlay replaced the active CSV');
                    else if(source&&text===source.text)core.beginSource(source);
                }
                core.observeFunction(fn,inst);
            } catch(error) {core.fail(error);}
            return baseTrigger.apply(this,arguments);
        };
        proto.tick=function() {
            if(!window.__TAS_CLOCK.stepping||!core.canAdvance())return;
            try {
                if(!core.hasSource()&&window.__CSV_SOURCE) {
                    const globals=Object.fromEntries(this.all_global_vars.map(v=>[v.name,v.data]));
                    if(globals.SimulatorMode===2&&globals.SingleAttack==='custom') {
                        const pad=this.types_by_index.find(t=>t.sid===9768267065126338)?.instances[0]?.instance_vars;
                        const zone=this.types_by_index.find(t=>t.sid===141231765387603)?.instances[0];
                        zone?.update_bbox();
                        const settled=zone&&[zone.bbox.left,zone.bbox.top,zone.bbox.right,zone.bbox.bottom]
                            .every((value,i)=>value===zone.instance_vars?.[i]);
                        if(pad)core.input(0,!!settled&&!pad[4]);
                    }
                }
                const token=core.beforeTick();if(!token)return;
                const result=baseTick.apply(this,arguments);core.afterTick(token);return result;
            } catch(error) {core.fail(error);}
        };
        if(window.__CSV_SOURCE_READY)window.__CSV_SOURCE_READY.catch(error=>core.fail(error));
        show(C.status,C);
    }
    if(window.cr?.runtime)install();else window.addEventListener('nohit-runtime-ready',install,{once:true});
})();

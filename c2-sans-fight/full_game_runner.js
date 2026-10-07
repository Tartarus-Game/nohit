// Continue the original Normal campaign with fresh CSV candidates at each
// native source boundary. The independent observer owns whole-game acceptance.
(() => {
    const query=new URLSearchParams(location.search);
    if(query.get('campaign')!=='1')return;
    const C=window.__CAMPAIGN={version:3,status:'preparing',attack:null,round:null,
        plans:[],error:null};
    let rt=null,round=null,active=false,roundNumber=-1,retryWidths=[];
    const stopped=new Set(['solving','unknown','failed','cancelled','stopped']);
    C.canAdvance=()=>!C.error&&!window.__FULL_GAME?.done&&!stopped.has(C.status);
    Object.defineProperties(C,{
        boundary:{get:()=>round?.state.boundary?{captured:round.state.boundary,wave:C.attack}:null},
        solvePromise:{get:()=>round?.state.solvePromise},
    });
    function status(value,detail='') {
        C.status=value;
        const badge=document.getElementById('tas-status-badge');
        if(badge)badge.textContent=({preparing:'推进原版对话',waiting_source:'等待原版攻击',waiting_start:'捕获原版起点',
            solving:'正在解算',playing:'执行数学路线',waiting:'等待下一轮',unknown:'有限搜索未找到候选',
            stopped:'求解暂停',failed:'执行已停止',cancelled:'执行已取消'}[value]||value)+(detail?' · '+detail:'');
    }
    function stop(reason) {
        C.error=String(reason);status('stopped',C.error);round?.release();
        if(rt)window.cr_setSuspended(true);
    }
    function parameter(inst) {
        const result={value:null,set_any(v){this.value=v;},set_string(v){this.value=v;},set_int(v){this.value=v;},set_float(v){this.value=v;}};
        inst.exps.Param(result,0);return result.value;
    }
    function createRound() {
        let controller,retryIndex=0;
        controller=window.NoHitCsvRoundController.create({runtime:rt,clock:window.__TAS_CLOCK,query,
            validateBoundary(boundary) {
                if(boundary.SimulatorMode!==0)throw Error('Campaign source is not in original Normal mode');
                if(window.__FULL_GAME?.done)throw Error('Whole-game observer has stopped');
            },
            onStatus(value,state) {
                if(value==='completed')return;
                status(value,C.attack||'');
                if(value==='failed'||value==='cancelled')C.error=state.error;
                if(value==='unknown'&&retryIndex<retryWidths.length) {
                    const generation=state.request_generation;
                    queueMicrotask(()=>{
                        if(round!==controller||!active||C.error||window.__FULL_GAME?.done||window.__FULL_GAME?.firstDamage||
                            state.status!=='unknown'||state.request_generation!==generation||state.firstDamage)return;
                        try {controller.retry({width:retryWidths[retryIndex++]});}
                        catch(error) {stop(error);}
                    });
                }
            },
            onPlan(state) {
                C.plans.push({round:roundNumber,wave:C.attack,captured:state.boundary,plan:state.plan,
                    source_environment:state.source_environment,source_arena:state.source_arena,
                    initial_target_history:state.initial_target_history,source_text:state.source_text,
                    source_sha256:state.csv_sha256,request:state.request,request_generation:state.request_generation});
            },
            onComplete(state) {
                active=false;status('waiting',C.attack);
                const entry=C.plans.findLast(item=>item.round===roundNumber);
                if(entry) {entry.actionsApplied=state.actionsApplied;entry.events=state.events;entry.rows=state.rows;}
            },
        });
        return controller;
    }
    C.retry=(settings={})=>{
        if(C.error||window.__FULL_GAME?.done||!active)throw Error('Retry requires an unchanged unresolved round');
        return round.retry(settings);
    };
    C.cancel=()=>{round?.cancel();C.error='cancelled_by_user';status('cancelled');};
    function install() {
        rt=window.c2runtime||document.getElementById('c2canvas')?.c2runtime;
        if(!rt)return;
        if(query.has('oracle')||query.get('csvtas')==='1') {stop('Campaign cannot share control with oracle or Custom CSV TAS');return;}
        if(window.__TAS_CLOCK?.mode!=='fixed-240hz-realtime-catchup'||window.__TAS_CLOCK.physicsHz!==240) {
            stop('Normal campaign requires compensate=1 and its native 240 Hz timestamp clock');return;
        }
        if(!window.NoHitCsvRoundController||!window.NoHitMenuController) {stop('Campaign shared controllers are not ready');return;}
        if(query.has('retry_widths')) {
            const values=query.get('retry_widths').split(',');
            if(values.some(value=>!/^\d+$/.test(value)||!Number.isSafeInteger(Number(value))||Number(value)<=0)) {
                stop('retry_widths requires comma-separated positive safe integers');return;
            }
            retryWidths=[...new Set(values.map(Number))];
        }
        round=createRound();C.round=round.state;status('preparing');
        const proto=rt.constructor.prototype,baseTrigger=proto.trigger,baseTick=proto.tick;
        proto.trigger=function(method,inst,value) {
            const fn=method===cr.plugins_.Function.prototype.cnds.OnFunction?String(value).toLowerCase():'';
            try {
                if(fn==='runattack') {
                    const raw=String(parameter(inst));
                    if(active)throw Error('Original RunAttack replaced an unfinished round');
                    if(!/^sans_[a-z0-9_]+(?:\.csv)?$/.test(raw))throw Error('Unrecognized original attack: '+raw);
                    round=createRound();C.round=round.state;active=true;roundNumber++;
                    C.attack=raw.endsWith('.csv')?raw:raw+'.csv';status('waiting_source',C.attack);
                }
                if(fn==='tlplay'&&active)round.beginSource({text:String(parameter(inst)),name:C.attack});
                if(active)round.observeFunction(fn,inst);
            } catch(error) {stop(error);}
            return baseTrigger.apply(this,arguments);
        };
        proto.tick=function() {
            if(!window.__TAS_CLOCK.stepping||!C.canAdvance())return;
            let token=null,owner=round;
            try {
                if(active) {
                    if(!round.hasSource())round.input(0,false);
                    token=round.beforeTick();
                }
                else {
                    const menu=window.NoHitMenuController.step(this);C.menu=menu;
                    if(menu.blocked)throw Error('Menu search found no safe input: '+menu.reason);
                    round.input(menu.keymask,menu.confirm);
                }
                if(!C.canAdvance())return;
                const output=baseTick.apply(this,arguments);
                // RunAttack/TLPlay can first occur inside baseTick. The new
                // round must still capture that committed source frame0.
                if(active)round.afterTick(owner===round?token:null);
                return output;
            } catch(error) {stop(error);}
        };
    }
    if(window.cr?.runtime)install();else window.addEventListener('nohit-runtime-ready',install,{once:true});
})();

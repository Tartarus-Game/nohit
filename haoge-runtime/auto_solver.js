// Fresh math search -> independent original replay -> visible real-time TAS.
// No checkpoint branching or saved-route lookup is used for candidate generation.
(() => {
    const query=new URLSearchParams(location.search);
    if(query.get('compute')!=='canonical'||!query.has('oracle')) return;
    const state=window.__AUTO_SOLVER={status:'waiting_for_original_start'};
    const display=document.createElement('pre');
    display.id='auto-solver-status';
    display.style='position:fixed;bottom:100px;left:8px;right:8px;padding:12px;color:white;background:#16202b;z-index:100001;white-space:pre-wrap';
    document.body.appendChild(display);
    function show(status,text){state.status=status;display.textContent=text;}
    show('waiting_for_original_start','自动解算：等待原版关卡起点');
    const timer=setInterval(async()=>{
        if(!window.EngineOracle?.ready) return;
        clearInterval(timer);
        const O=EngineOracle;
        try {
            const s=O.observe();
            if(s.HP!==92||s.KR!==0) throw Error('原版起点已受伤，不能开始无伤验收');
            const wave=query.get('attack')+'.csv';
            const captured=NoHitSolverState.capture(document.getElementById('c2canvas').c2runtime);
            const initial=captured.initial;
            show('solving','正在从真实起点重新解算 '+wave);
            const params=new URLSearchParams({wave,compute:'canonical',seed:query.get('seed')||'42',initial:JSON.stringify(initial),max_nodes:query.get('max_nodes')||'500000',lookahead:query.get('lookahead')||'60',margin:query.get('margin')||'4'});
            params.set('initial_environment',JSON.stringify(captured.initial_environment));
            params.set('clock_start_ms',String(captured.clock_start_ms));
            // The original single-attack mode exits to MainMenu on Cancel.
            // Its legal combat controls differ from a normal battle's slow key.
            if(query.get('mode')==='single')params.set('allow_cancel','0');
            if(query.has('weights')) params.set('weights',query.get('weights'));
            const response=await fetch('/api/tas?'+params);
            const plan=await response.json();
            state.plan=plan;
            if(!response.ok) throw Error(plan.error||'解算服务不可用');
            if(!plan.candidate_found) {
                show(plan.search_status,'解算未完成：'+plan.search_status+'\n'+JSON.stringify(plan.issues||[])+'\n这不代表原版关卡无解。');
                return;
            }
            show('verifying','候选已生成，正在用原版逐步验算 '+plan.action_sequence.length+' 帧');
            const replay=await O.replay(plan.action_sequence);
            state.replay=replay;
            if(!replay.no_hit||replay.status!=='end_attack') {
                await fetch('/api/acceptance',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({wave,seed:plan.seed,suite:'canonical-model-replay-failure',plan,replay})});
                throw Error('原版验算失败：'+replay.status+'，HP '+replay.rows.at(-1).HP+'，KR '+replay.rows.at(-1).KR+'。已保存模型差异证据。');
            }
            const actions=Array.from({length:replay.frames},(_,i)=>plan.action_sequence[i]||[0,0]);
            const registered=await fetch('/api/oracle-plan',{method:'POST',headers:{'Content-Type':'application/json'},
                body:JSON.stringify({wave,seed:plan.seed,planner:plan.planner,result:{status:'candidate_found',actions,trajectory:replay.rows,end:replay.rows.at(-1),search_limited:plan.search_limited,
                    ms:plan.timing_ms?.first_route_wall,
                    computation:{initial:plan.initial,seed:plan.seed,margin:plan.margin,max_nodes:plan.max_nodes,lookahead:plan.lookahead,
                        ranking_weights:plan.ranking_weights,weights_affect_safety:plan.weights_affect_safety,
                        no_beam_pruning:plan.no_beam_pruning,margin_is_pruning:plan.margin_is_pruning,preferred_margin_satisfied:plan.preferred_margin_satisfied,retained_states:plan.retained_states,
                        expansions:plan.expansions,kernel_sha256:plan.kernel_sha256,csv_sha256:plan.csv_sha256,
                        route_cache_hit:plan.route_cache_hit,timing_ms:plan.timing_ms}}})});
            const candidate=await registered.json();
            if(!registered.ok) throw Error(candidate.error||'候选登记失败');
            show('replay_passed','原版单步验算通过；进入正常速度三轮 TAS 验收');
            const live=new URL(location.href);
            live.searchParams.delete('oracle');live.searchParams.delete('compute');
            live.searchParams.set('candidate',candidate.candidate_id);
            live.searchParams.set('acceptance','1');live.searchParams.set('continuous','1');
            if(!live.searchParams.has('compensate'))live.searchParams.set('compensate','1');
            location.replace(live.href);
        } catch(error) {state.error=String(error);show('failed',String(error));}
    },100);
})();

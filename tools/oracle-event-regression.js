// Load through CUA CDP in sans_bonestab3, seed42, oracle mode.
window.runOracleEventRegression=async()=>{
    const q=new URLSearchParams(location.search),o=window.EngineOracle;
    if(q.get('attack')!=='sans_bonestab3'||window.__TAS_SEED.seed!==42)throw Error('Regression wave or seed mismatch');
    const result=await o.solveEventPolicies({maxFrames:450,marginPx:1,budgetMs:10000});
    if(result.status!=='candidate_found'||result.frame!==378||result.settleFrames!==2)throw Error('Sustained jump route regression');
    const replay=await o.replay(result.actions);
    if(!replay.no_hit)throw Error('Independent original-engine replay took damage');
    return {status:result.status,frames:result.frame,hold:result.hold,marginPx:result.marginPx,
        solve_ms:result.ms,settleFrames:result.settleFrames,independent_replay_no_hit:replay.no_hit,attempts:result.attempts};
};

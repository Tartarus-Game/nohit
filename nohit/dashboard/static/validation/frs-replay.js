// Development verification only. Runs the original fixed-step oracle, never
// search, then registers its observed trajectory for separate real-time runs.
window.verifyFreshFRS = async function () {
    const solver = await fetch('/validation/frs-candidate-20261005.json').then(r => r.json());
    const O = window.EngineOracle;
    if (!O?.ready || O.busy || O.replaying || O.searching) throw Error('Oracle is not ready');
    if (solver.status !== 'candidate_found') throw Error('No fresh candidate');
    O.restore(O.initial);
    const trajectory = [O.observe()], microticks = [];
    let minClearance = 8;
    O.replaying = true;
    try {
        for (let frame = 0; frame < solver.actions.length && !O.ended; frame++) {
            const run = O.step(solver.actions[frame]);
            microticks.push(...run.rows);
            trajectory.push(run.end);
            if (!O.ended) {
                let low = 0, high = 8;
                for (let k = 0; k < 8; k++) {
                    const mid = (low + high) / 2;
                    if (O.hasClearance(mid)) low = mid; else high = mid;
                }
                minClearance = Math.min(minClearance, low);
            }
            if (frame % 60 === 0) await new Promise(resolve => setTimeout(resolve, 0));
        }
        const startHP = trajectory[0].HP;
        const passed = O.ended && trajectory.length === solver.actions.length + 1 &&
            microticks.every(r => r.HP === startHP && r.KR === 0);
        const report = {wave: solver.wave, seed: 42, clock:'original-runtime-fixed-240hz',
            source:'fresh-native-frs-candidate', original_replay_passed:passed,
            result:{passed, frames:trajectory.length - 1, microticks:microticks.length,
                start_hp:startHP, end_hp:trajectory.at(-1).HP, max_kr:Math.max(...microticks.map(r=>r.KR)),
                min_frame_boundary_clearance_px:minClearance},
            solver_configuration:{exact_state_folding:solver.exact_state_folding,
                max_beam:solver.max_beam, complete_search_configuration:solver.complete_search_configuration},
            plan:{actions:solver.actions}, trajectory, microtick_records:microticks};
        const savedResponse = await fetch('/api/acceptance', {method:'POST',
            headers:{'Content-Type':'application/json'}, body:JSON.stringify(report)});
        const saved = await savedResponse.json();
        if (!savedResponse.ok) throw Error(JSON.stringify(saved));
        if (!passed) return {passed:false, result:report.result, saved};
        const regResponse = await fetch('/api/oracle-plan', {method:'POST',
            headers:{'Content-Type':'application/json'}, body:JSON.stringify({wave:solver.wave, seed:42,
                planner:'native-frs-exact-folding-bounded-frontier',
                solver_configuration:report.solver_configuration,
                result:{status:'candidate_found', actions:solver.actions, trajectory,
                    end:trajectory.at(-1), ms:solver.timing_ms.search_including_load,
                    total_ms:solver.timing_ms.first_route_wall, expansions:solver.expansions}})});
        const registration = await regResponse.json();
        if (!regResponse.ok) throw Error(JSON.stringify(registration));
        O.draw();
        return {passed:true, result:report.result, saved, registration};
    } finally { O.replaying = false; }
};

// Run in the oracle page through CUA CDP Runtime.evaluate, passing the JSON
// fixture in tools/platforms4hard-regression.json. Uses only original ticks.
window.runOracleRegression = async function (fixture, policy = 'support') {
    const O = window.EngineOracle;
    const query = new URLSearchParams(location.search);
    if (query.get('attack') !== fixture.wave || window.__TAS_SEED.seed !== fixture.seed)
        throw Error('Regression wave or seed mismatch');
    const initial = O.initial;
    try {
        O.restore(initial);
        for (const action of fixture.prefix_actions) {
            const run = O.step(action);
            if (run.hit || run.end.KR !== 0) throw Error('Regression prefix changed');
        }
        O.initial = O.checkpoint();
        let result = await O.solve({ ...fixture.options, policy });
        while (result.status === 'budget_limit')
            result = await O.solve({ resume: true, budgetMs: fixture.options.budgetMs });
        const expected = fixture.fixed_expected;
        const passed = result.status === expected.status && result.frame === expected.frame;
        window.oracleRegressionResult = {
            policy, passed, status: result.status, frame: result.frame, ms: result.ms,
            expected, full_actions: fixture.prefix_actions.concat(result.actions)
        };
        if (!passed) throw Error('Original-engine regression: ' + JSON.stringify({ policy, status: result.status, frame: result.frame }));
        O.initial = initial;
        const replay = await O.replay(window.oracleRegressionResult.full_actions);
        if (!replay.no_hit) throw Error('Regression full-route replay took damage');
        window.oracleRegressionResult.independent_replay_no_hit = true;
        return window.oracleRegressionResult;
    } finally {
        O.initial = initial;
        O.restore(initial);
    }
};

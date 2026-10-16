// Test-only forward playback. No checkpoint restore or health modification.
window.realhellAppendVerifiedRoute = async function (routeUrl, endTick) {
    const route = await (await fetch(routeUrl, {cache: 'no-store'})).json();
    const runtime = document.getElementById('c2canvas').c2runtime;
    const controller = window.__CSV_TAS;
    const clock = window.__TAS_CLOCK;
    const record = window.__REALHELL_FORWARD;
    const observer = window.__CUSTOM_WAVE;
    if (!runtime.suspended || !record || record.mismatches.length)
        throw Error('Expected a paused, matching forward run');
    const stop = Math.min(endTick ?? route.actions.length, route.actions.length);
    const start = record.applied;
    const before = window.NoHitSolverState.capturePhysical(runtime);
    if (before.initial.some((v, i) => !Object.is(v, route.trajectory[start][i])))
        throw Error('Continuation does not match the current physical state');
    const keys = window.TASRunner.getKeyboardInstance().keyMap;
    const damageCount = () => observer.events.filter(e => e.fn.toLowerCase() === 'damageplayer').length;
    const initialDamageCount = damageCount();
    if (before.HP !== 92 || before.KR !== 0 || observer.firstDamage)
        throw Error('Forward run has already observed damage');
    record.route_frames = route.actions.length;
    record.last_route_url = routeUrl;
    for (let i = start; i < stop; ++i) {
        keys.fill(false);
        for (const [code, bit] of [[37, 1], [39, 2], [38, 4], [40, 8], [88, 16]])
            keys[code] = !!(route.actions[i] & bit);
        keys[90] = !!route.confirm_sequence?.[i];
        controller.status = 'diagnostic_forward_only';
        clock.stepping = true;
        try {
            runtime.tick(true, runtime.last_tick_time + clock.logicalStepMs, true);
        } finally {
            clock.stepping = false;
            controller.status = 'unknown';
        }
        const row = window.NoHitSolverState.capturePhysical(runtime);
        record.rows.push(row);
        record.applied = i + 1;
        const differences = row.initial.flatMap((v, j) =>
            Object.is(v, route.trajectory[i + 1][j]) ? [] : [{field: j, actual: v, expected: route.trajectory[i + 1][j]}]);
        if (row.HP !== 92 || row.KR !== 0 || observer.firstDamage || damageCount() !== initialDamageCount)
            differences.push({damage: true, HP: row.HP, KR: row.KR, firstDamage: observer.firstDamage});
        if (differences.length) {
            record.mismatches.push({route_tick: i + 1, native_tick: row.tick, differences});
            break;
        }
        if ((i + 1) % 240 === 0) await new Promise(resolve => setTimeout(resolve, 0));
    }
    const last = record.rows.at(-1);
    const label = document.getElementById('realhell-progress');
    if (label) label.textContent = [
        'Real HELL 削弱版 · 原游戏逐帧验证',
        '已执行 ' + (record.applied / 60).toFixed(2) + 's / ' + record.applied.toLocaleString() + '帧',
        'HP' + last.HP + ' · KR' + last.KR + ' · 伤害事件' + damageCount() + ' · 状态差异' + record.mismatches.length,
        '尚未确认整谱通关'
    ].join(String.fromCharCode(10));
    const paused = runtime.suspended;
    try { runtime.suspended = false; if (runtime.glwrap) runtime.drawGL(); else runtime.draw(); }
    finally { runtime.suspended = paused; }
    return {start, applied: record.applied, mismatches: record.mismatches, HP: last.HP, KR: last.KR,
        line: last.line, running: last.running, observerDone: observer.done, observerStatus: observer.status,
        terminalCertified: observer.terminalCertified, damageEvents: damageCount()};
};

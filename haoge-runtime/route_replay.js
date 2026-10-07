// Play a pre-solved, verified route instead of re-solving it.
//
// With `?route=<round>` the page fetches `routes/<round>.plan.json` and answers
// the controller's own `/api/solve-csv` request with that plan, so the normal
// playback path runs unchanged. Everything the controller validates still
// applies and is still checked against THIS run's live boundary: the CSV hash,
// the clock schedule hash, the dt prefix, the action/Confirm/trajectory shapes
// and the native EndAttack. Only `provenance.request_id` is rewritten, because
// that id is minted per request; the plan's own computation stays attributed to
// the request id it was produced under in `solver_request_id`.
//
// A stale or mismatched route therefore FAILS loudly instead of playing.
(() => {
    const query = new URLSearchParams(location.search);
    // Tolerate a playlist that carries the short round name: every published plan
    // is named `sans_<round>`, so normalise rather than silently 404.
    const requested = query.get('route');
    if (query.get('csvtas') !== '1' || !requested) return;
    const route = /^sans_/.test(requested) ? requested : 'sans_' + requested;
    if (!/^sans_[A-Za-z0-9_]+$/.test(route)) return;

    const R = window.__ROUTE_REPLAY = { route, requested, status: 'loading', error: null, plan: null };
    const decoder = new TextDecoder();

    function base64ToBytes(base64) {
        const binary = atob(base64);
        const bytes = new Uint8Array(binary.length);
        for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
        return bytes;
    }

    // The plan lives inside the game directory, not behind the dashboard API.
    const load = fetch('routes/' + route + '.plan.json', { cache: 'no-store' })
        .then(response => { if (!response.ok) throw Error('route ' + route + ' is not published'); return response.json(); })
        .then(plan => {
            R.plan = plan;
            R.solver_request_id = plan.provenance && plan.provenance.request_id;
            R.status = 'ready';
            return plan;
        })
        .catch(error => { R.status = 'failed'; R.error = String(error); throw error; });
    window.__ROUTE_REPLAY_READY = load.catch(() => null);

    const original = window.fetch;
    window.fetch = function (input, init) {
        let url = '';
        try { url = typeof input === 'string' ? input : (input && input.url) || ''; } catch (_) {}
        if (url.indexOf('/api/solve-csv') < 0 || !init || !init.body) {
            return original.apply(this, arguments);
        }
        return load.then(plan => {
            const request = JSON.parse(typeof init.body === 'string' ? init.body : decoder.decode(init.body));
            const answer = Object.assign({}, plan, {
                provenance: Object.assign({}, plan.provenance, { request_id: request.request_id }),
                replay: { cached_route: route, solver_request_id: R.solver_request_id,
                    note: 'verified route replayed; every field re-validated against this run' },
            });
            R.status = 'replaying';
            const badge = document.getElementById('tas-status-badge');
            if (badge) badge.textContent = '回放已验证路线 ' + route + '（' + (answer.actions || []).length + ' 步）';
            return new Response(JSON.stringify(answer),
                { status: 200, headers: { 'Content-Type': 'application/json' } });
        }).catch(error => {
            R.status = 'failed'; R.error = String(error);
            return new Response(JSON.stringify({ error: 'route replay unavailable: ' + error, status: 'unknown' }),
                { status: 502, headers: { 'Content-Type': 'application/json' } });
        });
    };

    // Continuous demonstration: `playlist=<round>:<sourceId>|<round>:<sourceId>|...`
    // holds the rounds still to play, in the game's own attack order. When this
    // round reaches a terminal state the page shows the result for a moment and
    // then walks to the next entry, so one recording covers the whole run without
    // anybody touching the keyboard.
    const playlist = query.get('playlist');
    if (!playlist) return;
    const remaining = playlist.split('|').filter(Boolean).map(entry => {
        const [round, sourceId] = entry.split(':');
        return { round, sourceId };
    });
    if (!remaining.length) return;

    const panel = document.createElement('div');
    panel.id = 'demo-playlist';
    panel.style = 'position:fixed;top:8px;left:50%;transform:translateX(-50%);z-index:1000000;'
        + 'background:#122030ee;color:#e6edf3;padding:8px 16px;border-radius:8px;'
        + 'font:13px/1.5 "Segoe UI",system-ui,sans-serif;text-align:center;pointer-events:none';
    const showPanel = (html, tone) => {
        panel.innerHTML = `<span style="color:${tone || '#e6edf3'}">${html}</span>`
            + '<br><span style="color:#8b949e;font-size:11px">'
            + (window.NoHitDemo && window.NoHitDemo.enabled ? window.NoHitDemo.label : '严格无伤模式')
            + ' · 剩余 ' + Math.max(0, remaining.length - 1) + ' 回合</span>';
    };
    const status = () => (window.__CSV_TAS && window.__CSV_TAS.status) || null;
    let advanced = false;
    let sawProgress = false;
    const FAILED = ['failed', 'unknown', 'cancelled'];

    function finish(entry, tone, text) {
        if (advanced) return;
        advanced = true;
        showPanel(text, tone);
        const rest = remaining.slice(1);
        if (!rest.length) { showPanel('<b>全部回合播放完毕</b>', '#3fb950'); return; }
        const next = rest[0];
        setTimeout(() => {
            location.href = location.pathname + '?csvtas=1&csv_source=' + next.sourceId
                + '&route=' + next.round + '&attack=custom&custom_acceptance=1&seed=42&fps=30'
                + '&demo=' + (window.NoHitDemo && window.NoHitDemo.enabled ? '1' : '0')
                + '&playlist=' + encodeURIComponent(rest.map(r => r.round + ':' + r.sourceId).join('|'));
        }, entry.pauseMs);
    }

    function watch() {
        const state = window.__CSV_TAS;
        if (!state) { setTimeout(watch, 300); return; }
        const now = state.status;
        const applied = state.actionsApplied || 0;
        // `playing`/`solving` and any applied input prove the round really started.
        // A first poll that lands after the round is already running must NOT be
        // read as "it never started" -- that misfire stopped the run outright.
        if (now === 'playing' || now === 'solving' || applied > 0) sawProgress = true;

        if (now === 'completed') {
            const hit = state.firstDamage ? ` · 掉血 tick ${state.firstDamage.tick}` : ' · 未掉血';
            const tail = state.openLoop ? '（分叉后开环打完）' : '';
            finish({ pauseMs: 5000 }, state.openLoop ? '#d29922' : '#3fb950',
                `<b>${route}</b> 完成${hit} · 已执行 ${applied} 步${tail}`);
            return;
        }
        if (now === 'waiting_source' || now === 'waiting_start' || now === 'solving' || now === 'playing') {
            if (state.openLoop) {
                // The controller keeps driving the planned keys after the real game
                // diverged; it is no longer a verified tail, so the banner says so.
                showPanel(`<b>${route}</b> 真机分叉，开环继续操作 · 已执行 ${applied} 步`, '#d29922');
            } else {
                const phase = now === 'solving' ? '装载路线' : now === 'playing' ? '执行输入' : '等待入口';
                showPanel(`正在播放 <b>${route}</b> · ${phase} · 已执行 ${applied} 步`);
            }
        }
        // A failure before the round ever produced a step means the replay itself
        // was rejected (route/boundary mismatch). That is reported and stops the
        // run: it is a real problem, not something to skip past silently.
        if (!sawProgress && FAILED.indexOf(now) >= 0) {
            const why = state.error || window.__ROUTE_REPLAY?.error || 'unknown';
            showPanel(`<b>${route}</b> 未能开始（状态 ${now}）<br>${why}`, '#f85149');
            return;
        }
        if (FAILED.indexOf(now) >= 0) {
            // The controller switches itself to the open loop on divergence, so a
            // failure past the start means something it could not recover from.
            finish({ pauseMs: 4000 }, '#f85149',
                `<b>${route}</b> 中断（${now}）：${state.error || '未知原因'} · 已执行 ${applied} 步`);
            return;
        }
        setTimeout(watch, 500);
    }
    document.body.appendChild(panel);
    watch();
})();

/**
 * Real-browser end-to-end verification over CDP
 * =============================================
 * Drives the actual Chrome instance against the dashboard-served game page and
 * verifies, in the browser's own JS engine, that:
 *
 *   A. http://127.0.0.1:<port>/game/index.html loads the real Construct 2 export
 *      together with tas_runner.js, with no page errors;
 *   B. both engine hooks are installed on the live Runtime prototype;
 *   C. an OnFunction("RunAttack") emitted through the engine's own
 *      window.c2_callFunction is observed and the optimal route is fetched;
 *   D. the real PlayerHeart instance is located and its centre maps onto the
 *      solver's arena frame;
 *   E. real Runtime.prototype.tick() drives the plan, and the real
 *      Keyboard.keyMap receives the injected input.
 *
 * Usage: node tools/browser_e2e.mjs [httpPort] [cdpPort] [wave]
 */

import fs from "node:fs";

const HTTP_PORT = process.argv[2] || "8099";
const CDP_PORT = process.argv[3] || "9222";
const WAVE = process.argv[4] || "sans_bonegap1";
const PAGE_URL = `http://127.0.0.1:${HTTP_PORT}/game/index.html`;

let failures = 0;
let checks = 0;
function check(name, cond, detail = "") {
    checks++;
    if (cond) console.log(`  \u2713 ${name}`);
    else {
        failures++;
        console.log(`  \u2717 ${name}${detail ? " \u2014 " + detail : ""}`);
    }
}
const section = (t) => console.log(`\n${t}`);

// ---------------------------------------------------------------------------
// Minimal CDP client over the built-in WebSocket
// ---------------------------------------------------------------------------
class CDP {
    constructor(wsUrl) {
        this.ws = new WebSocket(wsUrl);
        this.id = 0;
        this.pending = new Map();
        this.events = [];
        this.ready = new Promise((resolve, reject) => {
            this.ws.addEventListener("open", () => resolve());
            this.ws.addEventListener("error", (e) => reject(new Error("ws error: " + (e.message || e.type))));
        });
        this.ws.addEventListener("message", (ev) => {
            let msg;
            try { msg = JSON.parse(ev.data); } catch { return; }
            if (msg.id !== undefined && this.pending.has(msg.id)) {
                const { resolve, reject } = this.pending.get(msg.id);
                this.pending.delete(msg.id);
                if (msg.error) reject(new Error(JSON.stringify(msg.error)));
                else resolve(msg.result);
            } else if (msg.method) {
                this.events.push(msg);
            }
        });
    }
    send(method, params = {}, sessionId) {
        const id = ++this.id;
        const payload = { id, method, params };
        if (sessionId) payload.sessionId = sessionId;
        this.ws.send(JSON.stringify(payload));
        return new Promise((resolve, reject) => {
            this.pending.set(id, { resolve, reject });
            setTimeout(() => {
                if (this.pending.has(id)) {
                    this.pending.delete(id);
                    reject(new Error(`CDP timeout: ${method}`));
                }
            }, 30000);
        });
    }
    close() { try { this.ws.close(); } catch {} }
}

async function httpJson(pathname) {
    const res = await fetch(`http://127.0.0.1:${CDP_PORT}${pathname}`);
    return res.json();
}

// ---------------------------------------------------------------------------
section("[A] Chrome / CDP");
let version;
try {
    version = await httpJson("/json/version");
} catch (err) {
    console.log(`  \u2717 cannot reach CDP on ${CDP_PORT}: ${err}`);
    process.exit(1);
}
check("Chrome DevTools endpoint reachable", !!version.Browser, version.Browser);
console.log(`    ${version.Browser} / ${version["User-Agent"]}`);

const targets = await httpJson("/json/list");
let pageTarget = targets.find((t) => t.type === "page");
if (!pageTarget) {
    const created = await fetch(`http://127.0.0.1:${CDP_PORT}/json/new?about:blank`, { method: "PUT" }).then((r) => r.json());
    pageTarget = created;
}
check("a page target is available", !!pageTarget && !!pageTarget.webSocketDebuggerUrl);

const cdp = new CDP(pageTarget.webSocketDebuggerUrl);
await cdp.ready;

const { sessionId } = await cdp.send("Target.attachToTarget", { targetId: pageTarget.id, flatten: true });
const send = (m, p) => cdp.send(m, p, sessionId);

await send("Runtime.enable");
await send("Log.enable");
await send("Page.enable");
await send("Network.enable");

const consoleLogs = [];
const pageErrors = [];
cdp.ws.addEventListener("message", (ev) => {
    let msg;
    try { msg = JSON.parse(ev.data); } catch { return; }
    if (msg.method === "Runtime.consoleAPICalled") {
        const text = (msg.params.args || [])
            .map((a) => (a.value !== undefined ? String(a.value) : (a.description || a.type)))
            .join(" ");
        consoleLogs.push({ level: msg.params.type, text });
    } else if (msg.method === "Runtime.exceptionThrown") {
        const d = msg.params.exceptionDetails;
        pageErrors.push(d.exception ? (d.exception.description || d.exception.value) : d.text);
    } else if (msg.method === "Log.entryAdded" && msg.params.entry.level === "error") {
        pageErrors.push(msg.params.entry.text);
    }
});

// ---------------------------------------------------------------------------
section("[B] Page load");
const evalJs = async (expression, awaitPromise = false) => {
    const res = await send("Runtime.evaluate", {
        expression,
        awaitPromise,
        returnByValue: true,
        allowUnsafeEvalBlockedByCSP: true,
    });
    if (res.exceptionDetails) {
        const d = res.exceptionDetails;
        throw new Error(d.exception ? (d.exception.description || d.exception.value) : d.text);
    }
    return res.result.value;
};

await send("Page.navigate", { url: PAGE_URL });
await new Promise((r) => setTimeout(r, 4000));

// Wait for the runner to be mounted AND for its own initial /api/tas fetch to
// settle. Without this the harness can fire RunAttack while the previous page's
// (or the default wave's) route is still in flight, and the assertions below
// would measure a stale arena frame rather than a bug.
let ready = false;
for (let i = 0; i < 40; i++) {
    const s = await evalJs(`(() => {
        const T = window.TASRunner;
        if (!T) return { mounted: false };
        const st = T.getState();
        return { mounted: true, actionCount: st.actionCount, wave: st.currentWave, arena: !!st.arena };
    })()`).catch(() => ({ mounted: false }));
    if (s.mounted && s.actionCount > 0 && s.arena) { ready = true; break; }
    await new Promise((r) => setTimeout(r, 500));
}
check("runner mounted and initial route settled before driving", ready);


const title = await evalJs("document.title");
check("page loaded with the game title", /bad time|sans/i.test(String(title)), String(title));

const hasRuntime = await evalJs("!!(window.cr && window.cr.runtime)");
check("c2runtime.js evaluated in the browser (window.cr.runtime)", hasRuntime === true);

const runnerMounted = await evalJs("!!window.TASRunner");
check("tas_runner.js mounted in the browser (window.TASRunner)", runnerMounted === true);

const runnerLogs = consoleLogs.filter((l) => /TAS (Runner|Auto-Pilot|Engine)/.test(l.text));
check("runner emitted its boot logs to the browser console", runnerLogs.length >= 2, `${runnerLogs.length} lines`);
for (const l of runnerLogs.slice(0, 6)) console.log(`    \u203a ${l.text}`);

// ---------------------------------------------------------------------------
section("[C] Live runtime hooks");
const hookState = await evalJs(`(() => {
    const T = window.TASRunner;
    const rt = window.c2runtime || (document.getElementById('c2canvas') || {}).c2runtime;
    const proto = rt && rt.constructor && rt.constructor.prototype;
    return {
        hasRuntimeInstance: !!rt,
        triggerHooked: !!(proto && proto.__tasWrapped),
        tickHooked: !!(proto && proto.__tasTickWrapped),
        runnerSaysTickHooked: T.isTickHooked(),
        keyboardFound: !!T.getKeyboardInstance(),
    };
})()`);
check("live Runtime instance reachable", hookState.hasRuntimeInstance === true);
check("Runtime.prototype.trigger hooked in the browser", hookState.triggerHooked === true);
check("Runtime.prototype.tick hooked in the browser", hookState.tickHooked === true);
check("real Keyboard plugin instance located", hookState.keyboardFound === true);

// ---------------------------------------------------------------------------
section("[D] Real OnFunction bus -> level detection -> optimal route");
// IMPORTANT: Battle.xml maps `RunAttack(<index>)` to
// `TLPlay(AttackList.Get(Function.Param(0)))`, so the parameter is an INDEX into
// the AttackList array, not a file name. The authoritative signal for "which
// script is actually playing" is therefore the TLPlay argument, which the
// runner's trigger hook observes.
const attackResult = await evalJs(`(async () => {
    if (typeof window.c2_callFunction !== 'function') return { error: 'no c2_callFunction' };
    const target = '${WAVE}';
    const rt = window.c2runtime || document.getElementById('c2canvas').c2runtime;

    // Resolve the AttackList index the way the game's own menu does.
    let idx = -1;
    const list = rt.attackList || rt.AttackList || (window.cr && cr.attackList);
    if (list && typeof list.At === 'function') {
        for (let i = 0; i < 128; i++) {
            const n = list.At(i);
            if (n === undefined || n === null || n === '') break;
            if (String(n).replace(/\\.csv$/i, '') === target) { idx = i; break; }
        }
    }

    if (idx >= 0) {
        window.c2_callFunction('RunAttack', [idx]);
    } else {
        // Fall back to what RunAttack itself calls: TLPlay takes the name.
        window.c2_callFunction('TLPlay', [target]);
    }
    await new Promise(r => setTimeout(r, 3500));
    const s = window.TASRunner.getState();
    return {
        idx,
        listFound: !!list,
        wave: s.currentWave,
        actionCount: s.actionCount,
        physicsMode: s.physicsMode,
        arena: s.arena,
    };
})()`, true);
check(
    "RunAttack/TLPlay observed through the real trigger path",
    attackResult.wave === WAVE + ".csv",
    JSON.stringify(attackResult).slice(0, 240)
);
check("optimal route fetched from /api/tas", attackResult.actionCount > 0, `actionCount=${attackResult.actionCount}`);
check("physics mode is c2", attackResult.physicsMode === "c2", String(attackResult.physicsMode));
check("arena absolute frame present", !!attackResult.arena, JSON.stringify(attackResult.arena));

const arena = attackResult.arena;
const apiState = await fetch(`http://127.0.0.1:${HTTP_PORT}/api/tas?wave=${WAVE}.csv&T=150&soul_w=4&soul_h=4&physics_mode=c2`).then((r) => r.json());
check(
    "browser arena frame equals the API arena frame",
    arena && arena.c2_left === apiState.arena.c2_left && arena.c2_floor === apiState.arena.c2_floor,
    `${JSON.stringify(arena)} vs ${JSON.stringify(apiState.arena)}`
);

// ---------------------------------------------------------------------------
section("[E] Real PlayerHeart + input injection");
const heartProbe = await evalJs(`(() => {
    const T = window.TASRunner;
    const heart = T.getHeartInstance();
    const pos = T.getHeartPos();
    return {
        found: !!heart,
        typeName: heart ? heart.type.name : null,
        x: heart ? heart.x : null,
        y: heart ? heart.y : null,
        local: pos ? { x: pos.x, y: pos.y } : null,
    };
})()`);
check("real PlayerHeart instance located in the browser", heartProbe.found === true, JSON.stringify(heartProbe));
check("located type is the minified t55 sprite", heartProbe.typeName === "t55", String(heartProbe.typeName));
check(
    "heart centre converted through the live arena frame",
    heartProbe.local && Math.abs(heartProbe.local.x - (heartProbe.x - arena.c2_left)) < 1e-6 &&
        Math.abs(heartProbe.local.y - (arena.c2_floor - heartProbe.y)) < 1e-6,
    JSON.stringify(heartProbe.local)
);

// Force the heart onto the plan's current reference frame each step, arm
// playback, and drive real engine ticks. The browser is sitting on the
// MainMenu layout (no attack running), so the engine does not move the heart
// itself -- we emulate the 5 px/frame walk that PlayerHeart performs while a
// direction key is held. What this verifies is the wiring: the closed-loop
// controller picks the right direction, writes it into the real
// Keyboard.keyMap, and the real Runtime.prototype.tick advances the plan.
const driveResult = await evalJs(`(async () => {
    const T = window.TASRunner;
    const rt = window.c2runtime || document.getElementById('c2canvas').c2runtime;
    const kb = T.getKeyboardInstance();
    const heart = T.getHeartInstance();
    const arena = T.getArena();
    const st = await fetch('/api/tas?wave=${WAVE}.csv&T=150&soul_w=4&soul_h=4&physics_mode=c2').then(r => r.json());
    const traj = st.trajectory;
    T.startPlayback();
    await new Promise(r => setTimeout(r, 200));
    const before = T.getState().plannedFrame;
    let sawDirection = false;
    let sawRelease = false;
    let maxAbsDrift = 0;
    for (let i = 0; i < 45; i++) {
        // Pin the heart to the plan's current reference frame (engine walk).
        const idx = Math.min(T.getState().plannedFrame, traj.length - 1);
        heart.x = arena.c2_left + traj[idx][0];
        heart.y = arena.c2_floor - traj[idx][1];
        rt.tick(false, performance.now(), false);
        if (kb.keyMap[37] || kb.keyMap[39] || kb.keyMap[65] || kb.keyMap[68]) sawDirection = true;
        else sawRelease = true;
        // The engine walk happens after the control decision.
        const step = (kb.keyMap[39] || kb.keyMap[68]) ? 5 : ((kb.keyMap[37] || kb.keyMap[65]) ? -5 : 0);
        heart.x += step;
        maxAbsDrift = Math.max(maxAbsDrift, Math.abs(T.getState().drift.dx));
    }
    const after = T.getState().plannedFrame;
    const localAfter = T.getHeartPos();
    const tlRunning = T.getTimelineRunning();
    T.resetPlayback();
    return {
        advanced: after - before,
        sawDirection,
        sawRelease,
        maxAbsDrift,
        localAfter: localAfter ? { x: localAfter.x, y: localAfter.y } : null,
        initial: st.initial_state,
        timelineRunning: tlRunning,
    };
})()`, true);

check("playback armed and the real tick advanced the plan", driveResult.advanced >= 45, JSON.stringify(driveResult).slice(0, 200));
check("real Keyboard.keyMap received injected direction keys", driveResult.sawDirection === true);
check("idle plan frames hard-release every key", driveResult.sawRelease === true);
check(
    "on-plan heart stays inside the drift deadzone in the live browser",
    driveResult.maxAbsDrift <= 3,
    `max|dx|=${driveResult.maxAbsDrift}`
);
check(
    "Timeline.Running read from the MainMenu layout (no attack active => 0/false)",
    driveResult.timelineRunning === 0 || driveResult.timelineRunning === false || driveResult.timelineRunning === null,
    `timelineRunning=${JSON.stringify(driveResult.timelineRunning)}`
);

// ---------------------------------------------------------------------------
section("[F] Console health");
// Errors that come from the third-party ad/analytics host page, not from the
// game or the TAS runner. Everything else is a real failure.
const HOST_PAGE_NOISE =
    /ysdk|ShowAd|favicon|net::ERR_|adsbygoogle|googletagmanager|google-analytics|Failed to load resource|EncodingError|Unable to decode audio|doubleclick|Content Security Policy|child-src|frame-src/i;
const relevantErrors = pageErrors.filter((e) => !HOST_PAGE_NOISE.test(String(e)));
const tasErrors = consoleLogs.filter((l) => l.level === "error" && /TAS/.test(l.text));
check("no page exceptions unrelated to the ad host page", relevantErrors.length === 0, relevantErrors.slice(0, 3).join(" | "));
check("no TAS runner error logs", tasErrors.length === 0, tasErrors.slice(0, 3).map((l) => l.text).join(" | "));

console.log(`\n${checks - failures}/${checks} checks passed`);
const report = { checks, failures, consoleLogs, pageErrors, attackResult, heartProbe, driveResult };
fs.writeFileSync(
    new URL("./.browser_e2e_report.json", import.meta.url),
    JSON.stringify(report, null, 2),
    "utf8"
);
cdp.close();
process.exit(failures === 0 ? 0 : 1);

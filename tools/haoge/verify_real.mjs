/**
 * Real-game TAS acceptance batch.
 *
 * For each named round: register its CSV as an immutable source, open the
 * instrumented haoge build's Custom entry with the same clock the route was
 * solved under, let the driver capture the boundary, solve, and execute the
 * route tick by tick in the real runtime while the independent observer records
 * HP/KR on every native tick.
 *
 * The page owns the evidence (it POSTs to /api/acceptance itself); this batch
 * only reports the terminal status per round and writes a compact summary.
 *
 * Usage: node verify_real.mjs --cdp 9333 --http 8160 --rounds a,b,c --out <file>
 */
import fs from "node:fs";
import path from "node:path";

function arg(name, fallback) {
    const i = process.argv.indexOf("--" + name);
    return i >= 0 ? process.argv[i + 1] : fallback;
}
const CDP_PORT = Number(arg("cdp", "9333"));
const HTTP_PORT = Number(arg("http", "8160"));
const GAME_DIR = arg("game-dir", "haoge-runtime");
const ROUNDS = arg("rounds", "").split(",").filter(Boolean);
const OUT = arg("out", "scratch/haoge-run/real-verification.json");
const WIDTH = arg("width", "1200");
const SECONDS = arg("seconds", "120");
const FPS = arg("fps", "30");
const PER_ROUND_TIMEOUT = Number(arg("per-round-timeout", "420"));
// --route-mode replays the published, verified plan instead of re-solving. The
// page still validates that plan against this run's live boundary, so a route
// that does not belong to this entry fails instead of playing.
const ROUTE_MODE = arg("route-mode", "0") === "1";

const list = await (await fetch(`http://127.0.0.1:${CDP_PORT}/json/list`)).json();
const page = list.find((t) => t.type === "page");
if (!page) throw new Error("no page target on CDP " + CDP_PORT);

const ws = new WebSocket(page.webSocketDebuggerUrl);
let id = 0; const pending = new Map();
const send = (method, params = {}, sessionId) => {
    const mid = ++id;
    ws.send(JSON.stringify(sessionId ? { id: mid, method, params, sessionId } : { id: mid, method, params }));
    return new Promise((res, rej) => {
        pending.set(mid, { res, rej });
        setTimeout(() => { if (pending.delete(mid)) rej(new Error("timeout " + method)); }, 60000);
    });
};
ws.onmessage = (ev) => {
    let m; try { m = JSON.parse(ev.data); } catch { return; }
    if (m.id !== undefined && pending.has(m.id)) {
        const { res, rej } = pending.get(m.id); pending.delete(m.id);
        m.error ? rej(new Error(JSON.stringify(m.error))) : res(m.result);
    }
};
await new Promise((r, j) => { ws.onopen = r; ws.onerror = () => j(new Error("ws error")); });

const { sessionId } = await send("Target.attachToTarget", { targetId: page.id, flatten: true });
await send("Page.enable", {}, sessionId);
await send("Runtime.enable", {}, sessionId);
await send("Network.enable", {}, sessionId);
await send("Network.setCacheDisabled", { cacheDisabled: true }, sessionId);
await send("Target.activateTarget", { targetId: page.id });

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const evaluate = async (expression) => {
    try {
        const r = await send("Runtime.evaluate", { expression, returnByValue: true, awaitPromise: false }, sessionId);
        if (r.exceptionDetails) return null;
        return r.result.value;
    } catch { return null; }
};

const PROBE = `(() => {
  const T=window.__CSV_TAS, W=window.__CUSTOM_WAVE, B=window.__CSV_SOURCE_BRIDGE;
  return JSON.stringify({
    bridge: B && B.status, bridgeError: B && B.error, bridgeAjax: B && B.ajaxResolution,
    status: T && T.status, error: T && T.error,
    actionsApplied: T && T.actionsApplied,
    plan: T && T.plan ? {status:T.plan.status, reason:T.plan.reason, actions:(T.plan.actions||[]).length,
      reached_tick:T.plan.reached_tick, game_seconds:T.plan.game_seconds, verified:T.plan.verified,
      physics_hz:T.plan.physics_hz, clock_start_ms:T.plan.clock_start_ms,
      original_replay_passed:T.plan.original_replay_passed} : null,
    custom: W ? {status:W.status, ticks:W.ticks&&W.ticks.length, rows:W.rows&&W.rows.length,
      firstDamage:W.firstDamage && {tick:W.firstDamage.tick,HP:W.firstDamage.HP,KR:W.firstDamage.KR,source:W.firstDamage.source,line:W.firstDamage.line,args:W.firstDamage.args},
      krInjections:(W.krInjections||[]).length, krDetail:(W.krInjections||[]).slice(0,8),
      errors:W.errors, eofObserved:W.eofObserved,
      terminalCertified:W.terminalCertified, saved:W.saved,
      csv_sha256:W.csv_sha256, entry:W.entry ? {tick:W.entry.tick,HP:W.entry.HP,KR:W.entry.KR} : null,
      lastRow:W.rows&&W.rows.length ? (()=>{const r=W.rows[W.rows.length-1];
        return {tick:r.tick,HP:r.HP,KR:r.KR,state:r.state};})() : null,
      // A.ticks is one [tick,HP,KR,SimulatorMode,keymask,confirm,line,T,running,hazards]
      // row per native tick -- the frame-by-frame no-damage record.
      minHP:(W.ticks||[]).reduce((m,t)=>Math.min(m,t[1]),Infinity),
      maxKR:(W.ticks||[]).reduce((m,t)=>Math.max(m,t[2]),0),
      tickSpan:(W.ticks||[]).length>1?[W.ticks[0][0],W.ticks[W.ticks.length-1][0]]:null,
      tickGaps:(W.ticks||[]).filter((t,i,a)=>i>0&&t[0]!==a[i-1][0]+1).length,
      eofSnapshot:W.eofSnapshot ? {tick:W.eofSnapshot.tick,HP:W.eofSnapshot.HP,KR:W.eofSnapshot.KR} : null} : null,
    baseline: window.NoHitBaseline ? window.NoHitBaseline.value : null,
    criterion: window.NoHitBaseline ? window.NoHitBaseline.criterion : null,
    seed: window.__TAS_SEED && window.__TAS_SEED.seed,
    clock: window.__TAS_CLOCK ? {mode:window.__TAS_CLOCK.mode, physicsHz:window.__TAS_CLOCK.physicsHz,
      logicalStepMs:window.__TAS_CLOCK.logicalStepMs} : null,
  });
})()`;

/** Full observer record for the evidence file (bulk vectors kept as-is; the
 *  observer already stores one row per native tick). */
const FULL = `(() => { const W=window.__CUSTOM_WAVE; if(!W) return null;
  try { return JSON.stringify(W); } catch(e) { return JSON.stringify({serializeError:String(e),
    status:W.status, ticks:(W.ticks||[]).length}); } })()`;

const terminal = new Set(["completed", "failed", "cancelled", "unknown"]);

async function register(file) {
    const body = JSON.stringify({ csv_path: path.resolve(GAME_DIR, file) });
    const res = await fetch(`http://127.0.0.1:${HTTP_PORT}/api/csv-source`, {
        method: "POST", headers: { "Content-Type": "application/json" }, body });
    if (!res.ok) throw new Error(`register ${file}: ${res.status}`);
    return (await res.json()).id;
}

const summary = [];
async function runRound(round, sourceId) {
    const url = `http://127.0.0.1:${HTTP_PORT}/game/index.html?csvtas=1&csv_source=${sourceId}`
        + `&attack=custom&custom_acceptance=1&seed=42&fps=${FPS}&seconds=${SECONDS}&width=${WIDTH}&max_ticks=40000`
        + (ROUTE_MODE ? `&route=${round}` : "");
    const started = Date.now();
    await send("Page.navigate", { url }, sessionId);
    let probe = null;
    let lastProgress = Date.now();
    let lastKey = "";
    while ((Date.now() - started) / 1000 < PER_ROUND_TIMEOUT) {
        await sleep(3000);
        const raw = await evaluate(PROBE);
        if (!raw) continue;
        probe = JSON.parse(raw);
        if (probe.status && terminal.has(probe.status)) break;
        // The bridge can declare itself ready while the page never starts ticking
        // (a stale document from the previous round). Re-navigate once rather than
        // burning the whole round timeout on a dead document.
        const key = `${probe.status}/${probe.custom && probe.custom.status}/${probe.actionsApplied}`;
        if (key !== lastKey) { lastKey = key; lastProgress = Date.now(); }
        if (probe.status === "waiting_source" && Date.now() - lastProgress > 35000 &&
            Date.now() - started > 40000) {
            await send("Page.navigate", { url }, sessionId);
            lastProgress = Date.now();
        }
    }
    return { probe, elapsed: (Date.now() - started) / 1000 };
}

for (const round of ROUNDS) {
    const file = round + ".csv";
    const record = { round, started: new Date().toISOString() };
    try {
        const sourceId = await register(file);
        const { probe, elapsed } = await runRound(round, sourceId);
        await sleep(4000);   // let the page flush its own evidence POST
        record.elapsed_seconds = elapsed;
        record.summary = probe;
        const c = (probe && probe.custom) || {};
        record.passed = !!(probe && c.ticks > 0 && !c.firstDamage &&
            (c.status === "incomplete_eof" || c.status === "completed"));
        // Persist the observer's own per-tick record next to the summary so the
        // no-damage claim can be re-checked without re-running the browser.
        const raw = await evaluate(FULL);
        if (raw) {
            const evidenceDir = path.join(path.dirname(OUT), "real-evidence");
            fs.mkdirSync(evidenceDir, { recursive: true });
            fs.writeFileSync(path.join(evidenceDir, round + ".observer.json"), raw, "utf-8");
            record.evidence = path.posix.join(path.dirname(OUT), "real-evidence", round + ".observer.json");
        }
        console.log(`${round.padEnd(24)} csvtas=${probe && probe.status} custom=${c.status} ` +
            `applied=${probe && probe.actionsApplied} ticks=${c.ticks} minHP=${c.minHP} maxKR=${c.maxKR} ` +
            `damage=${c.firstDamage ? "YES@" + c.firstDamage.tick : "none"} kr=${c.krInjections || 0} ${elapsed.toFixed(0)}s`);
    } catch (error) {
        record.error = String(error);
        console.log(`${round.padEnd(24)} HARNESS ERROR ${error}`);
    }
    summary.push(record);
    fs.writeFileSync(OUT, JSON.stringify(summary, null, 2), "utf-8");
}
const ok = summary.filter((r) => r.passed).length;
console.log(`\nreal-game no-damage completed rounds: ${ok}/${summary.length} -> ${OUT}`);
ws.close();

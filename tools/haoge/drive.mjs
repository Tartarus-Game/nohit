/**
 * CDP driver for the nohit engine's real-game TAS entry.
 *
 * Usage:
 *   node drive.mjs --cdp 9333 --url "<game url>" --out <result.json>
 *                  [--timeout 1800] [--poll 2000] [--label "<text>"]
 *
 * Connects to an already-running Chrome started with --remote-debugging-port,
 * opens the URL in a page target, polls the in-page state objects that the
 * instrumented game installs (__CSV_TAS / __CUSTOM_WAVE / __CAMPAIGN /
 * __FULL_GAME / __CSV_SOURCE_BRIDGE / __TAS_CLOCK), and on a terminal state
 * writes a compact JSON summary plus every console error seen.
 *
 * The page itself persists the heavyweight evidence through /api/acceptance;
 * this driver never fabricates or edits that evidence.
 */
import fs from "node:fs";

function arg(name, fallback) {
    const i = process.argv.indexOf("--" + name);
    return i >= 0 ? process.argv[i + 1] : fallback;
}

const CDP_PORT = Number(arg("cdp", "9333"));
const URL_ = arg("url", null);
const OUT = arg("out", "result.json");
const TIMEOUT_S = Number(arg("timeout", "1800"));
const POLL_MS = Number(arg("poll", "2000"));
const LABEL = arg("label", "");

if (!URL_) { console.error("--url is required"); process.exit(2); }

const PROBE = `(() => {
  const S = (v) => (v === undefined ? null : v);
  const T = window.__CSV_TAS, C = window.__CAMPAIGN, F = window.__FULL_GAME, W = window.__CUSTOM_WAVE;
  const B = window.__CSV_SOURCE_BRIDGE, K = window.__TAS_CLOCK;
  const plan = T && T.plan;
  let boundary = null;
  try {
    const b = T && T.boundary;
    if (b) boundary = {tick: b.tick, HP: b.HP, KR: b.KR, x: b.x, y: b.y,
      SimulatorMode: b.SimulatorMode, HitAttempts: b.HitAttempts,
      arena: b.arena ? {target: b.arena.target, size: b.arena.size, speed: b.arena.speed} : null};
  } catch (e) { boundary = 'probe_error:' + e; }
  return JSON.stringify({
    href: location.search,
    clock: K ? {mode: K.mode, physicsHz: K.physicsHz, stepping: S(K.stepping), enabled: S(K.enabled)} : null,
    bridge: B ? {status: B.status, error: B.error} : null,
    csvtas: T ? {status: T.status, error: T.error, source_entered: S(T.source_entered),
        request_recipe: S(T.request_recipe), solve_timing: S(T.solve_timing),
        actionsApplied: S(T.actionsApplied), events: S(T.events),
        plan: plan ? {status: plan.status, reason: plan.reason, verified: plan.verified,
            reached_tick: plan.reached_tick, physics_hz: S(plan.physics_hz),
            actions: plan.actions ? plan.actions.length : null,
            game_seconds: S(plan.game_seconds), wall_seconds: S(plan.wall_seconds),
            original_replay_passed: S(plan.original_replay_passed)} : null,
        boundary} : null,
    custom: W ? {status: W.status, done: W.done, started: W.started,
        ticks: W.ticks ? W.ticks.length : null, rows: W.rows ? W.rows.length : null,
        firstDamage: W.firstDamage, errors: W.errors, eofObserved: S(W.eofObserved),
        terminalCertified: S(W.terminalCertified), stopReason: S(W.stopReason),
        recordPromise: !!W.recordPromise, saved: S(W.saved)} : null,
    campaign: C ? {status: C.status, error: C.error, planCount: C.plans ? C.plans.length : null,
        plans: (C.plans || []).map(p => ({round: p.round, wave: p.wave,
            actions: p.plan && p.plan.actions ? p.plan.actions.length : null,
            status: p.plan && p.plan.status, reached_tick: p.plan && p.plan.reached_tick}))} : null,
    full: F ? {status: F.status, done: F.done, rounds: F.rounds ? F.rounds.length : null,
        checkedTicks: S(F.checkedTicks), firstDamage: F.firstDamage,
        winObserved: S(F.winObserved), protocolErrors: F.protocolErrors,
        tickGaps: F.tickGaps ? F.tickGaps.length : null,
        clockErrors: F.clockErrors ? F.clockErrors.length : null,
        saved: S(F.saved), error: F.error, payloadBytes: S(F.payloadBytes)} : null,
  });
})()`;

const TERMINAL = {
    custom: new Set(["completed", "failed", "cancelled", "unknown"]),
    campaign: new Set(["stopped", "failed", "cancelled"]),
    full: new Set(["passed", "failed_damage", "failed_protocol", "failed_clock", "failed_save", "failed_driver"]),
};

class CDP {
    constructor(wsUrl) {
        this.ws = new WebSocket(wsUrl);
        this.id = 0;
        this.pending = new Map();
        this.events = [];
        this.ready = new Promise((resolve, reject) => {
            this.ws.onopen = () => resolve();
            this.ws.onerror = (e) => reject(new Error("CDP websocket error"));
        });
        this.ws.onmessage = (ev) => {
            let msg; try { msg = JSON.parse(ev.data); } catch { return; }
            if (msg.id !== undefined && this.pending.has(msg.id)) {
                const { resolve, reject } = this.pending.get(msg.id);
                this.pending.delete(msg.id);
                msg.error ? reject(new Error(JSON.stringify(msg.error))) : resolve(msg.result);
            } else if (msg.method) {
                this.events.push(msg);
            }
        };
    }
    send(method, params = {}, sessionId) {
        const id = ++this.id;
        const payload = { id, method, params };
        if (sessionId) payload.sessionId = sessionId;
        this.ws.send(JSON.stringify(payload));
        return new Promise((resolve, reject) => {
            this.pending.set(id, { resolve, reject });
            setTimeout(() => { if (this.pending.delete(id)) reject(new Error("CDP timeout " + method)); }, 30000);
        });
    }
    close() { try { this.ws.close(); } catch {} }
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function main() {
    const list = await (await fetch(`http://127.0.0.1:${CDP_PORT}/json/list`)).json();
    let page = list.find((t) => t.type === "page");
    if (!page) throw new Error("No page target on CDP port " + CDP_PORT);
    const cdp = new CDP(page.webSocketDebuggerUrl);
    await cdp.ready;

    const { sessionId } = await cdp.send("Target.attachToTarget", { targetId: page.id, flatten: true });
    await cdp.send("Page.enable", {}, sessionId);
    await cdp.send("Runtime.enable", {}, sessionId);
    await cdp.send("Log.enable", {}, sessionId);
    // The driver scripts are edited between runs; a cached copy silently measures
    // the previous build. The server already sends no-store, but the renderer's
    // memory cache can still win, so disable it for the whole session.
    await cdp.send("Network.enable", {}, sessionId);
    await cdp.send("Network.setCacheDisabled", { cacheDisabled: true }, sessionId);
    await cdp.send("Target.activateTarget", { targetId: page.id });

    console.log(`[drive] ${LABEL} navigating -> ${URL_}`);
    await cdp.send("Page.navigate", { url: URL_ }, sessionId);

    const started = Date.now();
    const seen = new Set();
    let summary = null, finalStatus = null, lastLog = 0;

    while ((Date.now() - started) / 1000 < TIMEOUT_S) {
        await sleep(POLL_MS);
        let probe;
        try {
            const r = await cdp.send("Runtime.evaluate",
                { expression: PROBE, returnByValue: true, awaitPromise: false }, sessionId);
            if (r.exceptionDetails) { console.log("[drive] probe exception", JSON.stringify(r.exceptionDetails).slice(0, 300)); continue; }
            probe = JSON.parse(r.result.value);
        } catch (e) { console.log("[drive] probe failed:", e.message); continue; }

        summary = probe;
        const key = JSON.stringify(probe);
        if (key !== seen.last) { seen.add(key); seen.last = key; }
        finalStatus = probe.csvtas ? probe.csvtas.status
            : probe.campaign ? probe.campaign.status
            : probe.full ? probe.full.status : null;

        const elapsed = ((Date.now() - started) / 1000).toFixed(0);
        if (Date.now() - lastLog > 20000) {
            lastLog = Date.now();
            console.log(`[drive] t=${elapsed}s status=${finalStatus} ` + JSON.stringify({
                bridge: probe.bridge && probe.bridge.status,
                csvtas: probe.csvtas && probe.csvtas.status,
                plan: probe.csvtas && probe.csvtas.plan && probe.csvtas.plan.status,
                recipe: probe.csvtas && probe.csvtas.request_recipe,
                custom: probe.custom && probe.custom.status,
                campaign: probe.campaign && probe.campaign.status,
                rounds: probe.campaign && probe.campaign.planCount,
                full: probe.full && probe.full.status,
                fullRounds: probe.full && probe.full.rounds,
                ticks: probe.full && probe.full.checkedTicks,
                damage: probe.full && probe.full.firstDamage && probe.full.firstDamage.tick,
            }));
        }

        let done = false;
        if (probe.csvtas && TERMINAL.custom.has(probe.csvtas.status)) done = true;
        if (probe.full && TERMINAL.full.has(probe.full.status)) done = true;
        if (probe.campaign && TERMINAL.campaign.has(probe.campaign.status)) done = true;
        if (done) break;
    }

    // Give the page a moment to flush its own evidence POST.
    await sleep(4000);

    const consoleErrors = [];
    for (const ev of cdp.events) {
        if (ev.method === "Runtime.exceptionThrown") {
            consoleErrors.push({ kind: "exception", text: ev.params?.exceptionDetails?.text,
                url: ev.params?.exceptionDetails?.url, line: ev.params?.exceptionDetails?.lineNumber });
        } else if (ev.method === "Log.entryAdded" && ev.params?.entry?.level === "error") {
            consoleErrors.push({ kind: "log", text: ev.params.entry.text, url: ev.params.entry.url });
        } else if (ev.method === "Runtime.consoleAPICalled" && ev.params?.type === "error") {
            consoleErrors.push({ kind: "console", text: (ev.params.args || []).map((a) => a.value ?? a.description).join(" ") });
        }
    }

    const record = {
        label: LABEL, url: URL_, started_at: new Date(started).toISOString(),
        elapsed_seconds: (Date.now() - started) / 1000,
        terminal_status: finalStatus, last_summary: summary, console_errors: consoleErrors,
    };
    fs.writeFileSync(OUT, JSON.stringify(record, null, 2), "utf-8");
    console.log(`[drive] done -> ${OUT} terminal=${finalStatus} elapsed=${record.elapsed_seconds.toFixed(0)}s errors=${consoleErrors.length}`);
    cdp.close();
}

main().catch((e) => { console.error("[drive] fatal:", e); process.exit(1); });

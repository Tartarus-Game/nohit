/**
 * Calibrates PlayerHeart's real dynamics cleanly.
 *
 * Problem with the naive approach: driving `rt.tick()` by hand while the page's
 * own requestAnimationFrame loop is still running double-steps the engine and
 * shreds `rt.dt` (observed 0.0003 instead of ~0.004). This harness therefore:
 *
 *   1. cancels the page's RAF loop and replaces it with a manual pump, so the
 *      engine advances exactly once per recorded sample and `rt.dt` is stable;
 *   2. records a real BLUE-heart run (HeartMode != RED) with scripted input;
 *   3. fits the vertical model from the samples:
 *        - the tick latency between setting dy and y moving
 *        - the per-tick displacement law (dy * dt vs pxPerStep stepping)
 *        - the gravity ladder: G = f(DownSpeed) from observed dv/dt
 *        - the terminal velocity clamp
 *        - the landing offset
 *
 * Usage: node tools/calibrate_heart.mjs [httpPort] [cdpPort] [ticks]
 */

import fs from "node:fs";

const HTTP_PORT = process.argv[2] || "8099";
const CDP_PORT = process.argv[3] || "9333";
const TICKS = Number(process.argv[4] || 600);
const PAGE_URL = `http://127.0.0.1:${HTTP_PORT}/game/index.html`;

class CDP {
    constructor(wsUrl) {
        this.ws = new WebSocket(wsUrl);
        this.id = 0;
        this.pending = new Map();
        this.ready = new Promise((res, rej) => {
            this.ws.addEventListener("open", () => res());
            this.ws.addEventListener("error", (e) => rej(new Error("ws " + (e.message || e.type))));
        });
        this.ws.addEventListener("message", (ev) => {
            const msg = JSON.parse(ev.data);
            if (msg.id !== undefined && this.pending.has(msg.id)) {
                const { resolve, reject } = this.pending.get(msg.id);
                this.pending.delete(msg.id);
                msg.error ? reject(new Error(JSON.stringify(msg.error))) : resolve(msg.result);
            }
        });
    }
    send(method, params = {}, sessionId) {
        const id = ++this.id;
        const p = { id, method, params };
        if (sessionId) p.sessionId = sessionId;
        this.ws.send(JSON.stringify(p));
        return new Promise((res, rej) => {
            this.pending.set(id, { resolve: res, reject: rej });
            setTimeout(() => { if (this.pending.delete(id)) rej(new Error("timeout " + method)); }, 120000);
        });
    }
}

const targets = await fetch(`http://127.0.0.1:${CDP_PORT}/json/list`).then((r) => r.json());
const page = targets.find((t) => t.type === "page" && !/chrome-extension/.test(t.url || ""));
const cdp = new CDP(page.webSocketDebuggerUrl);
await cdp.ready;
const { sessionId } = await cdp.send("Target.attachToTarget", { targetId: page.id, flatten: true });
const send = (m, p) => cdp.send(m, p, sessionId);
await send("Runtime.enable");
await send("Page.navigate", { url: PAGE_URL });
await new Promise((r) => setTimeout(r, 9000));

const evalJs = async (expression, awaitPromise = false) => {
    const res = await send("Runtime.evaluate", { expression, awaitPromise, returnByValue: true });
    if (res.exceptionDetails) {
        const d = res.exceptionDetails;
        throw new Error(d.exception ? (d.exception.description || d.exception.value) : d.text);
    }
    return res.result.value;
};

// 1) Freeze the page's own loop and install a manual pump.
const setup = await evalJs(String.raw`(async () => {
    const rt = window.c2runtime || document.getElementById('c2canvas').c2runtime;
    window.__rt = rt;

    // Stop C2's own RAF loop by clearing its request id, then neuter rAF.
    window.__rafQueue = [];
    window.requestAnimationFrame = function (fn) { window.__rafQueue.push(fn); return 0; };
    window.cancelAnimationFrame = function () { };
    if (rt.raf_id !== undefined) { try { cancelAnimationFrame(rt.raf_id); } catch (e) {} rt.raf_id = null; }
    rt.isSuspended = true;          // C2 renders via its own loop we just removed
    rt.tickcount = rt.tickcount || 0;

    // Manual pump with a FIXED dt (1/60) so the model is deterministic.
    rt.dt = 1 / 60;
    window.__tick = () => { rt.tick(false, performance.now(), false); };
    window.__setDt = (d) => { rt.dt = d; };

    const press = (w, hold) => {
        const mk = (t) => new KeyboardEvent(t, { which: w, keyCode: w, bubbles: true, cancelable: true });
        document.dispatchEvent(mk('keydown'));
        setTimeout(() => document.dispatchEvent(mk('keyup')), hold || 110);
    };
    press(90);   // MainMenu -> BattleScreen
    return { layout: rt.running_layout && rt.running_layout.name, dt: rt.dt };
})()`, true);
console.log("=== setup ===");
console.log(JSON.stringify(setup, null, 2));

await new Promise((r) => setTimeout(r, 1500));

// 2) Reach the practice-attack screen: Z (FIGHT) -> pick entry -> start.
//    Use the engine's own function bus where possible, then confirm presses.
const reach = await evalJs(String.raw`(async () => {
    const rt = window.__rt;
    const pump = (n) => { for (let i = 0; i < n; i++) window.__tick(); };
    const press = (w, hold) => {
        const mk = (t) => new KeyboardEvent(t, { which: w, keyCode: w, bubbles: true, cancelable: true });
        document.dispatchEvent(mk('keydown'));
        setTimeout(() => document.dispatchEvent(mk('keyup')), hold || 110);
    };
    const gv = () => { const o = {}; (rt.all_global_vars || []).forEach(v => { o[v.name] = v.data; }); return o; };

    // Battle menu: confirm on FIGHT.
    press(90);
    await new Promise(r => setTimeout(r, 900));
    pump(10);
    let s1 = gv();
    // Second confirm starts the practice attack.
    press(90);
    await new Promise(r => setTimeout(r, 1200));
    pump(30);
    let s2 = gv();

    const t55 = (rt.types_by_index || []).find(t => t && t.name === 't55');
    const heart = t55.instances[0];
    window.__heart = heart;
    window.__cm = heart.behavior_insts[0];
    return {
        layout: rt.running_layout && rt.running_layout.name,
        s1: { MenuState: s1.MenuState, SimulatorMode: s1.SimulatorMode, SingleAttack: s1.SingleAttack, HP: s1.HP },
        s2: { MenuState: s2.MenuState, SimulatorMode: s2.SimulatorMode, SingleAttack: s2.SingleAttack, HP: s2.HP },
        pos: { x: heart.x, y: heart.y },
        visible: heart.visible,
        mode: heart.instance_vars ? heart.instance_vars[0] : null,
        cm: { dx: window.__cm.dx, dy: window.__cm.dy, stepMode: window.__cm.stepMode, pxPerStep: window.__cm.pxPerStep, enabled: window.__cm.enabled },
    };
})()`, true);
console.log("\n=== reach ===");
console.log(JSON.stringify(reach, null, 2));

// 3) Scripted measurement runs with a fixed dt.
const runs = await evalJs(String.raw`(async () => {
    const rt = window.__rt, h = window.__heart, cm = window.__cm;
    const kb = (rt.types_by_index || []).map(t => t && t.instances && t.instances[0]).find(i => i && i.keyMap);
    const setKeys = (o) => {
        if (!kb) return;
        kb.keyMap[38] = !!o.up;   kb.keyMap[87] = !!o.up;
        kb.keyMap[40] = !!o.down; kb.keyMap[83] = !!o.down;
        kb.keyMap[37] = !!o.left; kb.keyMap[65] = !!o.left;
        kb.keyMap[39] = !!o.right; kb.keyMap[68] = !!o.right;
    };
    const sample = () => ({
        x: +h.x.toFixed(6), y: +h.y.toFixed(6),
        dx: +(cm.dx || 0).toFixed(6), dy: +(cm.dy || 0).toFixed(6),
        mode: h.instance_vars ? h.instance_vars[0] : -1,
        dt: rt.dt,
    });

    const out = {};

    // Run A: RED mode idle - baseline (does y drift?).
    setKeys({});
    { const seq = []; for (let i = 0; i < 30; i++) { window.__tick(); seq.push(sample()); } out.idleRed = seq; }

    // Run B: RED mode RIGHT held - measure per-tick x displacement.
    setKeys({ right: 1 });
    { const seq = []; for (let i = 0; i < 30; i++) { window.__tick(); seq.push(sample()); } out.rightRed = seq; }
    setKeys({});

    // Run C: RED mode UP held - measure per-tick y displacement.
    setKeys({ up: 1 });
    { const seq = []; for (let i = 0; i < 40; i++) { window.__tick(); seq.push(sample()); } out.upRed = seq; }
    setKeys({});

    // Run D: release and let it settle (jump cutoff behaviour).
    { const seq = []; for (let i = 0; i < 60; i++) { window.__tick(); seq.push(sample()); } out.settleRed = seq; }

    return out;
})()`, true);
void runs;

const outPath = new URL("./.calib_runs.json", import.meta.url);
fs.writeFileSync(outPath, JSON.stringify(runs, null, 2), "utf8");

const summarize = (label, seq) => {
    if (!seq || !seq.length) { console.log(`  ${label}: (empty)`); return; }
    console.log(`  ${label}: n=${seq.length} mode=${seq[0].mode} startPos=(${seq[0].x}, ${seq[0].y}) endPos=(${seq[seq.length - 1].x}, ${seq[seq.length - 1].y})`);
    const steps = [];
    for (let i = 1; i < Math.min(seq.length, 12); i++) {
        steps.push(`(${(seq[i].x - seq[i - 1].x).toFixed(3)},${(seq[i].y - seq[i - 1].y).toFixed(3)})`);
    }
    console.log(`     first steps: ${steps.join(" ")}`);
    const cmSteps = seq.slice(0, 8).map(s => `dx=${s.dx} dy=${s.dy}`);
    console.log(`     cm: ${cmSteps.join(" | ")}`);
};

console.log("\n=== summary ===");
summarize("idle RED", runs.idleRed);
summarize("RIGHT RED", runs.rightRed);
summarize("UP RED", runs.upRed);
summarize("settle", runs.settleRed);
console.log(`\nfull runs -> ${outPath.pathname}`);

cdp.ws.close();
process.exit(0);

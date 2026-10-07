/**
 * Records ground-truth PlayerHeart motion from the running export.
 *
 * The compiled export keeps the movement state where Construct 2 puts it, so
 * this first LOCATES the mode/direction/speed storage (probing several known C2
 * layouts), then drives a real battle and records, once per engine tick:
 *
 *   tick, input bits (VPad/Down-key), x, y, and every speed-like field found
 *
 * The resulting trace is the ground truth the Python stepper must reproduce:
 * it exposes the tick latency between setting a speed and the position moving,
 * the exact per-tick displacement, and the landing rule.
 *
 * Usage: node tools/record_hearts.mjs [httpPort] [cdpPort] [ticks]
 */

import fs from "node:fs";

const HTTP_PORT = process.argv[2] || "8099";
const CDP_PORT = process.argv[3] || "9333";
const TICKS = Number(process.argv[4] || 240);
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
            setTimeout(() => { if (this.pending.delete(id)) rej(new Error("timeout " + method)); }, 90000);
        });
    }
}

const targets = await fetch(`http://127.0.0.1:${CDP_PORT}/json/list`).then((r) => r.json());
const page = targets.find((t) => t.type === "page" && !/chrome-extension/.test(t.url || ""));
if (!page) { console.error("no page target"); process.exit(1); }
const cdp = new CDP(page.webSocketDebuggerUrl);
await cdp.ready;
const { sessionId } = await cdp.send("Target.attachToTarget", { targetId: page.id, flatten: true });
const send = (m, p) => cdp.send(m, p, sessionId);
await send("Runtime.enable");
await send("Page.navigate", { url: PAGE_URL });
await new Promise((r) => setTimeout(r, 8000));

const evalJs = async (expression, awaitPromise = false) => {
    const res = await send("Runtime.evaluate", { expression, awaitPromise, returnByValue: true });
    if (res.exceptionDetails) {
        const d = res.exceptionDetails;
        throw new Error(d.exception ? (d.exception.description || d.exception.value) : d.text);
    }
    return res.result.value;
};

// ---- locate heart + its speed storage -------------------------------------
const locate = await evalJs(String.raw`(() => {
    const rt = window.c2runtime || document.getElementById('c2canvas').c2runtime;
    window.__rt = rt;
    const t55 = (rt.types_by_index || []).find(t => t && t.name === 't55');
    const heart = t55 && t55.instances && t55.instances[0];
    window.__heart = heart;
    if (!heart) return { ok: false, reason: 'no heart instance' };

    const instBehs = heart.behavior_insts || heart.behaviors || [];
    const behDump = [];
    for (let i = 0; i < (instBehs.length || 0); i++) {
        const b = instBehs[i];
        behDump.push({
            i,
            ctor: b && b.constructor && b.constructor.name,
            keys: b ? Object.keys(b) : null,
            dx: b ? b.dx : undefined,
            dy: b ? b.dy : undefined,
            speed: b ? b.speed : undefined,
        });
    }
    const typeBehs = (t55.behaviorTypes || []).map((bt, i) => ({
        i, name: bt && bt.name,
        klass: bt && bt.behavior && bt.behavior.constructor && bt.behavior.constructor.name,
    }));
    return {
        ok: true,
        layout: rt.running_layout && rt.running_layout.name,
        dt: rt.dt, fps: rt.fps,
        pos: { x: heart.x, y: heart.y },
        instanceVars: heart.instance_vars,
        instBehCount: instBehs.length || 0,
        behDump, typeBehs,
        heartKeys: Object.keys(heart),
    };
})()`);
console.log("=== locate ===");
console.log(JSON.stringify(locate, null, 2));

// ---- enter a battle -------------------------------------------------------
const startAttack = process.argv[5] || "";
await evalJs(String.raw`(() => {
    const press = (w, hold) => {
        const mk = (t) => new KeyboardEvent(t, { which: w, keyCode: w, bubbles: true, cancelable: true });
        document.dispatchEvent(mk('keydown'));
        setTimeout(() => document.dispatchEvent(mk('keyup')), hold || 110);
    };
    const attack = ${JSON.stringify(startAttack)};
    if (attack && typeof window.c2_callFunction === 'function') {
        // Practice / single-attack path: RunAttack(<name>)
        window.c2_callFunction('RunAttack', [attack]);
    }
    press(90); setTimeout(() => press(90), 800); setTimeout(() => press(90), 1600);
    return true;
})()`);
await new Promise((r) => setTimeout(r, 4000));

const battlestate = await evalJs(String.raw`(() => {
    const rt = window.__rt, heart = window.__heart;
    return {
        layout: rt.running_layout && rt.running_layout.name,
        tick: rt.tickcount,
        pos: { x: heart.x, y: heart.y },
        visible: heart.visible,
        mode: heart.instance_vars ? heart.instance_vars[0] : null,
        dt: rt.dt,
    };
})()`);
console.log("\n=== battle state ===");
console.log(JSON.stringify(battlestate, null, 2));

// ---- record ---------------------------------------------------------------
const trace = await evalJs(String.raw`(() => {
    const rt = window.__rt, heart = window.__heart;
    const kb = (rt.types_by_index || []).map(t => t && t.instances && t.instances[0])
        .find(i => i && i.keyMap);
    const instBehs = heart.behavior_insts || heart.behaviors || [];
    const rows = [];
    for (let i = 0; i < ${TICKS}; i++) {
        const before = { x: heart.x, y: heart.y, t: rt.tickcount };
        rt.tick(false, performance.now(), false);
        const speeds = [];
        for (let b = 0; b < (instBehs.length || 0); b++) {
            const bi = instBehs[b];
            if (bi && (bi.dx !== undefined || bi.dy !== undefined)) {
                speeds.push([+(bi.dx || 0).toFixed(6), +(bi.dy || 0).toFixed(6)]);
            }
        }
        rows.push({
            i,
            tick: before.t,
            x: +heart.x.toFixed(6),
            y: +heart.y.toFixed(6),
            dx: +(heart.x - before.x).toFixed(6),
            dy: +(heart.y - before.y).toFixed(6),
            sp: speeds.length ? speeds[0] : null,
            mode: heart.instance_vars ? heart.instance_vars[0] : null,
            keys: kb ? [37, 38, 39, 40].map(k => (kb.keyMap[k] ? 1 : 0)).join('') : null,
        });
    }
    return { dt: rt.dt, rows };
})()`);

console.log(`\n=== trace (${trace.rows.length} ticks, dt=${trace.dt}) ===`);
const head = trace.rows.slice(0, 40);
for (const r of head) {
    console.log(`  t=${String(r.i).padStart(3)} pos=(${r.x}, ${r.y}) d=(${r.dx}, ${r.dy}) sp=${JSON.stringify(r.sp)} mode=${r.mode} keys=${r.keys}`);
}
const outPath = new URL("./.heart_trace.json", import.meta.url);
fs.writeFileSync(outPath, JSON.stringify(trace, null, 2), "utf8");
console.log(`\nfull trace -> ${outPath.pathname}`);

cdp.ws.close();
process.exit(0);

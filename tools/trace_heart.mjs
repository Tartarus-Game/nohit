/**
 * Deterministic calibration recorder for PlayerHeart.
 *
 * Fixes the two measurement bugs found earlier:
 *   - do NOT hand-drive rt.tick() while the page's RAF loop runs (double-step,
 *     shredded dt). Instead hook rt.tick and sample once per REAL engine tick.
 *   - C2 computes dt from the wall clock (c2runtime.js:5372-5385), so lock it
 *     with timescale: dt = dt1 * timescale == 1/60 exactly.
 *
 * Records a real BattleScreen run with scripted input and emits the trace plus
 * a model-fit summary (per-tick displacement, gravity ladder, terminal
 * velocity, landing offset).
 *
 * Usage: node tools/trace_heart.mjs [httpPort] [cdpPort] [ticks]
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

// ---------------------------------------------------------------------------
// Install: lock dt to 1/60, hook tick, script input, record.
// ---------------------------------------------------------------------------
const result = await evalJs(String.raw`(async () => {
    const rt = window.c2runtime || document.getElementById('c2canvas').c2runtime;
    window.__rt = rt;

    // --- lock the timestep: dt = dt1 * timescale ---------------------------
    Object.defineProperty(rt, 'timescale', {
        configurable: true,
        get() { return window.__timescale; },
        set(v) { window.__timescale = v; },
    });
    window.__timescale = 1;
    const lockDt = () => {
        const d1 = rt.dt1 || (1 / 60);
        if (d1 > 0) window.__timescale = (1 / 60) / d1;
    };
    window.__lockDt = lockDt;
    lockDt();

    // --- locate heart + behaviour ------------------------------------------
    const findHeart = () => {
        const t55 = (rt.types_by_index || []).find(t => t && t.name === 't55');
        return t55 && t55.instances && t55.instances[0];
    };
    const kb = (rt.types_by_index || [])
        .map(t => t && t.instances && t.instances[0])
        .find(i => i && i.keyMap);
    window.__kb = kb;

    const setKeys = (o) => {
        if (!kb) return;
        kb.keyMap[38] = !!o.up;   kb.keyMap[87] = !!o.up;
        kb.keyMap[40] = !!o.down; kb.keyMap[83] = !!o.down;
        kb.keyMap[37] = !!o.left; kb.keyMap[65] = !!o.left;
        kb.keyMap[39] = !!o.right; kb.keyMap[68] = !!o.right;
    };
    window.__setKeys = setKeys;

    const gv = () => { const o = {}; (rt.all_global_vars || []).forEach(v => { o[v.name] = v.data; }); return o; };

    // --- enter the battle: Z on the main menu ------------------------------
    const press = (w) => {
        const mk = (t) => new KeyboardEvent(t, { which: w, keyCode: w, bubbles: true, cancelable: true });
        document.dispatchEvent(mk('keydown'));
        setTimeout(() => document.dispatchEvent(mk('keyup')), 110);
    };
    press(90);
    await new Promise(r => setTimeout(r, 2500));
    // FIGHT -> practice attack
    press(90);
    await new Promise(r => setTimeout(r, 1500));
    press(90);
    await new Promise(r => setTimeout(r, 1500));

    const heart = findHeart();
    const cm = heart && heart.behavior_insts && heart.behavior_insts[0];
    window.__heart = heart;
    window.__cm = cm;

    const preState = {
        layout: rt.running_layout && rt.running_layout.name,
        dt: rt.dt, dt1: rt.dt1, timescale: rt.timescale,
        tick: rt.tickcount,
        pos: { x: heart.x, y: heart.y },
        visible: heart.visible,
        mode: heart.instance_vars ? heart.instance_vars[0] : null,
        cm: cm ? { dx: cm.dx, dy: cm.dy, stepMode: cm.stepMode, pxPerStep: cm.pxPerStep } : null,
        globals: gv(),
    };

    // --- record: scripted input, one sample per real engine tick -----------
    // NOTE: match the heart's declared size to understand landing offsets.
    const rows = [];
    const proto = rt.constructor.prototype;
    const origTick = proto.tick;
    let n = 0;

    const trace = await new Promise((resolve) => {
        proto.tick = function () {
            // input for the NEXT tick, applied before the engine body runs
            const phase = n % 120;
            if (phase < 30) setKeys({ up: 1 });
            else if (phase < 45) setKeys({});
            else if (phase < 75) setKeys({ right: 1 });
            else if (phase < 90) setKeys({});
            else if (phase < 110) setKeys({ down: 1 });
            else setKeys({});
            lockDt();

            const before = { x: heart.x, y: heart.y, t: rt.tickcount };
            const r = origTick.apply(this, arguments);
            rows.push({
                i: n,
                tick: before.t,
                x: +heart.x.toFixed(6),
                y: +heart.y.toFixed(6),
                sx: +(heart.x - before.x).toFixed(6),
                sy: +(heart.y - before.y).toFixed(6),
                cdx: +(cm.dx || 0).toFixed(6),
                cdy: +(cm.dy || 0).toFixed(6),
                mode: heart.instance_vars ? heart.instance_vars[0] : -1,
                vis: heart.visible ? 1 : 0,
                dt: +rt.dt.toFixed(9),
                w: heart.width, hgt: heart.height,
                inUp: kb && kb.keyMap[38] ? 1 : 0,
                inDown: kb && kb.keyMap[40] ? 1 : 0,
                inLeft: kb && kb.keyMap[37] ? 1 : 0,
                inRight: kb && kb.keyMap[39] ? 1 : 0,
            });
            n++;
            if (n >= ${TICKS}) {
                proto.tick = origTick;
                setKeys({});
                resolve({ pre: preState, rows, finalGlobals: gv(), finalMode: heart.instance_vars ? heart.instance_vars[0] : -1 });
            }
            return r;
        };
    });

    return trace;
})()`, true);

const { pre, rows, finalGlobals, finalMode } = result;
console.log("=== pre-battle state ===");
console.log(JSON.stringify(pre, null, 2));

const dtSet = [...new Set(rows.map((r) => r.dt))];
console.log(`\n=== recorded ${rows.length} ticks | distinct dt = ${JSON.stringify(dtSet)} ===`);
console.log(`heart size = ${rows[0].w} x ${rows[0].hgt}`);
console.log(`final mode=${finalMode} HP=${finalGlobals.HP}`);

console.log("\n-- first 30 ticks --");
console.log("   i  input(UDRL)  x           y           stepx    stepy    cm.dx   cm.dy   mode");
for (const r of rows.slice(0, 30)) {
    const inp = `${r.inUp}${r.inDown}${r.inLeft}${r.inRight}`;
    console.log(`  ${String(r.i).padStart(3)}  ${inp}        ${String(r.x).padEnd(11)} ${String(r.y).padEnd(11)} ${String(r.sx).padEnd(8)} ${String(r.sy).padEnd(8)} ${String(r.cdx).padEnd(7)} ${String(r.cdy).padEnd(7)} ${r.mode}`);
}

// ---- fit summary ----------------------------------------------------------
const moving = rows.filter((r) => r.cdx !== 0 || r.cdy !== 0);
console.log(`\n-- ticks with non-zero cm velocity: ${moving.length} --`);
if (moving.length) {
    const firstMove = moving[0];
    console.log(`  first motion at i=${firstMove.i} pos=(${firstMove.x}, ${firstMove.y}) cm=(${firstMove.cdx}, ${firstMove.cdy})`);
}
const modes = [...new Set(rows.map((r) => r.mode))];
console.log(`  modes seen: ${JSON.stringify(modes)}`);

const outPath = new URL("./.heart_trace.json", import.meta.url);
fs.writeFileSync(outPath, JSON.stringify(result, null, 2), "utf8");
console.log(`\nfull trace -> ${outPath.pathname}`);

cdp.ws.close();
process.exit(0);

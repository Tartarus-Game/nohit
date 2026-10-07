/**
 * GROUND TRUTH TEST: run the real game against the solver's own plan.
 *
 * This is the test that was missing. Everything verified so far was
 * self-consistency (the solver and the verifier share one semantics, so they
 * agree with each other by construction). Here we instead:
 *
 *   1. enter a real battle in the compiled build;
 *   2. ask the Python solver for the witness action sequence for that attack;
 *   3. inject exactly those inputs into the real engine, one per engine tick;
 *   4. read back, per tick, the heart position AND the HP counter;
 *   5. compare the real trajectory against the solver's predicted trajectory,
 *      and the real HP against the "no-hit" claim.
 *
 * If the model is wrong, either the trajectories diverge (motion model) or HP
 * drops / collision triggers (settlement model).
 *
 * Usage: node tools/groundtruth_run.mjs [httpPort] [cdpPort] [wave] [ticks]
 */

import fs from "node:fs";

const HTTP_PORT = process.argv[2] || "8099";
const CDP_PORT = process.argv[3] || "9222";
const WAVE = process.argv[4] || "sans_bonegap1";
const TICKS = Number(process.argv[5] || 150);
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
if (!page) { console.error("no page target on", CDP_PORT); process.exit(1); }
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

// --- solver plan ----------------------------------------------------------
const planUrl = `http://127.0.0.1:${HTTP_PORT}/api/tas?wave=${WAVE}.csv&T=${TICKS}&soul_w=4&soul_h=4&physics_mode=c2`;
const plan = await fetch(planUrl)
    .then((r) => r.json())
    .catch((e) => ({ error: String(e) }));
if (plan.error || plan.is_deadlock) {
    console.log(`solver says: ${plan.error || "DEADLOCK @ t=" + plan.deadlock_frame}`);
    process.exit(2);
}
console.log(`=== solver plan for ${WAVE} ===`);
console.log(`  actions=${plan.action_sequence.length}  arena=${JSON.stringify(plan.arena)}  init=${JSON.stringify(plan.initial_state)}`);

// --- enter battle ----------------------------------------------------------
const enter = await evalJs(String.raw`(async () => {
    const rt = window.c2runtime || document.getElementById('c2canvas').c2runtime;
    window.__rt = rt;
    const press = (w) => {
        const mk = (t) => new KeyboardEvent(t, { which: w, keyCode: w, bubbles: true, cancelable: true });
        document.dispatchEvent(mk('keydown'));
        setTimeout(() => document.dispatchEvent(mk('keyup')), 110);
    };
    press(90);                                   // MainMenu -> BattleScreen
    await new Promise(r => setTimeout(r, 2500));
    press(90);                                   // FIGHT
    await new Promise(r => setTimeout(r, 1200));
    press(90);                                   // start practice attack
    await new Promise(r => setTimeout(r, 2500));

    const gv = () => { const o = {}; (rt.all_global_vars || []).forEach(v => { o[v.name] = v.data; }); return o; };
    const t55 = (rt.types_by_index || []).find(t => t && t.name === 't55');
    const heart = t55 && t55.instances && t55.instances[0];
    window.__heart = heart;
    window.__cm = heart && heart.behavior_insts && heart.behavior_insts[0];
    return {
        layout: rt.running_layout && rt.running_layout.name,
        heartVisible: heart ? heart.visible : null,
        heartPos: heart ? { x: +heart.x.toFixed(3), y: +heart.y.toFixed(3) } : null,
        mode: heart && heart.instance_vars ? heart.instance_vars[0] : null,
        cm: window.__cm ? { dx: window.__cm.dx, dy: window.__cm.dy } : null,
        globals: { HP: gv().HP, KR: gv().KR, SimulatorMode: gv().SimulatorMode },
    };
})()`, true);
console.log("\n=== battle state ===");
console.log(JSON.stringify(enter, null, 2));

// --- bone geometry ground truth -------------------------------------------
const boneGeo = await evalJs(String.raw`(async () => {
    const rt = window.__rt;

    // Helper: instance counts per type, to spot what a command creates.
    const counts = () => {
        const m = {};
        for (const t of (rt.types_by_index || [])) {
            if (t && t.instances && t.instances.length) m[t.name] = t.instances.length;
        }
        return m;
    };
    // Find the AttackSprite family members (bones live there).
    const before = counts();
    // Ask the game to spawn a vertical bone exactly like a script would.
    try {
        if (typeof window.c2_callFunction === 'function') {
            window.c2_callFunction('BoneV', [300, 300, 40, 1, 120, 0]);
        }
    } catch (e) { /* ignore */ }
    await new Promise(r => setTimeout(r, 300));
    const after = counts();

    const newTypes = [];
    for (const k of Object.keys(after)) {
        const d = (after[k] || 0) - (before[k] || 0);
        if (d > 0) newTypes.push([k, d]);
    }

    // Describe any freshly created instance across all types.
    const fresh = [];
    for (const t of (rt.types_by_index || [])) {
        if (!t || !t.instances) continue;
        for (const inst of t.instances) {
            if (inst && inst.__geoProbe) continue;
            if (newTypes.some(([n]) => n === t.name)) {
                inst.__geoProbe = true;
                fresh.push({
                    type: t.name,
                    x: +inst.x.toFixed(3), y: +inst.y.toFixed(3),
                    width: inst.width, height: inst.height,
                    hotspotX: inst.hotspotX, hotspotY: inst.hotspotY,
                    bbox: inst.bbox ? {
                        left: +inst.bbox.left.toFixed(3), top: +inst.bbox.top.toFixed(3),
                        right: +inst.bbox.right.toFixed(3), bottom: +inst.bbox.bottom.toFixed(3),
                    } : null,
                    polyLen: inst.collision_poly ? inst.collision_poly.length : null,
                    polyPoints: inst.collision_poly && inst.collision_poly.points
                        ? Array.from(inst.collision_poly.points).slice(0, 12)
                        : null,
                    instanceVars: inst.instance_vars,
                });
            }
        }
    }
    return { newTypes, fresh };
})()`, true);
console.log("\n=== bone geometry ground truth (after BoneV(300,300,40,1,120,0)) ===");
console.log(JSON.stringify(boneGeo, null, 2));

// --- run the solver's plan against the real engine ------------------------
const run = await evalJs(String.raw`(async () => {
    const rt = window.__rt, heart = window.__heart, cm = window.__cm;
    const kb = (rt.types_by_index || []).map(t => t && t.instances && t.instances[0]).find(i => i && i.keyMap);
    const gv = () => { const o = {}; (rt.all_global_vars || []).forEach(v => { o[v.name] = v.data; }); return o; };
    const actions = ${JSON.stringify(plan.action_sequence)};
    const predicted = ${JSON.stringify(plan.trajectory)};
    const arena = ${JSON.stringify(plan.arena)};

    const setKeys = (o) => {
        if (!kb) return;
        kb.keyMap[38] = !!o.up;   kb.keyMap[87] = !!o.up;
        kb.keyMap[40] = !!o.down; kb.keyMap[83] = !!o.down;
        kb.keyMap[37] = !!o.left; kb.keyMap[65] = !!o.left;
        kb.keyMap[39] = !!o.right; kb.keyMap[68] = !!o.right;
    };

    const hp0 = gv().HP;
    const rows = [];
    const prevTick = rt.tickcount;
    const proto = rt.constructor.prototype;
    const origTick = proto.tick;
    let i = 0;

    const trace = await new Promise((resolve) => {
        proto.tick = function () {
            const a = actions[Math.min(i, actions.length - 1)] || [0, 0];
            setKeys({ left: a[0] < 0, right: a[0] > 0, up: a[1] > 0, down: a[1] < 0 });
            const r = origTick.apply(this, arguments);
            const hp = gv().HP;
            rows.push({
                i,
                x: +heart.x.toFixed(3),
                y: +heart.y.toFixed(3),
                hp,
                vis: heart.visible ? 1 : 0,
                mode: heart.instance_vars ? heart.instance_vars[0] : -1,
                a,
            });
            i++;
            if (i >= ${TICKS}) {
                proto.tick = origTick;
                setKeys({});
                resolve(rows);
            }
            return r;
        };
    });

    // Compare against the solver's predicted local-space trajectory.
    const cmp = [];
    for (let k = 0; k < trace.length; k += 15) {
        const real = trace[k];
        const localX = real.x - arena.c2_left;
        const localY = arena.c2_floor - real.y;
        const pred = predicted[Math.min(k, predicted.length - 1)];
        cmp.push({
            i: k,
            realLocal: [+localX.toFixed(2), +localY.toFixed(2)],
            solverLocal: [pred[0], pred[1]],
            dx: +(localX - pred[0]).toFixed(2),
            dy: +(localY - pred[1]).toFixed(2),
        });
    }
    return { hp0, hpEnd: gv().HP, rows: trace.length, cmp, firstRows: trace.slice(0, 12) };
})()`, true);

console.log("\n=== real game vs solver plan ===");
console.log(`  HP: ${run.hp0} -> ${run.hpEnd}   (${run.hpEnd < run.hp0 ? "*** TOOK DAMAGE ***" : "no damage"})`);
console.log(`  ticks recorded: ${run.rows}`);
console.log("\n  i      real(local)      solver(local)     Δx       Δy");
for (const c of run.cmp) {
    console.log(`  ${String(c.i).padStart(4)}   ${JSON.stringify(c.realLocal).padEnd(16)} ${JSON.stringify(c.solverLocal).padEnd(16)} ${String(c.dx).padStart(7)}  ${String(c.dy).padStart(7)}`);
}

const outPath = new URL("./.groundtruth_trace.json", import.meta.url);
fs.writeFileSync(outPath, JSON.stringify(run, null, 2), "utf8");
console.log(`\nfull trace -> ${outPath.pathname}`);

cdp.ws.close();
process.exit(run.hpEnd < run.hp0 ? 1 : 0);

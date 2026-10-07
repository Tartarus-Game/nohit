/**
 * Runs ONE COMPLETE ROUND in the real game:
 *   menu -> attack starts -> bones exist -> solver's TAS drives the heart ->
 *   measure HP damage and trajectory divergence.
 *
 * Discovery approach is state-driven, not guess-driven: it reads the game's own
 * menu/global variables each step and presses confirm only while the game is
 * still in a menu, so it adapts to whichever mode (normal / endless / practice)
 * the build boots into.
 *
 * Usage: node tools/run_one_round.mjs [httpPort] [cdpPort] [wave] [ticks]
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
            setTimeout(() => { if (this.pending.delete(id)) rej(new Error("timeout " + method)); }, 180000);
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
    const res = await send("Runtime.evaluate", {
        expression, awaitPromise, returnByValue: true,
    });
    if (res.exceptionDetails) {
        const d = res.exceptionDetails;
        throw new Error(d.exception ? (d.exception.description || d.exception.value) : d.text);
    }
    return res.result.value;
};

const planUrl = `http://127.0.0.1:${HTTP_PORT}/api/tas?wave=${WAVE}.csv&T=${TICKS}&soul_w=4&soul_h=4&physics_mode=c2`;
const plan = await fetch(planUrl).then((r) => r.json());
console.log(`=== solver plan: ${WAVE} ===`);
console.log(`  actions=${plan.action_sequence ? plan.action_sequence.length : "n/a"} deadlock=${plan.is_deadlock} init=${JSON.stringify(plan.initial_state)}`);
if (!plan.action_sequence) { console.log("solver returned no plan; aborting"); process.exit(2); }

// ---------------------------------------------------------------------------
// Phase 1: drive the menus by reading the game's own state.
// ---------------------------------------------------------------------------
const menu = await evalJs(String.raw`(async () => {
    const rt = window.c2runtime || document.getElementById('c2canvas').c2runtime;
    window.__rt = rt;
    const gv = () => { const o = {}; (rt.all_global_vars || []).forEach(v => { o[v.name] = v.data; }); return o; };
    const heart = (rt.types_by_index || []).find(t => t && t.name === 't55').instances[0];
    window.__heart = heart;

    const tlr = () => { try { return window.c2_callFunction('TLIsRunning', []); } catch (e) { return null; } };
    const census = () => {
        const m = {};
        for (const t of (rt.types_by_index || [])) if (t && t.instances && t.instances.length) m[t.name] = t.instances.length;
        return m;
    };
    const bones = () => {
        const c = census();
        return Object.entries(c).filter(([k]) => /^t(30|31|36|37|38|43|66|67|70|71|72)$/.test(k))
            .reduce((a, [k, v]) => a + v, 0);
    };
    const press = (w) => {
        const mk = (t) => new KeyboardEvent(t, { which: w, keyCode: w, bubbles: true, cancelable: true });
        document.dispatchEvent(mk('keydown'));
        setTimeout(() => document.dispatchEvent(mk('keyup')), 110);
    };

    const log = [];
    const snap = (tag) => {
        const g = gv();
        const s = {
            tag,
            layout: rt.running_layout && rt.running_layout.name,
            MenuState: g.MenuState,
            SimulatorMode: g.SimulatorMode,
            SingleAttack: g.SingleAttack,
            HP: g.HP,
            tlRunning: tlr(),
            bones: bones(),
            heartVisible: heart.visible,
            heartPos: [+heart.x.toFixed(2), +heart.y.toFixed(2)],
        };
        log.push(s);
        return s;
    };

    snap('boot');
    // Press confirm while we are still in a menu / no attack is running.
    for (let i = 0; i < 8; i++) {
        const s = snap('before-press-' + i);
        const inMenu = s.layout === 'MainMenu' || (s.tlRunning !== 1 && s.bones === 0);
        if (!inMenu) break;
        if (s.bones > 0) break;
        press(90);
        await new Promise(r => setTimeout(r, 1400));
        const after = snap('after-press-' + i);
        if (after.bones > 0 || after.tlRunning === 1) break;
    }
    // Give the attack a moment to spawn bones.
    await new Promise(r => setTimeout(r, 3000));
    const fin = snap('final');
    return { log, final: fin,
             attackListPresent: typeof window.c2_callFunction === 'function' };
})()`, true);

console.log("\n=== menu navigation trace ===");
for (const s of menu.log) {
    console.log(`  [${s.tag}] layout=${s.layout} MenuState=${s.MenuState} SimMode=${s.SimulatorMode} HP=${s.HP} TL=${s.tlRunning} bones=${s.bones} heartVis=${s.heartVisible} pos=${JSON.stringify(s.heartPos)}`);
}

if (menu.final.bones === 0 && menu.final.tlRunning !== 1) {
    console.log("\n!! no attack running after menu drive; the build needs a different entry path.");
}

// ---------------------------------------------------------------------------
// Phase 2: run the solver's plan for real, sampling HP + position.
// ---------------------------------------------------------------------------
const run = await evalJs(String.raw`(async () => {
    const rt = window.__rt, heart = window.__heart;
    const cm = heart.behavior_insts[0];
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
    const proto = rt.constructor.prototype;
    const origTick = proto.tick;
    let i = 0;

    const trace = await new Promise((resolve) => {
        proto.tick = function () {
            const a = actions[Math.min(i, actions.length - 1)] || [0, 0];
            setKeys({ left: a[0] < 0, right: a[0] > 0, up: a[1] > 0, down: a[1] < 0 });
            const r = origTick.apply(this, arguments);
            rows.push({
                i,
                x: +heart.x.toFixed(3), y: +heart.y.toFixed(3),
                hp: gv().HP, vis: heart.visible ? 1 : 0,
                cdx: +(cm.dx || 0).toFixed(3), cdy: +(cm.dy || 0).toFixed(3),
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

    const hpEnd = gv().HP;
    const cmp = [];
    for (let k = 0; k < trace.length; k += 10) {
        const r = trace[k];
        const lx = r.x - arena.c2_left;
        const ly = arena.c2_floor - r.y;
        const p = predicted[Math.min(k, predicted.length - 1)];
        cmp.push({ i: k, real: [+lx.toFixed(2), +ly.toFixed(2)], plan: [p[0], p[1]], dx: +(lx - p[0]).toFixed(2), dy: +(ly - p[1]).toFixed(2) });
    }
    // Did the heart ever actually move?
    const xs = new Set(trace.map(r => r.x));
    const ys = new Set(trace.map(r => r.y));
    const hpSeries = [...new Set(trace.map(r => r.hp))];
    return { hp0, hpEnd, n: trace.length, distinctX: xs.size, distinctY: ys.size, hpSeries, cmp, head: trace.slice(0, 10) };
})()`, true);

console.log("\n=== one round: real game vs solver plan ===");
console.log(`  HP ${run.hp0} -> ${run.hpEnd}   HP values seen: ${JSON.stringify(run.hpSeries)}`);
console.log(`  heart distinct positions: x=${run.distinctX} y=${run.distinctY}  (1/1 == never moved)`);
console.log("\n  i     real(local)     solver(local)    Δx       Δy");
for (const c of run.cmp) {
    console.log(`  ${String(c.i).padStart(4)}  ${JSON.stringify(c.real).padEnd(15)} ${JSON.stringify(c.plan).padEnd(15)} ${String(c.dx).padStart(7)} ${String(c.dy).padStart(7)}`);
}

console.log("\n  first ticks (pos / cm velocity / action):");
for (const r of run.head) {
    console.log(`   ${String(r.i).padStart(3)}  (${r.x}, ${r.y})  cm=(${r.cdx}, ${r.cdy})  a=${JSON.stringify(r.a)}  hp=${r.hp} vis=${r.vis}`);
}

const out = new URL("./.one_round.json", import.meta.url);
fs.writeFileSync(out, JSON.stringify({ plan: { wave: WAVE, arena: plan.arena, init: plan.initial_state }, menu: menu.log, run }, null, 2), "utf8");
console.log(`\nfull report -> ${out.pathname}`);

cdp.ws.close();
process.exit(0);

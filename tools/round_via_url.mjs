/**
 * Enters a SPECIFIC attack directly through the game's own supported deep link
 * (`?mode=single&attack=<name>`, see MainMenu.xml) and then runs the solver's
 * TAS against it, reporting real HP and trajectory.
 *
 * This removes the menu-navigation guesswork that made earlier attempts
 * meaningless: pressing Z on the main menu selects "Normal" mode, where the
 * heart is not player-controlled at all.
 *
 * Usage: node tools/round_via_url.mjs [httpPort] [cdpPort] [wave] [ticks]
 */

import fs from "node:fs";

const HTTP_PORT = process.argv[2] || "8099";
const CDP_PORT = process.argv[3] || "9222";
const WAVE = process.argv[4] || "sans_bonegap1";
const TICKS = Number(process.argv[5] || 150);
const URL_GAME = `http://127.0.0.1:${HTTP_PORT}/game/index.html?mode=single&attack=${WAVE}`;

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
await send("Page.enable");
await send("Runtime.enable");

const evalJs = async (expression, awaitPromise = false) => {
    const res = await send("Runtime.evaluate", { expression, awaitPromise, returnByValue: true });
    if (res.exceptionDetails) {
        const d = res.exceptionDetails;
        throw new Error(d.exception ? (d.exception.description || d.exception.value) : d.text);
    }
    return res.result.value;
};

const observe = () => evalJs(`(() => {
    const c = document.getElementById('c2canvas');
    const rt = window.c2runtime || (c && c.c2runtime);
    const gv = {};
    if (rt && rt.all_global_vars) rt.all_global_vars.forEach(v => { gv[v.name] = v.data; });
    const heart = rt ? (rt.types_by_index || []).find(t => t && t.name === 't55') : null;
    const inst = heart && heart.instances && heart.instances[0];
    let bones = 0, census = {};
    if (rt) for (const t of (rt.types_by_index || [])) {
        if (t && t.instances && t.instances.length) {
            census[t.name] = t.instances.length;
            if (/^t(30|31|36|37|38|43|66|67|70|71|72)$/.test(t.name)) bones += t.instances.length;
        }
    }
    let tl = null;
    try { tl = window.c2_callFunction ? window.c2_callFunction('TLIsRunning', []) : null; } catch (e) {}
    return {
        layout: rt && rt.running_layout && rt.running_layout.name,
        SimulatorMode: gv.SimulatorMode, SingleAttack: gv.SingleAttack,
        HP: gv.HP, KR: gv.KR, tlRunning: tl, bones,
        heart: inst ? [+inst.x.toFixed(2), +inst.y.toFixed(2)] : null,
        heartVisible: inst ? inst.visible : null,
    };
})()`);

const shot = async (name) => {
    const s = await send("Page.captureScreenshot", { format: "png", captureBeyondViewport: false });
    fs.writeFileSync(new URL("./" + name, import.meta.url), Buffer.from(s.data, "base64"));
};

console.log(`=== navigating: ${URL_GAME} ===`);
await send("Page.navigate", { url: URL_GAME });
await new Promise((r) => setTimeout(r, 12000));

let st = await observe();
console.log("after load:", JSON.stringify(st));
await shot("url_01_loaded.png");

// The deep link reaches BattleScreen with SimulatorMode = SINGLE, but the round
// has not begun: HP is still 0 from the menu and the timeline is idle.
// `StartAttack` is what resets the round (HP := MaxHP, KR := 0, Failed := 0).
if (st.HP <= 0) {
    console.log("\n=== player is in the menu death state; firing StartAttack to begin the round ===");
    await evalJs(`(() => { window.c2_callFunction('StartAttack', []); return true; })()`);
    await new Promise((r) => setTimeout(r, 2500));
    st = await observe();
    console.log("after StartAttack:", JSON.stringify(st));
    await shot("url_01b_startattack.png");
}

// Wait for the attack to actually start (bones appear).
for (let i = 0; i < 20; i++) {
    if (st.bones > 0 || st.tlRunning === 1) break;
    await new Promise((r) => setTimeout(r, 1000));
    st = await observe();
}
console.log("attack start check:", JSON.stringify(st));
await shot("url_02_attack.png");

// Fetch the solver plan for whatever the game says is running.
const plan = await fetch(`http://127.0.0.1:${HTTP_PORT}/api/tas?wave=${WAVE}.csv&T=${TICKS}&soul_w=4&soul_h=4&physics_mode=c2`).then((r) => r.json());
console.log(`\nsolver plan: actions=${plan.action_sequence ? plan.action_sequence.length : "none"} deadlock=${plan.is_deadlock} init=${JSON.stringify(plan.initial_state)}`);
if (!plan.action_sequence) { console.log("no plan; stopping"); cdp.ws.close(); process.exit(2); }

// Run the TAS for real.
const run = await evalJs(`(async () => {
    const rt = window.c2runtime || document.getElementById('c2canvas').c2runtime;
    const heart = (rt.types_by_index || []).find(t => t && t.name === 't55').instances[0];
    const cm = heart.behavior_insts[0];
    const kb = (rt.types_by_index || []).map(t => t && t.instances && t.instances[0]).find(i => i && i.keyMap);
    const gv = () => { const o = {}; (rt.all_global_vars || []).forEach(v => { o[v.name] = v.data; }); return o; };
    const actions = ${JSON.stringify(plan.action_sequence)};
    const arena = ${JSON.stringify(plan.arena)};
    const predicted = ${JSON.stringify(plan.trajectory)};

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
                i, x: +heart.x.toFixed(3), y: +heart.y.toFixed(3),
                hp: gv().HP, vis: heart.visible ? 1 : 0,
                cdx: +(cm.dx || 0).toFixed(2), cdy: +(cm.dy || 0).toFixed(2), a,
            });
            i++;
            if (i >= ${TICKS}) { proto.tick = origTick; setKeys({}); resolve(rows); }
            return r;
        };
    });
    const hpEnd = gv().HP;
    const cmps = [];
    for (let k = 0; k < trace.length; k += 10) {
        const r = trace[k];
        const lx = r.x - arena.c2_left, ly = arena.c2_floor - r.y;
        const p = predicted[Math.min(k, predicted.length - 1)];
        cmps.push({ i: k, real: [+lx.toFixed(2), +ly.toFixed(2)], plan: [p[0], p[1]], dx: +(lx - p[0]).toFixed(2), dy: +(ly - p[1]).toFixed(2) });
    }
    const xs = new Set(trace.map(r => r.x)), ys = new Set(trace.map(r => r.y));
    return { hp0, hpEnd, n: trace.length, distinctX: xs.size, distinctY: ys.size, cmps, head: trace.slice(0, 12) };
})()`, true);

console.log(`\n=== ONE ROUND RESULT ===`);
console.log(`  HP ${run.hp0} -> ${run.hpEnd}  ${run.hpEnd < run.hp0 ? "*** TOOK DAMAGE ***" : "(no damage)"}`);
console.log(`  heart distinct positions: x=${run.distinctX} y=${run.distinctY}`);
console.log(`\n  i     real(local)     solver(local)    Δx       Δy`);
for (const c of run.cmps) {
    console.log(`  ${String(c.i).padStart(4)}  ${JSON.stringify(c.real).padEnd(15)} ${JSON.stringify(c.plan).padEnd(15)} ${String(c.dx).padStart(7)} ${String(c.dy).padStart(7)}`);
}
console.log(`\n  first ticks:`);
for (const r of run.head) {
    console.log(`   ${String(r.i).padStart(3)} (${r.x}, ${r.y}) cm=(${r.cdx},${r.cdy}) a=${JSON.stringify(r.a)} hp=${r.hp} vis=${r.vis}`);
}
await shot("url_03_after_tas.png");

fs.writeFileSync(new URL("./.round_url.json", import.meta.url), JSON.stringify({ plan: { wave: WAVE, arena: plan.arena, init: plan.initial_state }, run }, null, 2), "utf8");
cdp.ws.close();
process.exit(run.hpEnd < run.hp0 ? 1 : 0);

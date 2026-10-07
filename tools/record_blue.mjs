/**
 * Records a real BLUE-heart attack and dumps the per-tick motion as CSV on
 * stdout, so the authoritative stepper can be calibrated against it.
 *
 * The menu sequence used is the practice-mode one:
 *   Z -> FIGHT -> choose attack -> confirm
 * Single-attack / practice selection is driven by the engine's own
 * c2_callFunction("SetPracticeAttack", [name]) when available.
 *
 * Usage: node tools/record_blue.mjs [httpPort] [cdpPort] <attack> [ticks]
 */

const HTTP_PORT = process.argv[2] || "8099";
const CDP_PORT = process.argv[3] || "9333";
const ATTACK = process.argv[4] || "sans_bluebone";
const TICKS = Number(process.argv[5] || 300);
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

// MainMenu needs one confirm to enter BattleScreen.
const afterConfirm = await evalJs(String.raw`(() => {
    const rt = window.c2runtime || document.getElementById('c2canvas').c2runtime;
    window.__rt = rt;
    const press = (w, hold) => {
        const mk = (t) => new KeyboardEvent(t, { which: w, keyCode: w, bubbles: true, cancelable: true });
        document.dispatchEvent(mk('keydown'));
        setTimeout(() => document.dispatchEvent(mk('keyup')), hold || 110);
    };
    press(90);
    setTimeout(() => {
        // Configure a single practice attack if the engine supports it.
        try {
            if (typeof window.c2_callFunction === 'function') {
                window.c2_callFunction('SetSimulatorMode', ['MODE_SINGLE']);
            }
        } catch (e) { /* optional */ }
    }, 900);
    return true;
})()`);
void afterConfirm;
await new Promise((r) => setTimeout(r, 2500));

const menu = await evalJs(String.raw`(() => {
    const rt = window.__rt;
    const t55 = (rt.types_by_index || []).find(t => t && t.name === 't55');
    window.__heart = t55.instances[0];
    window.__cm = window.__heart.behavior_insts[0];
    const gv = {};
    (rt.all_global_vars || []).forEach(v => { gv[v.name] = v.data; });
    return {
        layout: rt.running_layout && rt.running_layout.name,
        SimulatorMode: gv.SimulatorMode,
        SingleAttack: gv.SingleAttack,
        MenuState: gv.MenuState,
        dt: rt.dt, fps: rt.fps,
        cm: { dx: window.__cm.dx, dy: window.__cm.dy, stepMode: window.__cm.stepMode, pxPerStep: window.__cm.pxPerStep, props: window.__cm.properties },
    };
})()`);
console.log("=== after first confirm ===");
console.log(JSON.stringify(menu, null, 2));

// Press Z a few times to run FIGHT -> practice attack list -> start.
const driven = await evalJs(String.raw`(() => {
    const press = (w) => {
        const mk = (t) => new KeyboardEvent(t, { which: w, keyCode: w, bubbles: true, cancelable: true });
        document.dispatchEvent(mk('keydown'));
        setTimeout(() => document.dispatchEvent(mk('keyup')), 110);
    };
    for (let i = 0; i < 4; i++) setTimeout(() => press(90), i * 800);
    // Also nudge down once in case the menu needs a selection move.
    setTimeout(() => press(40), 400);
    return true;
})()`);
void driven;
await new Promise((r) => setTimeout(r, 4500));

const state = await evalJs(String.raw`(() => {
    const rt = window.__rt, h = window.__heart, cm = window.__cm;
    const gv = {};
    (rt.all_global_vars || []).forEach(v => { gv[v.name] = v.data; });
    return {
        layout: rt.running_layout && rt.running_layout.name,
        tick: rt.tickcount, dt: rt.dt,
        pos: { x: h.x, y: h.y },
        visible: h.visible,
        mode: h.instance_vars ? h.instance_vars[0] : null,
        cm: { dx: cm.dx, dy: cm.dy },
        globals: { SimulatorMode: gv.SimulatorMode, SingleAttack: gv.SingleAttack, MenuState: gv.MenuState, HP: gv.HP },
    };
})()`);
console.log("\n=== after menu drive ===");
console.log(JSON.stringify(state, null, 2));

// Record with a scripted jump+walk input pattern so the vertical dynamics fire.
const trace = await evalJs(String.raw`(() => {
    const rt = window.__rt, h = window.__heart, cm = window.__cm;
    const kb = (rt.types_by_index || []).map(t => t && t.instances && t.instances[0]).find(i => i && i.keyMap);
    const rows = [];
    const setKeys = (up, down, left, right) => {
        if (!kb) return;
        kb.keyMap[38] = !!up; kb.keyMap[87] = !!up;
        kb.keyMap[40] = !!down; kb.keyMap[83] = !!down;
        kb.keyMap[37] = !!left; kb.keyMap[65] = !!left;
        kb.keyMap[39] = !!right; kb.keyMap[68] = !!right;
    };
    for (let i = 0; i < ${TICKS}; i++) {
        // Scripted pattern: hold UP for 20 ticks, rest, hold RIGHT for 20, rest.
        const phase = i % 80;
        if (phase < 20) setKeys(1, 0, 0, 0);
        else if (phase < 40) setKeys(0, 0, 0, 0);
        else if (phase < 60) setKeys(0, 0, 0, 1);
        else setKeys(0, 0, 0, 0);
        const b = { x: h.x, y: h.y, t: rt.tickcount };
        rt.tick(false, performance.now(), false);
        rows.push([
            i, +h.x.toFixed(6), +h.y.toFixed(6),
            +(h.x - b.x).toFixed(6), +(h.y - b.y).toFixed(6),
            +(cm.dx || 0).toFixed(6), +(cm.dy || 0).toFixed(6),
            h.instance_vars ? h.instance_vars[0] : -1,
            rt.dt,
        ]);
    }
    return rows;
})()`);

console.log("\n=== CSV: i,x,y,dx_step,dy_step,cm.dx,cm.dy,mode,dt ===");
for (const r of trace) console.log(r.join(","));

cdp.ws.close();
process.exit(0);

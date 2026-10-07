/**
 * Extracts the REAL movement dynamics of PlayerHeart from the compiled export.
 *
 * The source event sheets drive the heart through the CustomMovement BEHAVIOUR
 * (PlayerHeart.CustomMovement.dx / .dy, "On horizontal step" / "On vertical
 * step"), so the behaviour object has to be located before anything can be
 * measured:
 *
 *     heart.behaviors[heart.getBehaviorIndexByName("CustomMovement")]
 *
 * Experiments (all inside the live engine, one rt.tick per sample):
 *   1. walk probe      : set dx = +150, tick twice -> positions reveal the
 *                        per-tick displacement AND whether a speed set during
 *                        tick t is consumed by tick t or by tick t+1.
 *   2. gravity ladder  : set dy and watch dy/y evolve -> recovers the
 *                        DownSpeed -> Gravity table actually compiled in.
 *   3. free fall       : drop the heart to the floor -> reveals the landing
 *                        rule (integer snap vs. fractional clamp) and the
 *                        terminal velocity.
 *
 * Usage: node tools/extract_dynamics.mjs [httpPort] [cdpPort]
 */

const HTTP_PORT = process.argv[2] || "8099";
const CDP_PORT = process.argv[3] || "9222";
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
            setTimeout(() => { if (this.pending.delete(id)) rej(new Error("timeout " + method)); }, 40000);
        });
    }
}

const targets = await fetch(`http://127.0.0.1:${CDP_PORT}/json/list`).then((r) => r.json());
const page = targets.find((t) => t.type === "page");
if (!page) {
    console.error("no page target on CDP", CDP_PORT);
    process.exit(1);
}
const cdp = new CDP(page.webSocketDebuggerUrl);
await cdp.ready;
const { sessionId } = await cdp.send("Target.attachToTarget", { targetId: page.id, flatten: true });
const send = (m, p) => cdp.send(m, p, sessionId);
await send("Runtime.enable");
await send("Page.navigate", { url: PAGE_URL });
await new Promise((r) => setTimeout(r, 7000));

const evalJs = async (expression, awaitPromise = false) => {
    const res = await send("Runtime.evaluate", { expression, awaitPromise, returnByValue: true });
    if (res.exceptionDetails) {
        const d = res.exceptionDetails;
        throw new Error(d.exception ? (d.exception.description || d.exception.value) : d.text);
    }
    return res.result.value;
};

// --- enter the battle screen, then locate the heart + its behaviour ---------
const boot = await evalJs(`(() => {
    const press = (w) => {
        const mk = (t) => new KeyboardEvent(t, { which: w, keyCode: w, bubbles: true, cancelable: true });
        document.dispatchEvent(mk('keydown'));
        setTimeout(() => document.dispatchEvent(mk('keyup')), 120);
    };
    press(90); setTimeout(() => press(90), 700); setTimeout(() => press(90), 1400);
    return true;
})()`);
void boot;
await new Promise((r) => setTimeout(r, 3200));

const info = await evalJs(`(() => {
    const rt = window.c2runtime || document.getElementById('c2canvas').c2runtime;
    window.__rt = rt;
    const t55 = (rt.types_by_index || []).find(t => t && t.name === 't55');
    const heart = t55.instances[0];
    window.__heart = heart;
    const idxByName = heart.getBehaviorIndexByName ? heart.getBehaviorIndexByName('CustomMovement') : -1;
    const beh = heart.behaviors && heart.behaviors[idxByName];
    window.__cm = beh;
    return {
        layout: rt.running_layout && rt.running_layout.name,
        dt: rt.dt, fps: rt.fps, tickcount: rt.tickcount,
        heartPos: { x: heart.x, y: heart.y },
        behaviorIndex: idxByName,
        behaviorKeys: beh ? Object.keys(beh) : null,
        speedKeys: beh ? { dx: beh.dx, dy: beh.dy } : null,
        instanceVarNames: heart.instance_vars ? heart.instance_vars.length : 0,
    };
})()`);
console.log("=== boot state ===");
console.log(JSON.stringify(info, null, 2));

if (!info.behaviorKeys) {
    console.log("\n!! CustomMovement behaviour not found; dumping heart behaviours");
    const dump = await evalJs(`(() => {
        const h = window.__heart;
        return (h.behaviors || []).map((b, i) => ({
            i,
            ctor: b && b.constructor && b.constructor.name,
            keys: b ? Object.keys(b).slice(0, 25) : null,
        }));
    })()`);
    console.log(JSON.stringify(dump, null, 2));
    cdp.ws.close();
    process.exit(2);
}

// ---------------------------------------------------------------------------
// Experiment 1: walk probe
// ---------------------------------------------------------------------------
const walk = await evalJs(`(() => {
    const rt = window.__rt, h = window.__heart, cm = window.__cm;
    const rows = [];
    const reset = (x, y) => { h.x = x; h.y = y; cm.dx = 0; cm.dy = 0; rt.tick(false, performance.now(), false); };
    reset(320, 320);
    const base = { x: h.x, y: h.y, dx: cm.dx, dy: cm.dy };
    cm.dx = 150;                                   // HEARTSPEED
    rt.tick(false, performance.now(), false);
    rows.push({ tick: 1, x: h.x, dx: cm.dx });
    rt.tick(false, performance.now(), false);
    rows.push({ tick: 2, x: h.x, dx: cm.dx });
    cm.dx = 0;
    rt.tick(false, performance.now(), false);
    rows.push({ tick: 3, x: h.x, dx: cm.dx });
    rt.tick(false, performance.now(), false);
    rows.push({ tick: 4, x: h.x, dx: cm.dx });
    return { base, dt: rt.dt, rows };
})()`);
console.log("\n=== experiment 1: dx=150 walk probe ===");
console.log(JSON.stringify(walk, null, 2));

// ---------------------------------------------------------------------------
// Experiment 2: gravity ladder
// ---------------------------------------------------------------------------
const grav = await evalJs(`(() => {
    const rt = window.__rt, h = window.__heart, cm = window.__cm;
    const run = (vy0) => {
        h.x = 320; h.y = 320; cm.dx = 0; cm.dy = vy0;
        const seq = [];
        for (let i = 0; i < 7; i++) {
            rt.tick(false, performance.now(), false);
            seq.push([+cm.dy.toFixed(5), +h.y.toFixed(5)]);
        }
        return seq;
    };
    return {
        dt: rt.dt,
        'dy=0': run(0),
        'dy=+150': run(150),
        'dy=+300': run(300),
        'dy=-100': run(-100),
        'dy=-200': run(-200),
        'dy=-450': run(-450),
        'dy=-750': run(-750),
        'dy=-900': run(-900),
    };
})()`);
console.log("\n=== experiment 2: [dy, y] per tick for several initial dy ===");
console.log(JSON.stringify(grav, null, 2));

// ---------------------------------------------------------------------------
// Experiment 3: landing
// ---------------------------------------------------------------------------
const land = await evalJs(`(() => {
    const rt = window.__rt, h = window.__heart, cm = window.__cm;
    h.x = 320; h.y = 320; cm.dx = 0; cm.dy = 0;
    const trace = [];
    for (let i = 0; i < 200; i++) {
        rt.tick(false, performance.now(), false);
        trace.push([+h.y.toFixed(5), +cm.dy.toFixed(5)]);
    }
    let landIdx = -1;
    for (let i = 1; i < trace.length; i++) {
        if (trace[i][1] === 0 && trace[i - 1][1] < 0) { landIdx = i; break; }
    }
    return { dt: rt.dt, landIdx, window: trace.slice(Math.max(0, landIdx - 6), landIdx + 4) };
})()`);
console.log("\n=== experiment 3: free fall from y=320 -> landing ===");
console.log(JSON.stringify(land, null, 2));

cdp.ws.close();
process.exit(0);

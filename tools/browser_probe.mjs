/**
 * Focused browser probe: is the live PlayerHeart driven by the engine from the
 * CSV teleport anchor, and how does it move across real ticks?
 *
 * Usage: node tools/browser_probe.mjs [httpPort] [cdpPort] [wave]
 */

const HTTP_PORT = process.argv[2] || "8099";
const CDP_PORT = process.argv[3] || "9222";
const WAVE = process.argv[4] || "sans_bonegap1";
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
            setTimeout(() => { if (this.pending.delete(id)) rej(new Error("timeout " + method)); }, 30000);
        });
    }
}

const targets = await fetch(`http://127.0.0.1:${CDP_PORT}/json/list`).then((r) => r.json());
const page = targets.find((t) => t.type === "page");
const cdp = new CDP(page.webSocketDebuggerUrl);
await cdp.ready;
const { sessionId } = await cdp.send("Target.attachToTarget", { targetId: page.id, flatten: true });
const send = (m, p) => cdp.send(m, p, sessionId);
await send("Runtime.enable");
await send("Page.navigate", { url: PAGE_URL });
await new Promise((r) => setTimeout(r, 6000));

const evalJs = async (expression, awaitPromise = false) => {
    const res = await send("Runtime.evaluate", { expression, awaitPromise, returnByValue: true });
    if (res.exceptionDetails) {
        const d = res.exceptionDetails;
        throw new Error(d.exception ? (d.exception.description || d.exception.value) : d.text);
    }
    return res.result.value;
};

const out = await evalJs(`(async () => {
    const T = window.TASRunner;
    const rt = window.c2runtime || document.getElementById('c2canvas').c2runtime;
    const heart = T.getHeartInstance();
    const arena = T.getArena();
    const st = await fetch('/api/tas?wave=${WAVE}.csv&T=150&soul_w=4&soul_h=4&physics_mode=c2').then(r => r.json());
    const trace = [];
    const snap = (label) => {
        const h = T.getHeartInstance();
        const p = T.getHeartPos();
        trace.push({ label, x: h && h.x, y: h && h.y, local: p ? [Math.round(p.x), Math.round(p.y)] : null });
    };
    snap('after-load');
    // Place the heart exactly at the CSV HeartTeleport anchor.
    heart.x = arena.c2_left + st.initial_state[0];
    heart.y = arena.c2_floor - st.initial_state[1];
    snap('after-place');
    // One real tick only.
    rt.tick(false, performance.now(), false);
    snap('tick1');
    rt.tick(false, performance.now(), false);
    snap('tick2');
    rt.tick(false, performance.now(), false);
    snap('tick3');
    // Now arm the TAS and watch 20 ticks.
    T.startPlayback();
    await new Promise(r => setTimeout(r, 150));
    for (let i = 0; i < 20; i++) {
        rt.tick(false, performance.now(), false);
        if (i % 5 === 4) snap('tas+' + (i + 1));
    }
    T.resetPlayback();
    // Inspect candidate state holders.
    const localVars = (rt.all_local_vars || []).map(v => ({ n: v.name, d: v.data }));
    const globals = (rt.all_global_vars || []).map(v => ({ n: v.name, d: v.data }));
    return {
        arena,
        initial: st.initial_state,
        isDeadlock: st.is_deadlock,
        trace,
        state: T.getState(),
        localCount: localVars.length,
        globals,
        layout: rt.running_layout && rt.running_layout.name,
        canvasW: document.getElementById('c2canvas').width,
        canvasH: document.getElementById('c2canvas').height,
    };
})()`, true);

console.log(JSON.stringify(out, null, 2));
cdp.ws.close();
process.exit(0);

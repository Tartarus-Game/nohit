/**
 * scratch_B_state.mjs — one-shot state dump from the live game page.
 * Usage: node tools/scratch_B_state.mjs [cdpPort]
 */
const CDP_PORT = process.argv[2] || "9444";

class CDP {
    constructor(wsUrl) {
        this.ws = new WebSocket(wsUrl); this.id = 0; this.pending = new Map();
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
        const id = ++this.id; const p = { id, method, params };
        if (sessionId) p.sessionId = sessionId;
        this.ws.send(JSON.stringify(p));
        return new Promise((res, rej) => {
            this.pending.set(id, { resolve: res, reject: rej });
            setTimeout(() => { if (this.pending.delete(id)) rej(new Error("timeout " + method)); }, 60000);
        });
    }
}

const targets = await fetch(`http://127.0.0.1:${CDP_PORT}/json/list`).then((r) => r.json());
console.log("targets:", targets.map(t => `${t.type} ${t.url}`).join("\n  "));
const page = targets.find((t) => t.type === "page" && !/chrome-extension/.test(t.url || ""));
if (!page) { console.error("no page target"); process.exit(1); }
const cdp = new CDP(page.webSocketDebuggerUrl);
await cdp.ready;
const { sessionId } = await cdp.send("Target.attachToTarget", { targetId: page.id, flatten: true });
const send = (m, p) => cdp.send(m, p, sessionId);
await send("Runtime.enable");

const evalJs = async (expression) => {
    const res = await send("Runtime.evaluate", { expression, returnByValue: true, awaitPromise: true });
    if (res.exceptionDetails) {
        const d = res.exceptionDetails;
        throw new Error(d.exception ? (d.exception.description || d.exception.value) : d.text);
    }
    return res.result.value;
};

const st = await evalJs(`(() => {
    const c = document.getElementById('c2canvas');
    const rt = window.c2runtime || (c && c.c2runtime);
    if (!rt) return { err: 'no rt', hasWin: !!window.c2runtime, hasCanvas: !!c };
    const gv = {}; (rt.all_global_vars || []).forEach(v => { gv[v.name] = v.data; });
    const census = {};
    (rt.types_by_index || []).forEach(t => { if (t && t.instances && t.instances.length) census[t.name] = t.instances.length; });
    let tl = null; try { tl = window.c2_callFunction('TLIsRunning', []); } catch (e) { tl = 'ERR:' + e.message; }
    return {
        hasWinRuntime: !!window.c2runtime,
        dt: rt.dt, fps: rt.fps, tickcount: rt.tickcount, timescale: rt.timescale,
        layout: rt.running_layout && rt.running_layout.name,
        hooked: !!rt.__vbHooked, vbtick: window.__vbTick, recLen: (window.__vbRec || []).length,
        gv: { HP: gv.HP, KR: gv.KR, SimulatorMode: gv.SimulatorMode, SingleAttack: gv.SingleAttack,
              Failed: gv.Failed, SansState: gv.SansState, AttackTimer: gv.AttackTimer,
              AttackRunning: gv.AttackRunning, TimelineRunning: gv.TimelineRunning },
        censusAll: census,
        tlRunning: tl,
        rtKeys: Object.keys(rt).filter(k => /tick|raf/i.test(k)),
    };
})()`);
console.log(JSON.stringify(st, null, 1));
cdp.ws.close();
process.exit(0);

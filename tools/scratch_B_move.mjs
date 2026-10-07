/**
 * scratch_B_move.mjs — measures per-tick movement of a directly-spawned bone
 * group, to confirm the speed sign per direction.
 * Usage: node tools/scratch_B_move.mjs [cdpPort]
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
const page = targets.find((t) => t.type === "page" && !/chrome-extension/.test(t.url || ""));
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

// Spawn one direction-0 group and one direction-2 group, tag them, and record
// (tick, x) for a while.
const setup = await evalJs(`(() => {
    const c = document.getElementById('c2canvas');
    const rt = window.c2runtime || (c && c.c2runtime);
    const T31 = (rt.types_by_index || []).find(t => t && t.name === 't31');
    // clear
    for (const i of [...T31.instances]) i.destroy();
    window.c2_callFunction('BoneVRepeat', [128, 257, 95, 0, 180, 8, 120]);
    window.c2_callFunction('BoneVRepeat', [503, 257, 95, 2, 180, 8, 120]);
    window.__mv = { ticks: [], uids: T31.instances.map(i => i.uid) };
    const proto = rt.constructor.prototype;
    const orig = proto.tick || rt.tick;
    window.__mvTick = 0;
    proto.tick = function () {
        const r = orig.apply(this, arguments);
        window.__mvTick++;
        const row = { tick: window.__mvTick, xs: {} };
        for (const i of T31.instances) row.xs[i.uid] = i.x;
        window.__mv.ticks.push(row);
        return r;
    };
    return { n: T31.instances.length, uids: window.__mv.uids };
})()`);
console.log("setup:", JSON.stringify(setup));

await new Promise((r) => setTimeout(r, 3000));

const mv = await evalJs(`(() => {
    const m = window.__mv;
    const rows = m.ticks;
    if (rows.length < 2) return { n: rows.length, note: 'too few ticks' };
    const first = rows[0], last = rows[rows.length - 1];
    const per = [];
    for (const uid of m.uids) {
        const a = first.xs[uid], b = last.xs[uid];
        if (a === undefined || b === undefined) { per.push({ uid, gone: true }); continue; }
        per.push({ uid, x0: a, x1: b, ticks: last.tick - first.tick,
                   delta: +(b - a).toFixed(3),
                   perTick: +((b - a) / (last.tick - first.tick)).toFixed(5) });
    }
    return { tickSpan: last.tick - first.tick, uids: m.uids, per,
             sample: rows.slice(0, 4).map(r => ({ tick: r.tick, xs: Object.values(r.xs) })) };
})()`);
console.log(JSON.stringify(mv, null, 1));
cdp.ws.close();
process.exit(0);

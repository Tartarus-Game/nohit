/**
 * scratch_B_why.mjs — hooks t31 destroy() to find WHO kills the bones, and
 * simultaneously samples positions per tick so we can measure velocity while
 * the bones are alive.
 * Usage: node tools/scratch_B_why.mjs [cdpPort]
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

const setup = await evalJs(`(() => {
    const c = document.getElementById('c2canvas');
    const rt = window.c2runtime || (c && c.c2runtime);
    const T31 = (rt.types_by_index || []).find(t => t && t.name === 't31');
    for (const i of [...T31.instances]) i.destroy();

    window.__why = { destroys: [], samples: [] };
    window.__whyTick = 0;

    // hook destroy on the prototype chain used by t31 instances
    const proto = Object.getPrototypeOf(T31.instances[0] || new T31.plugin.Instance(T31));
    const chain = [];
    let p = proto;
    while (p && p !== Object.prototype) { chain.push(p); p = Object.getPrototypeOf(p); }
    let origDestroy = null, owner = null;
    for (const lvl of chain) {
        if (typeof lvl.destroy === 'function') { origDestroy = lvl.destroy; owner = lvl; break; }
    }
    window.__why.chain = chain.map(l => l.constructor && l.constructor.name);
    if (origDestroy) {
        owner.destroy = function () {
            const st = new Error('destroy').stack;
            window.__why.destroys.push({ tick: window.__whyTick, x: this.x, y: this.y,
                h: this.height, uid: this.uid, stack: String(st).split('\\n').slice(0, 5) });
            return origDestroy.apply(this, arguments);
        };
        window.__why.hookedDestroy = true;
    }

    // spawn both groups
    window.c2_callFunction('BoneVRepeat', [128, 257, 95, 0, 180, 8, 120]);
    window.c2_callFunction('BoneVRepeat', [503, 257, 95, 2, 180, 8, 120]);
    window.__why.uids = T31.instances.map(i => i.uid);

    const rtp = rt.constructor.prototype;
    const origTick = rtp.tick || rt.tick;
    rtp.tick = function () {
        const r = origTick.apply(this, arguments);
        window.__whyTick++;
        if (window.__whyTick <= 30) {
            window.__why.samples.push({ tick: window.__whyTick,
                xs: T31.instances.map(i => [i.uid, i.x]) });
        }
        return r;
    };
    return { n: T31.instances.length, uids: window.__why.uids, hooked: !!origDestroy };
})()`);
console.log("setup:", JSON.stringify(setup));

await new Promise((r) => setTimeout(r, 2500));

const why = await evalJs(`(() => ({
    ticks: window.__whyTick,
    destroys: window.__why.destroys.slice(0, 20),
    nDestroy: window.__why.destroys.length,
    samples: window.__why.samples,
    chain: window.__why.chain,
    hookedDestroy: window.__why.hookedDestroy,
}))()`);
console.log(JSON.stringify(why, null, 1));
cdp.ws.close();
process.exit(0);

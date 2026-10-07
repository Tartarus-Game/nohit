/**
 * Introspects where the compiled export actually keeps PlayerHeart's movement
 * state. The authoritative source touches `PlayerHeart.CustomMovement.dx/.dy`
 * via `Set speed (CustomMovement)`, so this finds the backing object/properties
 * and dumps every candidate so the real dynamics can be measured.
 *
 * Usage: node tools/probe_heart.mjs [httpPort] [cdpPort]
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

await evalJs(`(() => {
    const press = (w) => {
        const mk = (t) => new KeyboardEvent(t, { which: w, keyCode: w, bubbles: true, cancelable: true });
        document.dispatchEvent(mk('keydown'));
        setTimeout(() => document.dispatchEvent(mk('keyup')), 120);
    };
    press(90); setTimeout(() => press(90), 700); setTimeout(() => press(90), 1400);
    return true;
})()`);
await new Promise((r) => setTimeout(r, 3000));

const dump = await evalJs(`(() => {
    const rt = window.c2runtime || document.getElementById('c2canvas').c2runtime;
    const t55 = (rt.types_by_index || []).find(t => t && t.name === 't55');
    const heart = t55.instances[0];

    const ownKeys = Object.keys(heart);
    const protoKeys = [];
    let p = Object.getPrototypeOf(heart);
    while (p && p !== Object.prototype) {
        protoKeys.push(...Object.getOwnPropertyNames(p));
        p = Object.getPrototypeOf(p);
    }

    // Anything that smells like movement state.
    const candidates = {};
    for (const k of ownKeys) {
        const v = heart[k];
        if (v === null || v === undefined) continue;
        if (typeof v === 'object') {
            candidates[k] = { kind: 'object', ctor: v.constructor && v.constructor.name, keys: Object.keys(v).slice(0, 30) };
        } else if (/speed|movement|dx|dy|gravity|velocity/i.test(k)) {
            candidates[k] = { kind: typeof v, value: v };
        }
    }

    // The behaviour system: C2 keeps behaviours on the TYPE and on the instance.
    const behOnHeart = heart.behaviors ? heart.behaviors.length : -1;
    const typeBehs = t55.behaviors ? t55.behaviors.length : -1;
    const typeBehNames = [];
    if (Array.isArray(t55.behaviors)) {
        for (let i = 0; i < t55.behaviors.length; i++) {
            const b = t55.behaviors[i];
            typeBehNames.push(b && b.constructor && b.constructor.name);
        }
    }
    // behaviourTypes on the type
    const btypes = t55.behaviorTypes ? t55.behaviorTypes.length : -1;
    const btypeInfo = [];
    if (Array.isArray(t55.behaviorTypes)) {
        for (const bt of t55.behaviorTypes) {
            btypeInfo.push({
                name: bt && bt.name,
                klass: bt && bt.behavior && bt.behavior.constructor && bt.behavior.constructor.name,
            });
        }
    }

    // C2 stores instance behaviour state in `heart.behavior_insts`
    const binsts = heart.behavior_insts ? heart.behavior_insts.length : -1;
    const binstInfo = [];
    if (Array.isArray(heart.behavior_insts)) {
        for (const bi of heart.behavior_insts) {
            binstInfo.push({ ctor: bi && bi.constructor && bi.constructor.name, keys: bi ? Object.keys(bi).slice(0, 30) : null });
        }
    }

    return {
        layout: rt.running_layout && rt.running_layout.name,
        dt: rt.dt, fps: rt.fps,
        heartPos: { x: heart.x, y: heart.y },
        instanceVars: heart.instance_vars,
        ownKeys,
        protoKeys: [...new Set(protoKeys)].slice(0, 80),
        movementCandidates: candidates,
        behOnHeart, typeBehs, typeBehNames, btypes, btypeInfo, binsts, binstInfo,
    };
})()`);

console.log(JSON.stringify(dump, null, 2));
cdp.ws.close();
process.exit(0);

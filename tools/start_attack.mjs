/**
 * Picks the attack at the current cursor position in the Single-attack list and
 * confirms the round actually started (bones exist, timeline running, heart
 * teleported).
 *
 * Usage: node tools/start_attack.mjs [httpPort] [cdpPort] [downs]
 */

import fs from "node:fs";

const HTTP_PORT = process.argv[2] || "8099";
const CDP_PORT = process.argv[3] || "9222";
const DOWNS = Number(process.argv[4] || 0);

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

const state = async () => evalJs(`(() => {
    const c = document.getElementById('c2canvas');
    const rt = window.c2runtime || (c && c.c2runtime);
    const gv = {};
    if (rt && rt.all_global_vars) rt.all_global_vars.forEach(v => { gv[v.name] = v.data; });
    const heart = rt ? (rt.types_by_index || []).find(t => t && t.name === 't55') : null;
    const inst = heart && heart.instances && heart.instances[0];
    // Count bone-family instances actually alive in the world.
    let bones = 0, census = {};
    if (rt) for (const t of (rt.types_by_index || [])) {
        if (t && t.instances && t.instances.length) {
            census[t.name] = t.instances.length;
            if (/^t(30|31|34|35|36|37|38|43|66|67|70|71|72)$/.test(t.name)) bones += t.instances.length;
        }
    }
    let tl = null;
    try { tl = window.c2_callFunction ? window.c2_callFunction('TLIsRunning', []) : null; } catch (e) {}
    return {
        layout: rt && rt.running_layout && rt.running_layout.name,
        HP: gv.HP, SimulatorMode: gv.SimulatorMode, SingleAttack: gv.SingleAttack,
        tlRunning: tl, bones,
        heart: inst ? [+inst.x.toFixed(2), +inst.y.toFixed(2)] : null,
        heartVisible: inst ? inst.visible : null,
        census,
    };
})()`);

const press = async (which, key, holdMs = 120) => {
    await evalJs(`(() => {
        const mk = (t) => new KeyboardEvent(t, { which: ${which}, keyCode: ${which}, key: ${JSON.stringify(key)}, bubbles: true, cancelable: true });
        document.dispatchEvent(mk('keydown'));
        window.dispatchEvent(mk('keydown'));
        setTimeout(() => { document.dispatchEvent(mk('keyup')); window.dispatchEvent(mk('keyup')); }, ${holdMs});
        return true;
    })()`);
    await new Promise((r) => setTimeout(r, holdMs + 450));
};

const shot = async (name) => {
    const s = await send("Page.captureScreenshot", { format: "png", captureBeyondViewport: false });
    fs.writeFileSync(new URL("./" + name, import.meta.url), Buffer.from(s.data, "base64"));
};

if (DOWNS > 0) {
    console.log(`=== moving cursor down ${DOWNS} ===`);
    for (let i = 0; i < DOWNS; i++) await press(40, "ArrowDown");
}

console.log("=== before confirm ===");
console.log(JSON.stringify(await state(), null, 2));

console.log("\n=== press Z to start the attack ===");
await press(90, "z");
await new Promise((r) => setTimeout(r, 1200));
console.log(JSON.stringify(await state(), null, 2));
await shot("attack_01_started.png");

// Let the attack actually run a bit.
await new Promise((r) => setTimeout(r, 3500));
console.log("\n=== ~4.7s into the round ===");
console.log(JSON.stringify(await state(), null, 2));
await shot("attack_02_running.png");

cdp.ws.close();
process.exit(0);

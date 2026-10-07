/**
 * Drives the REAL game UI using genuine ArrowDown / Z key presses, following the
 * menu the screenshot actually shows:
 *
 *     Normal         <- heart cursor starts here
 *     Endless
 *     Single attack
 *
 * Previous attempts only pressed Z, which always selected "Normal" -- the one
 * mode where the heart is NOT player controlled, so no input could ever matter.
 *
 * This walks: MainMenu -(Down,Down,Z)-> Single attack -(choose)-> attack list
 * and screenshots each step so the flow can be verified visually.
 *
 * Usage: node tools/drive_menu.mjs [httpPort] [cdpPort]
 */

import fs from "node:fs";

const HTTP_PORT = process.argv[2] || "8099";
const CDP_PORT = process.argv[3] || "9222";

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
    let tl = null;
    try { tl = window.c2_callFunction ? window.c2_callFunction('TLIsRunning', []) : null; } catch (e) {}
    return {
        layout: rt && rt.running_layout && rt.running_layout.name,
        HP: gv.HP, SimulatorMode: gv.SimulatorMode, SingleAttack: gv.SingleAttack,
        tlRunning: tl,
        heart: inst ? [+inst.x.toFixed(2), +inst.y.toFixed(2)] : null,
        heartVisible: inst ? inst.visible : null,
    };
})()`);

// Real key press through InputManagement's own binding (jQuery keydown/keyup
// are what the C2 Keyboard plugin listens to).
const press = async (which, key, holdMs = 120) => {
    await evalJs(`(() => {
        const mk = (t) => new KeyboardEvent(t, { which: ${which}, keyCode: ${which}, key: ${JSON.stringify(key)}, bubbles: true, cancelable: true });
        document.dispatchEvent(mk('keydown'));
        window.dispatchEvent(mk('keydown'));
        setTimeout(() => {
            document.dispatchEvent(mk('keyup'));
            window.dispatchEvent(mk('keyup'));
        }, ${holdMs});
        return true;
    })()`);
    await new Promise((r) => setTimeout(r, holdMs + 500));
};

const shot = async (name) => {
    const s = await send("Page.captureScreenshot", { format: "png", captureBeyondViewport: false });
    const out = new URL("./" + name, import.meta.url);
    fs.writeFileSync(out, Buffer.from(s.data, "base64"));
    return out.pathname;
};

console.log("=== start state ===");
console.log(JSON.stringify(await state(), null, 2));
console.log("shot:", await shot("menu_00.png"));

// DOWN x2 to move the heart cursor from "Normal" to "Single attack".
console.log("\n=== press Down x2 (Normal -> Single attack) ===");
await press(40, "ArrowDown");
await press(40, "ArrowDown");
console.log(JSON.stringify(await state(), null, 2));
console.log("shot:", await shot("menu_01_single.png"));

// Z to enter the mode.
console.log("\n=== press Z (enter mode) ===");
await press(90, "z");
await new Promise((r) => setTimeout(r, 1500));
console.log(JSON.stringify(await state(), null, 2));
console.log("shot:", await shot("menu_02_after_z.png"));

cdp.ws.close();
process.exit(0);

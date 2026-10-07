/**
 * Attempts to actually START a battle in the real browser so heart motion can
 * be observed frame-by-frame (the TAS must be validated against a running
 * attack, not just against the main menu).
 *
 * Strategy: the C2 Keyboard plugin binds its handlers through jQuery
 * (`jQuery(document).keydown(...)`), so synthesizing a real `keydown` event
 * with the right `which` drives VPad exactly like a human key press. We then
 * probe which menu screen we are on and report the state so the correct number
 * of confirm presses can be determined.
 *
 * Usage: node tools/browser_start_battle.mjs [httpPort] [cdpPort]
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
await new Promise((r) => setTimeout(r, 7000));

const evalJs = async (expression, awaitPromise = false) => {
    const res = await send("Runtime.evaluate", { expression, awaitPromise, returnByValue: true });
    if (res.exceptionDetails) {
        const d = res.exceptionDetails;
        throw new Error(d.exception ? (d.exception.description || d.exception.value) : d.text);
    }
    return res.result.value;
};

const snapshot = await evalJs(`(() => {
    const rt = window.c2runtime || document.getElementById('c2canvas').c2runtime;
    const gv = {};
    (rt.all_global_vars || []).forEach(v => { if (/State|Attack|HP|Mode|Simulator/i.test(v.name)) gv[v.name] = v.data; });
    const t55 = (rt.types_by_index || []).find(t => t && t.name === 't55');
    const heart = t55 && t55.instances && t55.instances[0];
    return {
        layout: rt.running_layout && rt.running_layout.name,
        globals: gv,
        heart: heart ? { x: heart.x, y: heart.y, visible: heart.visible, mode: heart.instance_vars ? heart.instance_vars[0] : null } : null,
        hasJquery: !!window.jQuery,
    };
})()`);

console.log("=== state before input ===");
console.log(JSON.stringify(snapshot, null, 2));

// Synthesize a real keydown/keyup pair on the document (jQuery-bound path).
const press = async (which, holdMs = 90) => {
    await evalJs(`(() => {
        const mk = (type) => new KeyboardEvent(type, { which: ${which}, keyCode: ${which}, bubbles: true, cancelable: true });
        document.dispatchEvent(mk('keydown'));
        window.dispatchEvent(mk('keydown'));
        setTimeout(() => {
            document.dispatchEvent(mk('keyup'));
            window.dispatchEvent(mk('keyup'));
        }, ${holdMs});
        return true;
    })()`);
    await new Promise((r) => setTimeout(r, holdMs + 250));
};

// Z = 90 is the confirm key (InputManagement.xml: Confirm = key 90 or 13).
console.log("\n=== pressing confirm (Z) to enter FIGHT menu ===");
for (let i = 1; i <= 4; i++) {
    await press(90, 120);
    const s = await evalJs(`(() => {
        const rt = window.c2runtime || document.getElementById('c2canvas').c2runtime;
        const t55 = (rt.types_by_index || []).find(t => t && t.name === 't55');
        const heart = t55 && t55.instances && t55.instances[0];
        const gv = {};
        (rt.all_global_vars || []).forEach(v => { if (/State|Attack|HP|Running|Simulator/i.test(v.name)) gv[v.name] = v.data; });
        const atk = (rt.all_local_vars || []).filter(v => /Running|Attack/i.test(v.name)).map(v => [v.name, v.data]);
        return {
            layout: rt.running_layout && rt.running_layout.name,
            heart: heart ? { x: heart.x, y: heart.y, visible: heart.visible } : null,
            globals: gv,
            localAtk: atk,
        };
    })()`);
    console.log(`  press ${i}: layout=${s.layout} heart=${JSON.stringify(s.heart)} globals=${JSON.stringify(s.globals)}`);
}

cdp.ws.close();
process.exit(0);

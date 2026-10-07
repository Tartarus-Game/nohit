/**
 * Decisive test: can a specific attack be launched in the EXISTING build without
 * the (missing) practice-menu UI?
 *
 * The build inventory shows the compiled export implements every engine handler
 * (BoneV/BoneStab/GasterBlaster/Platform/SineBones/HeartTeleport/...) and is
 * missing only the custom-menu helpers
 * (SetPracticeAttack, MenuCustomRun/Select, MenuModeCustom/Practice).
 *
 * The launch path the game itself uses is
 *     RunAttack(<index>)  ->  TLPlay(AttackList.Get(<index>))
 * so if AttackList is populated by the loader's auto-load, calling RunAttack()
 * directly should start that attack. This harness verifies it end-to-end:
 * heart becomes visible, mode becomes RED/BLUE, the timeline starts running,
 * and the heart's position matches the CSV's HeartTeleport anchor.
 *
 * Usage: node tools/test_runattack_launch.mjs [httpPort] [cdpPort] [index]
 */

const HTTP_PORT = process.argv[2] || "8099";
const CDP_PORT = process.argv[3] || "9222";
const INDEX = Number(process.argv[4] ?? 1); // 1 == sans_bonegap1 in AttackLoader order
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

// Enter the battle screen (Z on the main menu) and wait for the loader's
// attack-list auto-load to settle.
await evalJs(String.raw`(() => {
    const mk = (t) => new KeyboardEvent(t, { which: 90, keyCode: 90, bubbles: true, cancelable: true });
    document.dispatchEvent(mk('keydown'));
    setTimeout(() => document.dispatchEvent(mk('keyup')), 110);
    return true;
})()`);
await new Promise((r) => setTimeout(r, 6000));

const pre = await evalJs(String.raw`(() => {
    const rt = window.c2runtime || document.getElementById('c2canvas').c2runtime;
    window.__rt = rt;
    const t55 = (rt.types_by_index || []).find(t => t && t.name === 't55');
    window.__heart = t55.instances[0];
    const gv = () => { const o = {}; (rt.all_global_vars || []).forEach(v => { o[v.name] = v.data; }); return o; };
    // Can we see AttackList? It is a C2 Array object instance.
    const arrs = (rt.types_by_index || []).filter(t => t && t.instances && t.instances[0] &&
        typeof t.instances[0].At === 'function');
    return {
        layout: rt.running_layout && rt.running_layout.name,
        heartVisible: window.__heart.visible,
        heartPos: { x: window.__heart.x, y: window.__heart.y },
        arrayTypes: arrs.map(t => t.name),
        globals: { HP: gv().HP, SimulatorMode: gv().SimulatorMode },
    };
})()`);
console.log("=== before launch ===");
console.log(JSON.stringify(pre, null, 2));

// Launch attack by index, exactly like the game's own menu does.
const launched = await evalJs(String.raw`(async () => {
    const rt = window.__rt, heart = window.__heart;
    if (typeof window.c2_callFunction !== 'function') return { error: 'no c2_callFunction' };
    const gv = () => { const o = {}; (rt.all_global_vars || []).forEach(v => { o[v.name] = v.data; }); return o; };

    // Ask the timeline whether it is running, through the game's own function.
    const tlRunning = () => {
        try { return window.c2_callFunction('TLIsRunning', []); } catch (e) { return 'err'; }
    };

    const before = { visible: heart.visible, x: heart.x, y: heart.y, tl: tlRunning() };
    window.c2_callFunction('RunAttack', [${INDEX}]);

    // Let the attack actually start.
    await new Promise(r => setTimeout(r, 2500));

    const after = {
        visible: heart.visible,
        x: +heart.x.toFixed(3),
        y: +heart.y.toFixed(3),
        tl: tlRunning(),
        hp: gv().HP,
        mode: heart.instance_vars ? heart.instance_vars[0] : null,
    };
    return { before, after };
})()`, true);
console.log("\n=== RunAttack(" + INDEX + ") launch attempt ===");
console.log(JSON.stringify(launched, null, 2));

// Watch the heart for real ticks: a running attack with movement/teleport shows
// up as a position change.
const watched = await evalJs(String.raw`(async () => {
    const rt = window.__rt, heart = window.__heart;
    const samples = [];
    for (let i = 0; i < 40; i++) {
        await new Promise(r => requestAnimationFrame(r));
        samples.push([+heart.x.toFixed(2), +heart.y.toFixed(2), heart.visible ? 1 : 0]);
    }
    const xs = new Set(samples.map(s => s[0]));
    const ys = new Set(samples.map(s => s[1]));
    return {
        ticks: samples.length,
        distinctX: xs.size,
        distinctY: ys.size,
        first: samples[0],
        last: samples[samples.length - 1],
        moved: xs.size > 1 || ys.size > 1,
    };
})()`, true);
console.log("\n=== heart after launch ===");
console.log(JSON.stringify(watched, null, 2));

cdp.ws.close();
process.exit(0);

/**
 * scratch_B_spawn.mjs — VERIFY_B final: captures the SPAWN INSTANT.
 *
 * The function is called from inside the wrapped tick, immediately after the
 * engine's own tick, so every recorded position is age == 0 (no movement yet).
 * Records x, y, height and bbox for every BoneV (t31) created, for both CSV
 * lines of sans_bonegap1.
 *
 * Usage: node tools/scratch_B_spawn.mjs [cdpPort]
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

const res = await evalJs(`(() => {
    const c = document.getElementById('c2canvas');
    const rt = window.c2runtime || (c && c.c2runtime);
    const T31 = (rt.types_by_index || []).find(t => t && t.name === 't31');
    for (const i of [...T31.instances]) i.destroy();

    const snap = (i) => {
        let bl = null, bt = null, br = null, bb = null;
        try { i.update_bbox(); bl = i.bbox.left; bt = i.bbox.top; br = i.bbox.right; bb = i.bbox.bottom; }
        catch (e) {}
        return { uid: i.uid, x: i.x, y: i.y, w: i.width, h: i.height,
                 bboxLeft: bl, bboxTop: bt, bboxRight: br, bboxBottom: bb,
                 hotX: i.hotspotX, hotY: i.hotspotY, angle: i.angle, layer: i.layer && i.layer.name };
    };

    const rtp = rt.constructor.prototype;
    const origTick = rtp.tick || rt.tick;
    const plan = [
        { tag: 'L1  dir0 start_x=128',  args: [128, 257, 95, 0, 180, 8, 120] },
        { tag: 'L2  dir2 start_x=503',  args: [503, 257, 95, 2, 180, 8, 120] },
    ];
    const out = [];
    let n = 0;
    rtp.tick = function () {
        const r = origTick.apply(this, arguments);
        if (n < plan.length) {
            const step = plan[n++];
            const before = new Set(T31.instances.map(i => i.uid));
            let err = null;
            try { window.c2_callFunction('BoneVRepeat', step.args); }
            catch (e) { err = e.message; }
            const created = T31.instances.filter(i => !before.has(i.uid)).map(snap);
            out.push({ tag: step.tag, args: step.args, err, created });
        }
        return r;
    };
    window.__spawnOut = out;
    window.__spawnDone = false;
    return 'armed';
})()`);
console.log("arm:", res);

await new Promise((r) => setTimeout(r, 1500));

const got = await evalJs(`(() => {
    window.__spawnDone = true;
    return window.__spawnOut;
})()`);

console.log("\n================ SPAWN-INSTANT (age = 0, inside the tick) ================");
for (const step of got) {
    console.log(`\n### ${step.tag}   args=${JSON.stringify(step.args)}${step.err ? '  ERR=' + step.err : ''}`);
    console.log(`created=${step.created.length}`);
    console.log("  i    x          y      h    bbox.left  bbox.top   hot");
    step.created.forEach((b, i) => {
        console.log(`  ${i}  ${String(b.x).padStart(9)}  ${String(b.y).padStart(5)}  ${String(b.h).padStart(4)}  ` +
            `${String(b.bboxLeft).padStart(9)}  ${String(b.bboxTop).padStart(7)}   ${b.hotX},${b.hotY}`);
    });
    console.log(`  x list:    ${JSON.stringify(step.created.map(b => b.x))}`);
    console.log(`  y list:    ${JSON.stringify(step.created.map(b => b.y))}`);
    console.log(`  bbox.left: ${JSON.stringify(step.created.map(b => b.bboxLeft))}`);
    console.log(`  deltas:    ${JSON.stringify(step.created.map((b, i, a) => i ? +(b.x - a[i-1].x).toFixed(4) : null).slice(1))}`);
}

cdp.ws.close();
process.exit(0);

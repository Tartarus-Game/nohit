/**
 * scratch_B_direct.mjs — VERIFY_B decisive test.
 *
 * Calls the game's own BoneVRepeat function with the EXACT CSV arguments and
 * records every BoneV (t31) instance created, with its x/y/height and bbox.
 *
 * This isolates the spawn loop from the timeline/CSV plumbing, so the result is
 * a direct read of the engine's own expansion of
 *     X = StartX - cos(Direction*90)*Spacing*loopindex
 *
 * Usage: node tools/scratch_B_direct.mjs [cdpPort]
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

const result = await evalJs(`(() => {
    const c = document.getElementById('c2canvas');
    const rt = window.c2runtime || (c && c.c2runtime);
    const T31 = (rt.types_by_index || []).find(t => t && t.name === 't31');
    if (!T31) return { err: 'no t31' };

    const snap = (inst) => {
        let bl = null, bt = null;
        try { inst.update_bbox(); bl = inst.bbox.left; bt = inst.bbox.top; }
        catch (e) { bl = 'ERR'; }
        return { uid: inst.uid, x: inst.x, y: inst.y, w: inst.width, h: inst.height,
                 bboxLeft: bl, bboxTop: bt, hotX: inst.hotspotX, hotY: inst.hotspotY,
                 layer: inst.layer && inst.layer.name, visible: inst.visible, depth: inst.depth };
    };

    // wipe any existing bones so the diff is clean
    const before = T31.instances.map(i => i.uid);
    const beforeSet = new Set(before);

    // --- THE CALL: exact args of the CSV line 0.2,BoneVRepeat,128,257,95,0,180,8,120
    let callErr = null;
    try {
        window.c2_callFunction('BoneVRepeat', [128, 257, 95, 0, 180, 8, 120]);
    } catch (e) { callErr = e.message; }

    const after = T31.instances.map(i => i.uid);
    const created = T31.instances.filter(i => !beforeSet.has(i.uid)).map(snap);

    return {
        callErr,
        beforeCount: before.length,
        afterCount: after.length,
        createdCount: created.length,
        created,
        allNow: T31.instances.map(snap),
        nInstances: T31.instances.length,
    };
})()`);

console.log("=== direct BoneVRepeat(128, 257, 95, 0, 180, 8, 120) ===");
console.log("callErr:", result.callErr);
console.log(`t31 count before=${result.beforeCount} after=${result.afterCount} created=${result.createdCount}`);
console.log("\n--- CREATED instances ---");
for (const b of result.created) {
    console.log(`uid=${String(b.uid).padStart(4)} x=${String(b.x).padStart(9)} y=${String(b.y).padStart(5)} ` +
        `h=${String(b.h).padStart(4)} bbox.left=${String(b.bboxLeft).padStart(9)} bbox.top=${String(b.bboxTop).padStart(5)} ` +
        `hot=${b.hotX},${b.hotY} layer=${b.layer} depth=${b.depth}`);
}
console.log("\n--- ALL t31 now ---");
for (const b of result.allNow) {
    console.log(`uid=${String(b.uid).padStart(4)} x=${String(b.x).padStart(9)} y=${String(b.y).padStart(5)} h=${String(b.h).padStart(4)}`);
}

// --- second call: the direction-2 line ---------------------------------------
const result2 = await evalJs(`(() => {
    const c = document.getElementById('c2canvas');
    const rt = window.c2runtime || (c && c.c2runtime);
    const T31 = (rt.types_by_index || []).find(t => t && t.name === 't31');
    const beforeSet = new Set(T31.instances.map(i => i.uid));
    let callErr = null;
    try { window.c2_callFunction('BoneVRepeat', [503, 257, 95, 2, 180, 8, 120]); }
    catch (e) { callErr = e.message; }
    const created = T31.instances.filter(i => !beforeSet.has(i.uid)).map(i => {
        let bl = null; try { i.update_bbox(); bl = i.bbox.left; } catch (e) {}
        return { uid: i.uid, x: i.x, y: i.y, h: i.height, bboxLeft: bl };
    });
    return { callErr, created };
})()`);
console.log("\n=== direct BoneVRepeat(503, 257, 95, 2, 180, 8, 120) ===");
console.log("callErr:", result2.callErr, " created:", result2.created.length);
for (const b of result2.created) {
    console.log(`uid=${String(b.uid).padStart(4)} x=${String(b.x).padStart(9)} y=${String(b.y).padStart(5)} ` +
        `h=${String(b.h).padStart(4)} bbox.left=${String(b.bboxLeft).padStart(9)}`);
}

cdp.ws.close();
process.exit(0);

/**
 * scratch_B_live2.mjs — VERIFY_B live probe (v2, starts the attack properly).
 *
 * Round start sequence (from repo_badtime event sheets + tools/prove_timeline_gate.mjs):
 *   ?mode=single&attack=<wave>  ->  StartAttack  ->  RunAttack(1)  ->  timeline
 *   dispatches CSV lines; CombatZoneResize(...,"TLResume") sets Running=1.
 *
 * Records every BoneV (runtime type t31) creation with its x/y/height AND bbox,
 * plus the layer transform so canvas-space conversion is explicit.
 *
 * Usage: node tools/scratch_B_live2.mjs [httpPort] [cdpPort] [wave] [seconds]
 */

import fs from "node:fs";

const HTTP_PORT = process.argv[2] || "8099";
const CDP_PORT = process.argv[3] || "9444";
const WAVE = process.argv[4] || "sans_bonegap1";
const SECONDS = Number(process.argv[5] || 5);
const URL_GAME = `http://127.0.0.1:${HTTP_PORT}/game/index.html?mode=single&attack=${WAVE}`;

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
            setTimeout(() => { if (this.pending.delete(id)) rej(new Error("timeout " + method)); }, 120000);
        });
    }
}

const targets = await fetch(`http://127.0.0.1:${CDP_PORT}/json/list`).then((r) => r.json());
const page = targets.find((t) => t.type === "page" && !/chrome-extension/.test(t.url || ""));
if (!page) { console.error("no page target"); process.exit(1); }
const cdp = new CDP(page.webSocketDebuggerUrl);
await cdp.ready;
const { sessionId } = await cdp.send("Target.attachToTarget", { targetId: page.id, flatten: true });
const send = (m, p) => cdp.send(m, p, sessionId);
await send("Page.enable");
await send("Runtime.enable");

const evalJs = async (expression) => {
    const res = await send("Runtime.evaluate", { expression, returnByValue: true, awaitPromise: true });
    if (res.exceptionDetails) {
        const d = res.exceptionDetails;
        throw new Error(d.exception ? (d.exception.description || d.exception.value) : d.text);
    }
    return res.result.value;
};

console.log(`=== navigating: ${URL_GAME} ===`);
await send("Page.navigate", { url: URL_GAME });
await new Promise((r) => setTimeout(r, 12000));

// --- install the recorder BEFORE the attack starts ---------------------------
const installed = await evalJs(`(() => {
    const c = document.getElementById('c2canvas');
    const rt = window.c2runtime || (c && c.c2runtime);
    if (!rt) return 'no runtime';
    const proto = rt.constructor.prototype;
    const orig = proto.tick || rt.tick;
    if (typeof orig !== 'function') return 'no tick fn';

    const T31 = (rt.types_by_index || []).find(t => t && t.name === 't31');
    const T30 = (rt.types_by_index || []).find(t => t && t.name === 't30');
    if (!T31) return 'no t31 type';

    const rec = [];
    window.__vbRec = rec;
    window.__vbTick = 0;
    window.__vbErr = null;
    const seen = new Map();   // uid -> first snapshot
    const births = [];        // {tick, uid, x, y, ...}

    const snap = (inst) => {
        let b = null;
        try { inst.update_bbox(); b = { l: inst.bbox.left, t: inst.bbox.top, r: inst.bbox.right, bo: inst.bbox.bottom }; }
        catch (e) { b = 'ERR:' + e.message; }
        return { uid: inst.uid, x: inst.x, y: inst.y, w: inst.width, h: inst.height,
                 bbox: b, hotX: inst.hotspotX, hotY: inst.hotspotY,
                 layer: inst.layer && inst.layer.name, visible: inst.visible, depth: inst.depth };
    };

    const collect = (type, tag) => {
        for (const inst of type.instances) {
            if (!seen.has(inst.uid)) {
                const s = snap(inst);
                seen.set(inst.uid, s);
                births.push({ tick: window.__vbTick, type: tag, ...s });
            }
        }
    };

    const hooked = function () {
        window.__vbTick++;
        const r = orig.apply(this, arguments);
        try { collect(T31, 't31'); if (T30) collect(T30, 't30'); }
        catch (e) { window.__vbErr = e.message; }
        return r;
    };
    proto.tick = hooked;
    rt.__vbHooked = true;
    window.__vbBirths = births;
    window.__vbSeen = seen;
    return 'installed';
})()`);
console.log("hook:", installed);
if (installed !== "installed") { cdp.ws.close(); process.exit(1); }

// --- start the round the way the game does ----------------------------------
const started = await evalJs(`(() => {
    const out = {};
    const gv = () => { const o = {}; const c = document.getElementById('c2canvas');
        const rt = window.c2runtime || (c && c.c2runtime);
        (rt.all_global_vars || []).forEach(v => { o[v.name] = v.data; }); return o; };
    out.before = { HP: gv().HP, mode: gv().SimulatorMode, atk: gv().SingleAttack };
    try { window.c2_callFunction('StartAttack', []); out.startAttack = 'ok'; }
    catch (e) { out.startAttack = 'ERR ' + e.message; }
    try { window.c2_callFunction('RunAttack', [1]); out.runAttack = 'ok'; }
    catch (e) { out.runAttack = 'ERR ' + e.message; }
    return out;
})()`);
console.log("start:", JSON.stringify(started));

// let it run
await new Promise((r) => setTimeout(r, Math.ceil(SECONDS * 1000)));

const out = await evalJs(`(() => {
    const c = document.getElementById('c2canvas');
    const rt = window.c2runtime || (c && c.c2runtime);
    const gv = {}; (rt.all_global_vars || []).forEach(v => { gv[v.name] = v.data; });
    let tl = null; try { tl = window.c2_callFunction('TLIsRunning', []); } catch (e) { tl = 'ERR'; }
    let layerXf = null;
    try {
        const L = (rt.running_layout.layers || []).find(l => l.name === 'CombatZoneClipped');
        layerXf = L ? { scrollX: L.scrollX, scrollY: L.scrollY, scale: L.scale, x: L.x, y: L.y,
                        parallaxX: L.parallaxX, parallaxY: L.parallaxY, zoomRate: L.zoomRate } : null;
    } catch (e) { layerXf = 'ERR ' + e.message; }
    let live = [];
    try {
        const T = (rt.types_by_index || []).find(t => t && t.name === 't31');
        if (T) live = T.instances.map(i => ({ uid: i.uid, x: i.x, y: i.y, h: i.height,
            bboxLeft: (i.update_bbox(), i.bbox.left), layer: i.layer && i.layer.name }));
    } catch (e) { live = ['ERR ' + e.message]; }
    return { tick: window.__vbTick, vberr: window.__vbErr, births: window.__vbBirths || [],
             live, tlRunning: tl, HP: gv.HP, mode: gv.SimulatorMode, layerXf,
             layoutScale: rt.running_layout.scale };
})()`);

console.log(`\n=== ticks: ${out.tick}  vberr: ${out.vberr} ===`);
console.log(`=== tlRunning: ${out.tlRunning}  HP: ${out.HP} ===`);
console.log(`=== layer CombatZoneClipped: ${JSON.stringify(out.layerXf)}  layoutScale=${out.layoutScale} ===`);
const b31 = out.births.filter(b => b.type === "t31");
const b30 = out.births.filter(b => b.type === "t30");
console.log(`\n=== t31 BIRTHS: ${b31.length}   t30 BIRTHS: ${b30.length} ===`);

console.log("\n--- t31 births grouped by tick (this is the SPAWN INSTANT) ---");
const byTick = new Map();
for (const b of b31) {
    if (!byTick.has(b.tick)) byTick.set(b.tick, []);
    byTick.get(b.tick).push(b);
}
for (const [t, arr] of byTick) {
    const xs = arr.map(b => b.x);
    const hs = [...new Set(arr.map(b => b.h))];
    console.log(`  tick ${String(t).padStart(3)}: n=${arr.length} h=${JSON.stringify(hs)} ` +
        `x=${JSON.stringify(xs)}`);
    console.log(`            sorted x: ${JSON.stringify([...xs].sort((a, b) => a - b))}`);
    console.log(`            bbox.left: ${JSON.stringify(arr.map(b => b.bbox && b.bbox.l))}`);
    console.log(`            hotspot:   ${JSON.stringify([...new Set(arr.map(b => b.hotX + ',' + b.hotY))])}`);
}

console.log("\n--- first 24 t31 birth records (raw) ---");
for (const b of b31.slice(0, 24)) {
    console.log(`tick=${String(b.tick).padStart(3)} uid=${String(b.uid).padStart(4)} ` +
        `x=${String(b.x).padStart(9)} y=${String(b.y).padStart(5)} h=${String(b.h).padStart(4)} ` +
        `bbox.l=${String(b.bbox && b.bbox.l).padStart(9)} hot=${b.hotX},${b.hotY} layer=${b.layer}`);
}

console.log("\n--- live t31 at end ---");
console.log(JSON.stringify(out.live, null, 1));

fs.writeFileSync(new URL("./scratch_B_live2_out.json", import.meta.url), JSON.stringify(out, null, 1));
console.log("\nwrote tools/scratch_B_live2_out.json");
cdp.ws.close();
process.exit(0);

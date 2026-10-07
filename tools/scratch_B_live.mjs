/**
 * scratch_B_live.mjs — VERIFY_B live probe.
 *
 * Answers empirically: at the INSTANT a BoneV (runtime type "t31") is created,
 * what is its transform x, and what does its bbox look like?
 *
 * Method: wrap the Construct 2 runtime tick, diff the t31 instance list each
 * tick, and record every newly-created instance with its x/y/width/height and
 * bbox. Also reports layer transform so canvas-space conversion is explicit.
 *
 * Usage: node tools/scratch_B_live.mjs [httpPort] [cdpPort] [wave] [ticks]
 */

import fs from "node:fs";

const HTTP_PORT = process.argv[2] || "8099";
const CDP_PORT = process.argv[3] || "9444";
const WAVE = process.argv[4] || "sans_bonegap1";
const TICKS = Number(process.argv[5] || 220);
const URL_GAME = `http://127.0.0.1:${HTTP_PORT}/game/index.html?mode=single&attack=${WAVE}`;

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
if (!page) { console.error("no page target", JSON.stringify(targets)); process.exit(1); }
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

console.log(`=== navigating: ${URL_GAME} ===`);
await send("Page.navigate", { url: URL_GAME });
await new Promise((r) => setTimeout(r, 12000));

// --- locate runtime + confirm the type-name -> plugin mapping -----------------
const info = await evalJs(`(() => {
    const c = document.getElementById('c2canvas');
    const rt = window.c2runtime || (c && c.c2runtime);
    if (!rt) return { err: 'no runtime' };
    const out = { names: {}, plugins: {} };
    (rt.types_by_index || []).forEach((t, i) => {
        if (!t) return;
        out.names[t.name] = i;
        if (t.name === 't31' || t.name === 't30') {
            out.plugins[t.name] = { plugin: t.plugin && t.plugin.constructor &&
                (t.plugin.constructor.name || String(t.plugin.constructor).slice(0,60)),
                is_world: t.plugin && t.plugin.is_world,
                texture: t.texture_file || (t.plugin && t.plugin.texture_file) || null,
                insts: t.instances ? t.instances.length : -1 };
        }
    });
    const gv = {}; (rt.all_global_vars || []).forEach(v => { gv[v.name] = v.data; });
    const layers = {};
    (rt.running_layout ? rt.running_layout.layers : []).forEach(l => {
        layers[l.name] = { scrollX: l.scrollX, scrollY: l.scrollY, scale: l.scale,
                           parallaxX: l.parallaxX, parallaxY: l.parallaxY,
                           x: l.x, y: l.y, angle: l.angle };
    });
    return { names: out.names, plugins: out.plugins, gv: { HP: gv.HP, SingleAttack: gv.SingleAttack,
             SimulatorMode: gv.SimulatorMode }, layers, layout: rt.running_layout && rt.running_layout.name,
             layoutW: rt.running_layout && rt.running_layout.width,
             layoutH: rt.running_layout && rt.running_layout.height };
})()`);
console.log("=== runtime info ===");
console.log(JSON.stringify(info, null, 1));

if (info.gv && info.gv.HP <= 0) {
    console.log("\n=== firing StartAttack ===");
    await evalJs(`(() => { window.c2_callFunction('StartAttack', []); return true; })()`);
    await new Promise((r) => setTimeout(r, 2500));
}

// --- install the tick hook ---------------------------------------------------
console.log(`\n=== installing tick hook, recording ${TICKS} ticks ===`);
const installed = await evalJs(`(() => {
    const c = document.getElementById('c2canvas');
    const rt = window.c2runtime || (c && c.c2runtime);
    if (!rt) return 'no runtime';
    if (rt.__vbHooked) return 'already';
    const proto = rt.constructor.prototype;
    const orig = proto.tick || rt.tick;
    if (typeof orig !== 'function') return 'no tick fn on ' + proto.constructor.name;

    const T31 = (rt.types_by_index || []).find(t => t && t.name === 't31');
    const T30 = (rt.types_by_index || []).find(t => t && t.name === 't30');
    if (!T31) return 'no t31 type';

    const rec = [];
    window.__vbRec = rec;
    window.__vbTick = 0;
    let prev31 = new Set(T31.instances.map(i => i.uid));
    let prev30 = T30 ? new Set(T30.instances.map(i => i.uid)) : new Set();
    let prevLayout = null;

    const snap = (inst) => {
        let bx = null, by = null, bxx = null, byy = null;
        try {
            if (!inst.bbox_changed) { /* up to date */ }
            inst.update_bbox && inst.update_bbox();
            bx = inst.bbox.left; by = inst.bbox.top;
            bxx = inst.bbox.right; byy = inst.bbox.bottom;
        } catch (e) { bx = 'ERR:' + e.message; }
        return { uid: inst.uid, x: inst.x, y: inst.y, w: inst.width, h: inst.height,
                 bboxLeft: bx, bboxTop: by, bboxRight: bxx, bboxBottom: byy,
                 hotspotX: inst.hotspotX, hotspotY: inst.hotspotY,
                 layer: inst.layer && inst.layer.name, visible: inst.visible,
                 depth: inst.depth };
    };

    const hooked = function () {
        const layoutName = rt.running_layout && rt.running_layout.name;
        if (layoutName !== prevLayout) { prevLayout = layoutName; }
        const t = ++window.__vbTick;
        const r = orig.apply(this, arguments);
        // after the tick: find newly created instances and record their state
        const cur31 = T31.instances;
        const s31 = new Set();
        for (const inst of cur31) {
            s31.add(inst.uid);
            if (!prev31.has(inst.uid)) rec.push({ tick: t, type: 't31', ...snap(inst) });
        }
        prev31 = s31;
        if (T30) {
            const s30 = new Set();
            for (const inst of T30.instances) {
                s30.add(inst.uid);
                if (!prev30.has(inst.uid)) rec.push({ tick: t, type: 't30', ...snap(inst) });
            }
            prev30 = s30;
        }
        return r;
    };
    proto.tick = hooked;
    rt.__vbHooked = true;
    return 'installed';
})()`);
console.log("hook:", installed);

// let it run
await new Promise((r) => setTimeout(r, Math.ceil((TICKS / 60) * 1000) + 2500));

const out = await evalJs(`(() => {
    const c = document.getElementById('c2canvas');
    const rt = window.c2runtime || (c && c.c2runtime);
    let live31 = [];
    try {
        const T = rt && (rt.types_by_index || []).find(t => t && t.name === 't31');
        if (T) live31 = T.instances.map(i => ({ uid: i.uid, x: i.x, y: i.y, h: i.height,
            bboxLeft: (i.update_bbox && i.update_bbox(), i.bbox.left) }));
    } catch (e) { live31 = ['ERR ' + e.message]; }
    return { tick: window.__vbTick, rec: window.__vbRec || [], live31 };
})()`);

console.log(`\n=== engine ticks observed: ${out.tick} ===`);
console.log(`=== t31 spawn events: ${out.rec.filter(r=>r.type==='t31').length} ===`);
console.log("\n--- first 40 t31 spawn events ---");
for (const r of out.rec.filter(r => r.type === 't31').slice(0, 40)) {
    console.log(`tick=${String(r.tick).padStart(3)} uid=${String(r.uid).padStart(4)} ` +
        `x=${String(r.x).padStart(9)} y=${String(r.y).padStart(6)} h=${String(r.h).padStart(4)} ` +
        `bbox.left=${String(r.bboxLeft).padStart(9)} bbox.top=${String(r.bboxTop).padStart(6)} ` +
        `hot=${r.hotspotX},${r.hotspotY} layer=${r.layer}`);
}
console.log("\n--- spawn events grouped by tick ---");
const byTick = {};
for (const r of out.rec.filter(r => r.type === 't31')) (byTick[r.tick] ||= []).push(r.x);
for (const [t, xs] of Object.entries(byTick)) console.log(`  tick ${t}: n=${xs.length} xs=${JSON.stringify(xs)}`);

console.log("\n--- t30 (BoneH) spawn events grouped by tick ---");
const byTick30 = {};
for (const r of out.rec.filter(r => r.type === 't30')) (byTick30[r.tick] ||= []).push(r.x);
for (const [t, xs] of Object.entries(byTick30)) console.log(`  tick ${t}: n=${xs.length} xs=${JSON.stringify(xs)}`);

console.log("\n--- live t31 snapshot at end ---");
console.log(JSON.stringify(out.live31, null, 1));

fs.writeFileSync(new URL("./scratch_B_live_out.json", import.meta.url),
    JSON.stringify({ info, out }, null, 1));
console.log("\nwrote tools/scratch_B_live_out.json");
cdp.ws.close();
process.exit(0);

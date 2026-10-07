/**
 * GROUND TRUTH probe (single run, no local tests).
 *
 * Loads the real game from the dashboard server, lets the in-game TASRunner
 * auto-fetch the solver plan and auto-start playback (the runner hooks
 * Runtime.prototype.tick itself), then records, for EVERY engine tick:
 *
 *   - heart abs x/y, HP, LastDamageTime
 *   - the plan frame the controller is currently driving
 *   - the exact bounding box of every Attack9Patch-family instance (the damage
 *     primitive per Battle.xml) and of the PlayerHitbox
 *   - the engine's OWN verdicts: rt.testOverlap(hitbox, bone) and
 *     bone.contains_pt(heart.x, heart.y)   <-- the "Pick overlapping point" test
 *
 * The output lets us diff the solver's baked hazard geometry against the live
 * engine at the exact frame where the plan believes it is safe.
 *
 * Usage: node tools/probe_ground_truth.mjs [ticks] [outfile]
 */

import fs from "node:fs";

const HTTP_PORT = "8099";
// ego-browser publishes its CDP port in %LOCALAPPDATA%\ego-lite-linux\browser.json
function egoCdpPort() {
    for (const p of [
        `${process.env.LOCALAPPDATA}\\ego-lite-linux\\browser.json`,
        `${process.env.LOCALAPPDATA}\\ego-lite\\browser.json`,
    ]) {
        try { const j = JSON.parse(fs.readFileSync(p, "utf8")); if (j.port) return String(j.port); } catch {}
    }
    return "9222";
}
const CDP_PORT = process.env.TAS_CDP_PORT || egoCdpPort();
const TICKS = Number(process.argv[2] || 3000);
const OUTFILE = process.argv[3] || "tools/.groundtruth_probe.json";
const WAVE = process.env.TAS_WAVE || "sans_bonegap1";

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
            setTimeout(() => { if (this.pending.delete(id)) rej(new Error("timeout " + method)); }, 180000);
        });
    }
}

const targets = await fetch(`http://127.0.0.1:${CDP_PORT}/json/list`).then((r) => r.json());
const page = targets.find((t) => t.type === "page" && /127\.0\.0\.1:8099\/game/.test(t.url || ""))
    || targets.find((t) => t.type === "page" && !/chrome-extension/.test(t.url || ""));
if (!page) { console.error("no page target; targets=", targets.map(t => t.url)); process.exit(3); }
console.log("target:", page.url);

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

const st = (s) => s.replace(/\\/g, "\\\\").replace(/'/g, "\\'").replace(/\n/g, "\\n");

// ---------------------------------------------------------------- navigate
const URL_GAME = `http://127.0.0.1:${HTTP_PORT}/game/index.html?mode=single&attack=${WAVE}&cb=gt${Date.now()}`;
console.log("=== navigate:", URL_GAME);
await send("Page.navigate", { url: URL_GAME });
await new Promise((r) => setTimeout(r, 8000));

console.log("=== waiting for TASRunner plan + auto-start (up to 180 s)");
const waitRes = await evalJs(`(async () => {
  const t0 = Date.now();
  let last = null;
  while (Date.now() - t0 < 180000) {
    const s = window.TASRunner ? window.TASRunner.getState() : null;
    last = s;
    if (s && s.actionCount > 100) return { ok: true, state: s, ms: Date.now() - t0 };
    await new Promise(r => setTimeout(r, 500));
  }
  return { ok: false, state: last, ms: Date.now() - t0 };
})()`, true);
console.log("plan:", JSON.stringify(waitRes).slice(0, 800));
if (!waitRes.ok) { console.error("plan never loaded"); cdp.ws.close(); process.exit(4); }

// ------------------------------------------------- arm a pure tracer
// We do NOT touch the runner's key injection: it is already driving playback.
// We only wrap tick() a second time to sample state after the engine ran.
console.log("=== installing tracer (post-tick sampler)");
await evalJs(`(() => {
  const rt = window.c2runtime || document.getElementById('c2canvas').c2runtime;
  const proto = rt.constructor.prototype;
  if (!proto.__gtWrapped) {
    const orig = proto.tick;
    window.__GT = { rows: [], limit: ${TICKS}, fps: 0, stopped: false };
    proto.tick = function () {
      const r = orig.apply(this, arguments);
      const G = window.__GT;
      if (G.rows.length < G.limit) {
        try {
          const types = rt.types_by_index || [];
          const byName = {};
          for (const t of types) if (t && t.instances) byName[t.name] = t;
          const heart = (byName['t55'] || {}).instances ? byName['t55'].instances[0] : null;
          const hb = (byName['t65'] || {}).instances ? byName['t65'].instances[0] : null;
          const gv = {}; (rt.all_global_vars || []).forEach(v => gv[v.name] = v.data);
          const s = window.TASRunner ? window.TASRunner.getState() : null;
          // Attack9Patch family members
          const names = ['t30','t31','t36','t37','t38','t43','t60','t61','t62','t63','t64','t66','t67','t70','t71','t72','t73'];
          const bones = [];
          for (const n of names) {
            const t = byName[n];
            if (!t || !t.instances) continue;
            for (const inst of t.instances) {
              if (!inst.visible) continue;
              inst.update_bbox();
              bones.push([n, +inst.x.toFixed(2), +inst.y.toFixed(2),
                          +inst.bbox.left.toFixed(2), +inst.bbox.top.toFixed(2),
                          +inst.bbox.right.toFixed(2), +inst.bbox.bottom.toFixed(2),
                          +inst.width.toFixed(2), +inst.height.toFixed(2), inst.iid]);
            }
          }
          let hbx = null, hbb = null;
          if (hb) { hb.update_bbox(); hbx = [+hb.x.toFixed(2), +hb.y.toFixed(2), +hb.width.toFixed(2), +hb.height.toFixed(2)];
                    hbb = [+hb.bbox.left.toFixed(2), +hb.bbox.top.toFixed(2), +hb.bbox.right.toFixed(2), +hb.bbox.bottom.toFixed(2)]; }
          // engine verdicts for the FLOOR-LEVEL bones only (keep the row small)
          const verdicts = [];
          if (heart && hb) {
            for (const b of bones) {
              if (b[3] > heart.y - 12 && b[5] < heart.x + 200 && b[6] > heart.x - 200) continue; // cheap prefilter kept
            }
            for (const b of bones) {
              if (Math.abs(b[1] - heart.x) > 200) continue;
              const t = byName[b[0]];
              let inst = null;
              for (const cand of t.instances) if (cand.iid === b[9]) { inst = cand; break; }
              if (!inst) continue;
              inst.update_bbox();
              const pt = inst.contains_pt(heart.x, heart.y);
              const ov = rt.testOverlap(hb, inst);
              if (pt || ov) verdicts.push([b[0], b[9], pt ? 1 : 0, ov ? 1 : 0,
                                           inst.bbox.left, inst.bbox.top, inst.bbox.right, inst.bbox.bottom]);
            }
          }
          G.rows.push({
            hx: heart ? +heart.x.toFixed(3) : null,
            hy: heart ? +heart.y.toFixed(3) : null,
            hp: gv.HP, ldt: gv.LastDamageTime, vis: heart ? (heart.visible ? 1 : 0) : null,
            f: s ? s.plannedFrame : null, cur: s ? s.currentFrame : null,
            playing: s ? (s.isPlaying ? 1 : 0) : null,
            drift: s ? s.drift : null,
            hb: hbx, hbb, nbones: bones.length,
            bones: G.rows.length % 4 === 0 ? bones : null,
            verdicts: verdicts.length ? verdicts : null,
            fps: rt.fps,
          });
        } catch (e) { G.err = String(e && e.stack || e); }
      }
      return r;
    };
    proto.__gtWrapped = true;
  }
  return { installed: true, limit: ${TICKS} };
})()`);

console.log(`=== recording ${TICKS} ticks`);
const rec = await evalJs(`(async () => {
  const G = window.__GT;
  const t0 = Date.now();
  while (Date.now() - t0 < 240000) {
    if (G.rows.length >= G.limit) break;
    const s = window.TASRunner ? window.TASRunner.getState() : null;
    if (s && s.actionCount > 0 && !s.isPlaying && G.rows.length > 50) break; // plan exhausted
    await new Promise(r => setTimeout(r, 500));
  }
  const s = window.TASRunner ? window.TASRunner.getState() : null;
  const hp0 = G.rows.length ? G.rows[0].hp : null;
  const hpLast = G.rows.length ? G.rows[G.rows.length - 1].hp : null;
  const dmg = [];
  for (let i = 1; i < G.rows.length; i++) if (G.rows[i].hp < G.rows[i-1].hp) dmg.push([i, G.rows[i-1].hp, G.rows[i].hp]);
  return { n: G.rows.length, err: G.err || null, state: s, hp0, hpLast, dmgCount: dmg.length, dmg: dmg.slice(0, 80), fps: G.rows.length ? G.rows[0].fps : null };
})()`, true);
console.log("record:", JSON.stringify(rec).slice(0, 3000));

const dump = await evalJs(`JSON.stringify({ rows: window.__GT.rows, err: window.__GT.err || null })`);
fs.writeFileSync(new URL("../" + OUTFILE.replace(/^tools\//, "tools/"), import.meta.url), dump, "utf8");
console.log("wrote", OUTFILE, dump.length, "bytes");
cdp.ws.close();
process.exit(0);

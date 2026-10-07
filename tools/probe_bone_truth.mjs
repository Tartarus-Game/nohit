/**
 * PROBE v4 — records the ENGINE's own collision verdicts together with the raw
 * bone boxes, so "model says safe / engine damages" can be pinned to geometry.
 *
 * Damage carriers are found through the runtime's family instance-variable
 * mapping (`inst.type.family_var_map[family_index] + offset`), because the
 * member types have no instance_vars of their own (probe v1/v2 got 0 carriers
 * and silently measured nothing).
 *
 * Recording starts at the round boundary (the first tick where the runner
 * reports `isPlaying` with `plannedFrame` small) so the attack's own restart
 * cycle cannot hide the beginning of the round.
 *
 * Usage: node tools/probe_bone_truth.mjs [ticks] [outfile]
 */
import fs from "node:fs";

const HTTP_PORT = "8099";
function egoCdpPort() {
    for (const p of [`${process.env.LOCALAPPDATA}\\ego-lite-linux\\browser.json`,
                     `${process.env.LOCALAPPDATA}\\ego-lite\\browser.json`]) {
        try { const j = JSON.parse(fs.readFileSync(p, "utf8")); if (j.port) return String(j.port); } catch {}
    }
    return "9222";
}
const CDP_PORT = process.env.TAS_CDP_PORT || egoCdpPort();
const TICKS = Number(process.argv[2] || 900);
const OUTFILE = process.argv[3] || "tools/.bone_truth.json";
const WAVE = process.env.TAS_WAVE || "sans_bonegap1";

class CDP {
    constructor(u) {
        this.ws = new WebSocket(u); this.id = 0; this.pending = new Map();
        this.ready = new Promise((res, rej) => { this.ws.addEventListener("open", () => res()); this.ws.addEventListener("error", (e) => rej(new Error("ws " + (e.message || e.type)))); });
        this.ws.addEventListener("message", (ev) => { const m = JSON.parse(ev.data); if (m.id !== undefined && this.pending.has(m.id)) { const { resolve, reject } = this.pending.get(m.id); this.pending.delete(m.id); m.error ? reject(new Error(JSON.stringify(m.error))) : resolve(m.result); } });
    }
    send(method, params = {}, sessionId) {
        const id = ++this.id; const p = { id, method, params }; if (sessionId) p.sessionId = sessionId;
        this.ws.send(JSON.stringify(p));
        return new Promise((res, rej) => { this.pending.set(id, { resolve: res, reject: rej }); setTimeout(() => { if (this.pending.delete(id)) rej(new Error("timeout " + method)); }, 180000); });
    }
}
const targets = await fetch(`http://127.0.0.1:${CDP_PORT}/json/list`).then(r => r.json());
const page = targets.find(t => t.type === "page" && /127\.0\.0\.1:8099\/game/.test(t.url || "")) || targets.find(t => t.type === "page" && !/chrome-extension/.test(t.url || ""));
if (!page) { console.error("no page"); process.exit(3); }
const cdp = new CDP(page.webSocketDebuggerUrl);
await cdp.ready;
const { sessionId } = await cdp.send("Target.attachToTarget", { targetId: page.id, flatten: true });
const send = (m, p) => cdp.send(m, p, sessionId);
await send("Page.enable"); await send("Runtime.enable");
const evalJs = async (e, aw = false) => {
    const r = await send("Runtime.evaluate", { expression: e, awaitPromise: aw, returnByValue: true });
    if (r.exceptionDetails) throw new Error(r.exceptionDetails.exception?.description || r.exceptionDetails.text);
    return r.result.value;
};

const URL_GAME = `http://127.0.0.1:${HTTP_PORT}/game/index.html?mode=single&attack=${WAVE}&cb=bt${Date.now()}`;
console.log("navigate:", URL_GAME);
await send("Page.navigate", { url: URL_GAME });
await new Promise(r => setTimeout(r, 7000));
console.log("waiting for run to begin...");
const w = await evalJs(`(async () => {
  const t0 = Date.now(); let last = null;
  while (Date.now() - t0 < 180000) {
    const s = window.TASRunner ? window.TASRunner.getState() : null; last = s;
    if (s && s.actionCount > 100 && s.isPlaying && s.plannedFrame < 12) return { ok: true, s };
    await new Promise(r => setTimeout(r, 100));
  }
  return { ok: false, s: last };
})()`, true);
console.log("start:", JSON.stringify(w.s && { plannedFrame: w.s.plannedFrame, isPlaying: w.s.isPlaying, actionCount: w.s.actionCount }));
if (!w.ok) { cdp.ws.close(); process.exit(4); }

console.log("installing bone-truth tracer");
const info = await evalJs(`(() => {
  const rt = (window.c2runtime || (document.getElementById('c2canvas')||{}).c2runtime);
  const proto = rt.constructor.prototype;
  const fams = {}; (rt.types_by_index||[]).forEach(t => { if (t && t.is_family) fams[t.name] = t; });
  const CARRIER = ['t70','t66','t68'].filter(n => fams[n]);
  window.__BT = { fams: {}, rows: [], limit: ${TICKS}, err: null };
  for (const fn of CARRIER) window.__BT.fams[fn] = { members: fams[fn].members.map(m=>m.name), ivs: (fams[fn].instance_vars||[]).map(v=>v&&v.name), famIdx: fams[fn].family_index };

  function carriers() {
    const out = [];
    for (const t of (rt.types_by_index || [])) {
      if (!t || !t.instances || !t.instances.length) continue;
      if (!t.is_family && !t.family_var_map) continue;
      let famName = null;
      for (const fn of CARRIER) if (fams[fn].members.indexOf(t) >= 0) { famName = fn; break; }
      if (!famName) continue;
      const off = t.family_var_map[fams[famName].family_index] || 0;
      const names = (fams[famName].instance_vars||[]).map(v=>v&&v.name);
      for (const i of t.instances) {
        if (!i.visible) continue;
        const iv = i.instance_vars || [];
        const vars = {};
        for (let k = 0; k < names.length; k++) vars[names[k]] = iv[off + k];
        out.push({ type: t.name, iid: i.iid, inst: i, vars });
      }
    }
    return out;
  }
  window.__BT.carrierCount = carriers().length;

  const inner = proto.tick;
  proto.tick = function () {
    const r = inner.apply(this, arguments);
    const B = window.__BT;
    if (B.rows.length < B.limit) {
      try {
        const byName = {};
        for (const t of (rt.types_by_index||[])) if (t) byName[t.name] = t;
        const heart = ((byName['t55']||{}).instances||[])[0];
        const hb = ((byName['t65']||{}).instances||[])[0];
        const gv = {}; (rt.all_global_vars||[]).forEach(v => gv[v.name] = v.data);
        const s = window.TASRunner ? window.TASRunner.getState() : null;
        const bones = [], hits = [];
        if (heart && hb) {
          heart.update_bbox(); hb.update_bbox();
          for (const c of carriers()) {
            if (!c.vars || !c.vars.Damage) continue;
            const i = c.inst; i.update_bbox();
            if (i.bbox.right < heart.x - 150 || i.bbox.left > heart.x + 150) continue;
            if (i.bbox.bottom < heart.y - 150 || i.bbox.top > heart.y + 150) continue;
            const row = [c.type, c.iid, c.vars.Damage, c.vars.Color,
                         +i.bbox.left.toFixed(3), +i.bbox.top.toFixed(3),
                         +i.bbox.right.toFixed(3), +i.bbox.bottom.toFixed(3),
                         +i.width.toFixed(2), +i.height.toFixed(2)];
            bones.push(row);
            const ov = rt.testOverlap(hb, i);
            if (ov) hits.push(row.concat([1]));
          }
        }
        B.rows.push({
          hx: heart ? +heart.x.toFixed(3) : null, hy: heart ? +heart.y.toFixed(3) : null,
          hp: gv.HP, kr: gv.KR,
          f: s ? s.plannedFrame : null, playing: s ? (s.isPlaying?1:0) : null,
          hbb: hb ? [+hb.bbox.left.toFixed(3), +hb.bbox.top.toFixed(3), +hb.bbox.right.toFixed(3), +hb.bbox.bottom.toFixed(3)] : null,
          nbone: bones.length, bones: bones, hits: hits,
        });
      } catch (e) { B.err = String(e && e.stack || e); }
    }
    return r;
  };
  return { carriers: window.__BT.carrierCount, fams: window.__BT.fams };
})()`);
console.log("tracer:", JSON.stringify(info).slice(0, 1500));

console.log(`recording ${TICKS} ticks`);
const rec = await evalJs(`(async () => {
  const B = window.__BT; const t0 = Date.now();
  while (Date.now() - t0 < 120000) {
    if (B.rows.length >= B.limit) break;
    await new Promise(r => setTimeout(r, 200));
  }
  const rows = B.rows; const dmg = [];
  for (let i = 1; i < rows.length; i++) if (rows[i].hp < rows[i-1].hp) dmg.push([i, rows[i-1].hp, rows[i].hp, rows[i].f]);
  const overlaps = rows.filter(r => r.hits && r.hits.length).length;
  return { n: rows.length, err: B.err, hp0: rows[0]?.hp, hpLast: rows[rows.length-1]?.hp,
           dmgCount: dmg.length, dmg: dmg.slice(0, 60), frames_with_overlap: overlaps };
})()`, true);
console.log("record:", JSON.stringify(rec));
fs.writeFileSync(OUTFILE, await evalJs(`JSON.stringify({ rows: window.__BT.rows, err: window.__BT.err, fams: window.__BT.fams, carriers: window.__BT.carrierCount })`), "utf8");
console.log("wrote", OUTFILE);
cdp.ws.close(); process.exit(0);

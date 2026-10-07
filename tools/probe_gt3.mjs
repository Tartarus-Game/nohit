/**
 * PROBE v3 — identifies the true damage carriers via the runtime's own family
 * instance-variable mapping (inst.type.family_var_map[family_index] + offset),
 * then records, per engine tick:
 *   - heart abs pos + the engine's OWN verdicts for every candidate:
 *       contains_pt(heart.x, heart.y)     [Pick overlapping point]
 *       rt.testOverlap(hitbox, inst)      [Is overlapping]
 *       rt.testOverlap(heart,  inst)      [diagnostic]
 *   - HP, plan frame, drift
 *
 * Usage: node tools/probe_gt3.mjs [ticks] [outfile]
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
const TICKS = Number(process.argv[2] || 2400);
const OUTFILE = process.argv[3] || "tools/.gt3.json";
const WAVE = process.env.TAS_WAVE || "sans_bonegap1";

class CDP {
    constructor(wsUrl) {
        this.ws = new WebSocket(wsUrl); this.id = 0; this.pending = new Map();
        this.ready = new Promise((res, rej) => {
            this.ws.addEventListener("open", () => res());
            this.ws.addEventListener("error", (e) => rej(new Error("ws " + (e.message || e.type))));
        });
        this.ws.addEventListener("message", (ev) => {
            const m = JSON.parse(ev.data);
            if (m.id !== undefined && this.pending.has(m.id)) {
                const { resolve, reject } = this.pending.get(m.id); this.pending.delete(m.id);
                m.error ? reject(new Error(JSON.stringify(m.error))) : resolve(m.result);
            }
        });
    }
    send(method, params = {}, sessionId) {
        const id = ++this.id; const p = { id, method, params };
        if (sessionId) p.sessionId = sessionId;
        this.ws.send(JSON.stringify(p));
        return new Promise((res, rej) => {
            this.pending.set(id, { resolve: res, reject: rej });
            setTimeout(() => { if (this.pending.delete(id)) rej(new Error("timeout " + method)); }, 180000);
        });
    }
}
const targets = await fetch(`http://127.0.0.1:${CDP_PORT}/json/list`).then(r => r.json());
const page = targets.find(t => t.type === "page" && /127\.0\.0\.1:8099\/game/.test(t.url || ""))
    || targets.find(t => t.type === "page" && !/chrome-extension/.test(t.url || ""));
if (!page) { console.error("no page"); process.exit(3); }
console.log("target:", page.url);
const cdp = new CDP(page.webSocketDebuggerUrl);
await cdp.ready;
const { sessionId } = await cdp.send("Target.attachToTarget", { targetId: page.id, flatten: true });
const send = (m, p) => cdp.send(m, p, sessionId);
await send("Page.enable"); await send("Runtime.enable");
const evalJs = async (expr, awaitPromise = false) => {
    const r = await send("Runtime.evaluate", { expression: expr, awaitPromise, returnByValue: true });
    if (r.exceptionDetails) throw new Error(r.exceptionDetails.exception?.description || r.exceptionDetails.text);
    return r.result.value;
};

const URL_GAME = `http://127.0.0.1:${HTTP_PORT}/game/index.html?mode=single&attack=${WAVE}&cb=g3${Date.now()}`;
console.log("=== navigate:", URL_GAME);
await send("Page.navigate", { url: URL_GAME });
await new Promise(r => setTimeout(r, 8000));
console.log("=== waiting for plan + playback");
const w = await evalJs(`(async () => {
  const t0 = Date.now(); let last = null;
  while (Date.now() - t0 < 180000) {
    const s = window.TASRunner ? window.TASRunner.getState() : null; last = s;
    if (s && s.actionCount > 100 && s.isPlaying) return { ok: true, s, ms: Date.now() - t0 };
    await new Promise(r => setTimeout(r, 400));
  }
  return { ok: false, s: last };
})()`, true);
console.log("plan:", JSON.stringify(w.s));
if (!w.ok) { cdp.ws.close(); process.exit(4); }

console.log("=== installing tracer v3");
const info = await evalJs(`(() => {
  const rt = (window.c2runtime || (document.getElementById('c2canvas')||{}).c2runtime);
  const proto = rt.constructor.prototype;

  // family index + var map for the three Damage-carrying families
  const fams = {};
  (rt.types_by_index||[]).forEach((t, idx) => { if (t && t.is_family) fams[t.name] = t; });
  const CARRIER_FAMS = ['t70','t66','t68'].filter(n => fams[n]);
  const memberTypes = new Set();
  for (const fn of CARRIER_FAMS) for (const m of fams[fn].members) memberTypes.add(m.name);

  function carriers(onlyNear, hx, hy) {
    const out = [];
    for (const t of (rt.types_by_index || [])) {
      if (!t || !t.instances || !t.instances.length) continue;
      if (!memberTypes.has(t.name)) continue;
      // which carrier family does this member belong to?
      let famName = null;
      for (const fn of CARRIER_FAMS) if (fams[fn].members.indexOf(t) >= 0) { famName = fn; break; }
      const fIdx = fams[famName].family_index;
      const off = t.family_var_map ? (t.family_var_map[fIdx] || 0) : 0;
      const ivNames = (fams[famName].instance_vars || []).map(v => v && v.name);
      for (const i of t.instances) {
        if (!i.visible) continue;
        const iv = i.instance_vars || [];
        const vals = {};
        for (let k = 0; k < ivNames.length; k++) vals[ivNames[k]] = iv[off + k];
        if (onlyNear) {
          if (i.bbox.right < hx - 80 || i.bbox.left > hx + 80) continue;
          if (i.bbox.bottom < hy - 80 || i.bbox.top > hy + 80) continue;
        }
        out.push({ name: t.name, fam: famName, iid: i.iid, inst: i, vars: vals, off: off });
      }
    }
    return out;
  }
  const probe = carriers(false, 0, 0);
  const uniq = {};
  for (const c of probe) uniq[c.name + ':' + JSON.stringify(c.vars)] = (uniq[c.name + ':' + JSON.stringify(c.vars)]||0)+1;
  window.__G3 = { rows: [], limit: ${TICKS}, carrierSample: uniq };
  if (!proto.__g3Wrapped) {
    const orig = proto.tick;
    proto.tick = function () {
      const r = orig.apply(this, arguments);
      const G = window.__G3;
      if (G.rows.length < G.limit) {
        try {
          const byName = {};
          for (const t of (rt.types_by_index||[])) if (t) byName[t.name] = t;
          const heart = ((byName['t55']||{}).instances||[])[0];
          const hb = ((byName['t65']||{}).instances||[])[0];
          const gv = {}; (rt.all_global_vars||[]).forEach(v => gv[v.name] = v.data);
          const s = window.TASRunner ? window.TASRunner.getState() : null;
          const cs = carriers(true, heart.x, heart.y).filter(c => c.vars.Damage);   // Damage != 0
          const hits = [], near = [];
          if (heart && hb) {
            hb.update_bbox(); heart.update_bbox();
            for (const c of cs) {
              const i = c.inst; i.update_bbox();
              const dx = Math.max(i.bbox.left - heart.x, heart.x - i.bbox.right, 0);
              const dy = Math.max(i.bbox.top - heart.y, heart.y - i.bbox.bottom, 0);
              if (Math.max(dx, dy) > 60) continue;
              const row = [c.name, c.iid, c.vars.Damage, c.vars.Karma, c.vars.Color,
                           +i.bbox.left.toFixed(2), +i.bbox.top.toFixed(2),
                           +i.bbox.right.toFixed(2), +i.bbox.bottom.toFixed(2)];
              near.push(row);
              const pt = i.contains_pt(heart.x, heart.y);
              const ov = rt.testOverlap(hb, i);
              const ovh = rt.testOverlap(heart, i);
              if (pt || ov || ovh) hits.push(row.concat([pt?1:0, ov?1:0, ovh?1:0]));
            }
          }
          G.rows.push({
            hx: heart ? +heart.x.toFixed(3) : null, hy: heart ? +heart.y.toFixed(3) : null,
            hp: gv.HP, f: s ? s.plannedFrame : null, drift: s ? s.drift : null,
            hbb: hb ? [+hb.bbox.left.toFixed(3), +hb.bbox.top.toFixed(3), +hb.bbox.right.toFixed(3), +hb.bbox.bottom.toFixed(3)] : null,
            hcb: heart ? [+heart.bbox.left.toFixed(3), +heart.bbox.top.toFixed(3), +heart.bbox.right.toFixed(3), +heart.bbox.bottom.toFixed(3)] : null,
            ncar: cs.length, hits: hits.length ? hits : null,
            near: (G.rows.length % 4 === 0) ? near : null,
          });
        } catch (e) { G.err = String(e && e.stack || e); }
      }
      return r;
    };
    proto.__g3Wrapped = true;
  }
  return { installed: true, kinds: Object.keys(uniq).slice(0, 24), n: probe.length, err: window.__G3.err || null };
})()`);
console.log("tracer:", JSON.stringify(info).slice(0, 3000));

console.log(`=== recording ${TICKS} ticks`);
const rec = await evalJs(`(async () => {
  const G = window.__G3; const t0 = Date.now();
  while (Date.now() - t0 < 240000) {
    if (G.rows.length >= G.limit) break;
    const s = window.TASRunner ? window.TASRunner.getState() : null;
    if (s && s.actionCount > 0 && !s.isPlaying && G.rows.length > 50) break;
    await new Promise(r => setTimeout(r, 400));
  }
  const rows = G.rows; const dmg = [];
  for (let i = 1; i < rows.length; i++) if (rows[i].hp < rows[i-1].hp) dmg.push([i, rows[i-1].hp, rows[i].hp, rows[i].f]);
  return { n: rows.length, err: G.err || null, hp0: rows[0]?.hp, hpLast: rows[rows.length-1]?.hp,
           dmgCount: dmg.length, dmg: dmg.slice(0, 60) };
})()`, true);
console.log("record:", JSON.stringify(rec));
fs.writeFileSync(OUTFILE, await evalJs(`JSON.stringify({ rows: window.__G3.rows, err: window.__G3.err||null, carrierSample: window.__G3.carrierSample })`), "utf8");
console.log("wrote", OUTFILE);
cdp.ws.close(); process.exit(0);

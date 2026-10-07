/**
 * Instrumented ground-truth probe v2.
 *
 * Fixes the identification bug in v1: the damage primitive is defined by
 * Battle.xml as
 *
 *   System  | Pick overlapping point(Attack9Patch, PlayerHeart.X, PlayerHeart.Y)
 *   PlayerHitbox | Is overlapping another object(Attack9Patch)
 *   Attack9Patch  | Damage != 0
 *   ... sub-event: Attack9Patch.Color == 0  ->  DamagePlayer
 *
 * so the candidate set is every visible instance that CARRIES the instance
 * variables Damage/Karma (i.e. an Attack9Patch / AttackSprite / AttackTiled
 * family member). We find those by looking at the live instances' own
 * instance_vars, and then ask the ENGINE for its verdicts
 * (`inst.contains_pt` and `rt.testOverlap`) instead of guessing object names.
 *
 * Usage: node tools/probe_gt2.mjs [ticks] [outfile]
 */

import fs from "node:fs";

const HTTP_PORT = "8099";
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
const OUTFILE = process.argv[3] || "tools/.gt2.json";
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
if (!page) { console.error("no page target"); process.exit(3); }
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

// The runtime is not always reachable as window.c2runtime; every other tool in
// this repo resolves it through the canvas, so mirror that here.
const GET_RT = `(window.c2runtime || (document.getElementById('c2canvas')||{}).c2runtime)`;

// ------------------------------------------------------------------ 1. census
const URL_GAME = `http://127.0.0.1:${HTTP_PORT}/game/index.html?mode=single&attack=${WAVE}&cb=g2${Date.now()}`;
console.log("=== navigate:", URL_GAME);
await send("Page.navigate", { url: URL_GAME });
await new Promise((r) => setTimeout(r, 8000));

console.log("=== waiting for plan + auto-start (<=180 s)");
const waitRes = await evalJs(`(async () => {
  const t0 = Date.now();
  let last = null;
  while (Date.now() - t0 < 180000) {
    const s = window.TASRunner ? window.TASRunner.getState() : null;
    last = s;
    if (s && s.actionCount > 100 && s.isPlaying) return { ok: true, state: s, ms: Date.now() - t0 };
    await new Promise(r => setTimeout(r, 400));
  }
  return { ok: false, state: last, ms: Date.now() - t0 };
})()`, true);
console.log("plan:", JSON.stringify(waitRes.state));
if (!waitRes.ok) { console.error("plan never started"); cdp.ws.close(); process.exit(4); }

// family membership (authoritative, from the runtime)
const fams = await evalJs(`(() => {
  const rt = (window.c2runtime || (document.getElementById('c2canvas')||{}).c2runtime);
  const out = {};
  (rt.types_by_index||[]).forEach(t => { if (t && t.is_family) out[t.name] = (t.members||[]).map(m=>m.name); });
  return out;
})()`);
console.log("families:", JSON.stringify(fams));

// ------------------------------------------------------------------ 2. tracer
console.log("=== installing tracer");
await evalJs(`(() => {
  const rt = (window.c2runtime || (document.getElementById('c2canvas')||{}).c2runtime);
  const proto = rt.constructor.prototype;
  const fams = ${JSON.stringify(fams)};
  // every type name that is a member of a Damage-carrying family
  const memberTypes = new Set();
  for (const f of ['t70','t66','t68']) (fams[f]||[]).forEach(n=>memberTypes.add(n));

  function damageCarriers() {
    const res = [];
    const types = rt.types_by_index || [];
    for (const t of types) {
      if (!t || !t.instances || !t.instances.length) continue;
      if (!memberTypes.has(t.name)) continue;
      for (const i of t.instances) {
        if (!i.visible) continue;
        let dmg = null, karma = null, color = null;
        const iv = i.instance_vars || [];
        const tn = i.type.instance_vars || [];
        for (let k = 0; k < iv.length; k++) {
          const nm = tn[k] && tn[k].name;
          if (nm === 'Damage') dmg = iv[k];
          else if (nm === 'Karma') karma = iv[k];
          else if (nm === 'Color') color = iv[k];
        }
        if (dmg === null || dmg === 0) continue;   // engine requires Damage != 0
        res.push({ t: t.name, iid: i.iid, inst: i, dmg: dmg, karma: karma, color: color });
      }
    }
    return res;
  }
  window.__G2 = { rows: [], limit: ${TICKS}, carriers: 0 };
  if (!proto.__g2Wrapped) {
    const orig = proto.tick;
    proto.tick = function () {
      const r = orig.apply(this, arguments);
      const G = window.__G2;
      if (G.rows.length < G.limit) {
        try {
          const types = rt.types_by_index || [];
          const byName = {};
          for (const t of types) if (t) byName[t.name] = t;
          const heart = ((byName['t55']||{}).instances||[])[0];
          const hb = ((byName['t65']||{}).instances||[])[0];
          const gv = {}; (rt.all_global_vars || []).forEach(v => gv[v.name] = v.data);
          const s = window.TASRunner ? window.TASRunner.getState() : null;
          const carriers = damageCarriers();
          G.carriers = carriers.length;
          const nearby = [];
          const verdicts = [];
          if (heart && hb) {
            hb.update_bbox();
            heart.update_bbox();
            for (const c of carriers) {
              const i = c.inst;
              i.update_bbox();
              if (Math.abs(i.bbox.left - heart.x) > 320 && Math.abs(i.bbox.right - heart.x) > 320) continue;
              const row = [c.t, c.iid, c.dmg, c.karma, c.color,
                           +i.bbox.left.toFixed(2), +i.bbox.top.toFixed(2),
                           +i.bbox.right.toFixed(2), +i.bbox.bottom.toFixed(2),
                           +i.width.toFixed(2), +i.height.toFixed(2), +i.x.toFixed(2), +i.y.toFixed(2)];
              nearby.push(row);
              const pt = i.contains_pt(heart.x, heart.y);
              const ov = rt.testOverlap(hb, i);
              const ovHeart = rt.testOverlap(heart, i);
              if (pt || ov || ovHeart) verdicts.push(row.concat([pt?1:0, ov?1:0, ovHeart?1:0]));
            }
          }
          G.rows.push({
            hx: heart ? +heart.x.toFixed(3) : null,
            hy: heart ? +heart.y.toFixed(3) : null,
            hp: gv.HP, kr: gv.KR, ldt: gv.LastDamageTime,
            vis: heart ? (heart.visible?1:0) : null,
            f: s ? s.plannedFrame : null, cur: s ? s.currentFrame : null,
            playing: s ? (s.isPlaying?1:0) : null,
            drift: s ? s.drift : null,
            hbb: hb ? [+hb.bbox.left.toFixed(3), +hb.bbox.top.toFixed(3), +hb.bbox.right.toFixed(3), +hb.bbox.bottom.toFixed(3)] : null,
            hcb: heart ? [+heart.bbox.left.toFixed(3), +heart.bbox.top.toFixed(3), +heart.bbox.right.toFixed(3), +heart.bbox.bottom.toFixed(3)] : null,
            ncar: carriers.length,
            hits: verdicts.length ? verdicts : null,
            near: (G.rows.length % 8 === 0) ? nearby : null,
          });
        } catch (e) { G.err = String(e && e.stack || e); }
      }
      return r;
    };
    proto.__g2Wrapped = true;
  }
  return { installed: true, carriers: window.__G2.carriers };
})()`);

console.log(`=== recording ${TICKS} ticks`);
const rec = await evalJs(`(async () => {
  const G = window.__G2;
  const t0 = Date.now();
  while (Date.now() - t0 < 240000) {
    if (G.rows.length >= G.limit) break;
    const s = window.TASRunner ? window.TASRunner.getState() : null;
    if (s && s.actionCount > 0 && !s.isPlaying && G.rows.length > 50) break;
    await new Promise(r => setTimeout(r, 400));
  }
  const rows = G.rows;
  const dmg = [];
  for (let i = 1; i < rows.length; i++) if (rows[i].hp < rows[i-1].hp) dmg.push([i, rows[i-1].hp, rows[i].hp, rows[i].f]);
  return { n: rows.length, err: G.err || null, carriers: G.carriers,
           hp0: rows[0] && rows[0].hp, hpLast: rows[rows.length-1] && rows[rows.length-1].hp,
           dmgCount: dmg.length, dmg: dmg.slice(0, 100),
           state: window.TASRunner ? window.TASRunner.getState() : null };
})()`, true);
console.log("record:", JSON.stringify(rec).slice(0, 2500));
const dump = await evalJs(`JSON.stringify({ rows: window.__G2.rows, err: window.__G2.err || null, families: ${JSON.stringify(fams)} })`);
fs.writeFileSync(OUTFILE, dump, "utf8");
console.log("wrote", OUTFILE, dump.length, "bytes");
cdp.ws.close();
process.exit(0);

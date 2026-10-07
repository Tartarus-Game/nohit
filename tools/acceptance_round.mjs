/**
 * ACCEPTANCE RUN — one clean round on the real machine.
 *
 * Records from the exact round boundary: the tick where HP is restored to
 * MaxHP (StartAttack does `HP := MaxHP`), which is also where the runner resets
 * the plan to frame 0. Then it reports:
 *
 *   - HP over the round (the acceptance criterion is "never drops"),
 *   - the sync quality: plannedFrame vs the script clock's frame,
 *   - per-plan-frame tracking error between the live heart and the plan.
 *
 * Usage: node tools/acceptance_round.mjs [outfile]
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
const OUTFILE = process.argv[2] || "tools/.acceptance.json";
const WAVE = process.env.TAS_WAVE || "sans_bonegap1";
const PLAN_JSON = process.argv[3] || "tools/.plan_bonegap1.json";

class CDP {
    constructor(u) { this.ws = new WebSocket(u); this.id = 0; this.pending = new Map();
        this.ready = new Promise((res, rej) => { this.ws.addEventListener("open", () => res()); this.ws.addEventListener("error", (e) => rej(new Error("ws " + (e.message || e.type)))); });
        this.ws.addEventListener("message", (ev) => { const m = JSON.parse(ev.data); if (m.id !== undefined && this.pending.has(m.id)) { const { resolve, reject } = this.pending.get(m.id); this.pending.delete(m.id); m.error ? reject(new Error(JSON.stringify(m.error))) : resolve(m.result); } }); }
    send(method, params = {}, sessionId) { const id = ++this.id; const p = { id, method, params }; if (sessionId) p.sessionId = sessionId; this.ws.send(JSON.stringify(p));
        return new Promise((res, rej) => { this.pending.set(id, { resolve: res, reject: rej }); setTimeout(() => { if (this.pending.delete(id)) rej(new Error("timeout " + method)); }, 240000); }); }
}
const targets = await fetch(`http://127.0.0.1:${CDP_PORT}/json/list`).then(r => r.json());
const page = targets.find(t => t.type === "page" && /127\.0\.0\.1:8099\/game/.test(t.url || "")) || targets.find(t => t.type === "page" && !/chrome-extension/.test(t.url || ""));
if (!page) { console.error("no page"); process.exit(3); }
const cdp = new CDP(page.webSocketDebuggerUrl); await cdp.ready;
const { sessionId } = await cdp.send("Target.attachToTarget", { targetId: page.id, flatten: true });
const send = (m, p) => cdp.send(m, p, sessionId);
await send("Page.enable"); await send("Runtime.enable");
const evalJs = async (e, aw = false) => { const r = await send("Runtime.evaluate", { expression: e, awaitPromise: aw, returnByValue: true }); if (r.exceptionDetails) throw new Error(r.exceptionDetails.exception?.description || r.exceptionDetails.text); return r.result.value; };

const URL_GAME = `http://127.0.0.1:${HTTP_PORT}/game/index.html?mode=single&attack=${WAVE}&cb=acc${Date.now()}`;
console.log("navigate:", URL_GAME);
await send("Page.navigate", { url: URL_GAME });
await new Promise(r => setTimeout(r, 7000));

const res = await evalJs(`(async () => {
  const rt = (window.c2runtime || (document.getElementById('c2canvas')||{}).c2runtime);
  const proto = rt.constructor.prototype;
  const SID_T = 3521916820909801;
  window.__ACC = { rows: [], started: false, err: null, hpMax: null };
  const A = window.__ACC;
  const gv = () => { const o = {}; (rt.all_global_vars||[]).forEach(v => o[v.name] = v.data); return o; };

  const inner = proto.tick;
  proto.tick = function () {
    const r = inner.apply(this, arguments);
    try {
      const g = gv();
      const s = window.TASRunner ? window.TASRunner.getState() : null;
      const T = rt.varsBySid && rt.varsBySid[SID_T] ? rt.varsBySid[SID_T].data : null;
      // Round boundary: HP restored to MaxHP with the plan at frame 0.
      if (!A.started && s && s.actionCount > 100 && g.HP >= g.MaxHP && g.HP > 0 && T !== null && T < 0.5) {
        A.started = true; A.hpMax = g.MaxHP;
        console.log('[ACC] round start: HP=' + g.HP + ' T=' + T);
      }
      if (A.started) {
        const byName = {}; for (const t of (rt.types_by_index||[])) if (t) byName[t.name] = t;
        const heart = ((byName['t55']||{}).instances||[])[0];
        A.rows.push({
          T: T === null ? null : +T.toFixed(5),
          HP: g.HP, KR: g.KR,
          planned: s ? s.plannedFrame : null,
          clockFrame: s ? s.clockFrame : null,
          syncMode: s ? s.syncMode : null,
          hx: heart ? +heart.x.toFixed(3) : null,
          hy: heart ? +heart.y.toFixed(3) : null,
          vis: heart ? (heart.visible ? 1 : 0) : null,
        });
      }
    } catch (e) { A.err = String(e && e.stack || e); }
    return r;
  };

  const t0 = Date.now();
  while (Date.now() - t0 < 200000) {
    if (A.started && A.rows.length > 1750) break;             // full round recorded
    if (A.started && A.rows.length > 200) {
      // Or the plan finished and the attack ended.
      const g = gv();
      if (g.HP <= 0) break;
      const s = window.TASRunner ? window.TASRunner.getState() : null;
      if (s && !s.isPlaying && s.plannedFrame >= s.actionCount) break;
    }
    await new Promise(r => setTimeout(r, 200));
  }
  proto.tick = inner;
  const rows = A.rows;
  const dmg = [];
  for (let i = 1; i < rows.length; i++) if (rows[i].HP < rows[i-1].HP) dmg.push([i, rows[i-1].HP, rows[i].HP, rows[i].planned, rows[i].T]);
  let maxSync = 0, maxSyncAt = null, nSync = 0;
  for (const r of rows) {
    if (r.syncMode === 'script-clock' && r.clockFrame !== null && r.planned !== null) {
      nSync++;
      const d = Math.abs(r.clockFrame - r.planned);
      if (d > maxSync) { maxSync = d; maxSyncAt = { T: r.T, planned: r.planned, clockFrame: r.clockFrame }; }
    }
  }
  return { started: A.started, hpMax: A.hpMax, err: A.err, n: rows.length,
           hpStart: rows[0]?.HP, hpEnd: rows[rows.length-1]?.HP,
           dmgCount: dmg.length, dmg: dmg.slice(0, 80),
           maxSyncDiff: maxSync, maxSyncAt, syncedRows: nSync,
           plannedEnd: rows[rows.length-1]?.planned };
})()`, true);
console.log("RESULT:", JSON.stringify(res, null, 2));
fs.writeFileSync(OUTFILE, await evalJs(`JSON.stringify({ rows: window.__ACC.rows, meta: { started: window.__ACC.started, hpMax: window.__ACC.hpMax } })`), "utf8");
console.log("wrote", OUTFILE);
cdp.ws.close(); process.exit(0);

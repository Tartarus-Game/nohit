/**
 * Verifies STRICT SYNC: the plan frame must equal floor(scriptClock * 60), where
 * scriptClock is the Timeline sheet's `T` (advanced by dt in Timeline.xml).
 *
 * Prints, once per tick: the script clock T, the runner's plannedFrame, the
 * tick-derived frame, and the heart's position. If sync holds, the game clock's
 * frame and the runner's frame stay equal for the whole round.
 *
 * Usage: node tools/probe_sync.mjs [ticks]
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
const OUTFILE = process.argv[3] || "tools/.sync_probe.json";
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

const URL_GAME = `http://127.0.0.1:${HTTP_PORT}/game/index.html?mode=single&attack=${WAVE}&cb=sy${Date.now()}`;
console.log("navigate:", URL_GAME);
await send("Page.navigate", { url: URL_GAME });
await new Promise(r => setTimeout(r, 7000));

// Install the sampler FIRST, then wait for the round to begin.
console.log("installing sync sampler");
const info = await evalJs(`(() => {
  const rt = (window.c2runtime || (document.getElementById('c2canvas')||{}).c2runtime);
  const proto = rt.constructor.prototype;

  function sheets() {
    const out = []; const push = s => { if (s && out.indexOf(s) === -1) out.push(s); };
    if (!rt.running_layout) return out;
    push(rt.running_layout.event_sheet);
    for (let i = 0; i < out.length; i++) {
      const s = out[i]; push(s.parent_sheet);
      if (Array.isArray(s.includes)) s.includes.forEach(push);
      if (Array.isArray(s.deep_includes)) s.deep_includes.forEach(push);
    }
    return out;
  }
  // C2 indexes every variable in runtime.varsBySid; Timeline's T is
  // sid 3521916820909801 and Running is sid 164016619418963.
  const SIDS = { T: 3521916820909801, Running: 164016619418963 };
  function sheetVar(name) {
    const sid = SIDS[name];
    if (sid && rt.varsBySid && rt.varsBySid[sid] && typeof rt.varsBySid[sid].data === "number") return rt.varsBySid[sid].data;
    for (const s of sheets()) {
      const d = s.localvardict;
      if (d && d[name] && typeof d[name].data === "number") return d[name].data;
      if (Array.isArray(s.localvars)) for (const v of s.localvars) if (v && v.name === name && typeof v.data === "number") return v.data;
    }
    return null;
  }
  window.__SY = { rows: [], limit: ${TICKS}, err: null, hasT: null, sheetNames: sheets().map(s => s.name) };
  const inner = proto.tick;
  proto.tick = function () {
    const r = inner.apply(this, arguments);
    const S = window.__SY;
    if (S.rows.length < S.limit) {
      try {
        const T = sheetVar('T'), Running = sheetVar('Running');
        if (S.hasT === null) S.hasT = (T !== null);
        const byName = {}; for (const t of (rt.types_by_index||[])) if (t) byName[t.name] = t;
        const heart = ((byName['t55']||{}).instances||[])[0];
        const gv = {}; (rt.all_global_vars||[]).forEach(v => gv[v.name] = v.data);
        const s = window.TASRunner ? window.TASRunner.getState() : null;
        const tickFrame = s ? Math.floor((S.rows.length) / 4) : null;
        S.rows.push({
          T: T === null ? null : +T.toFixed(5), Running,
          planned: s ? s.plannedFrame : null,
          clockFrame: s ? s.clockFrame : null,
          syncMode: s ? s.syncMode : null,
          tickFrame,
          hx: heart ? +heart.x.toFixed(3) : null, hy: heart ? +heart.y.toFixed(3) : null,
          hp: gv.HP,
        });
      } catch (e) { S.err = String(e && e.stack || e); }
    }
    return r;
  };
  return { installed: true, sheets: window.__SY.sheetNames, T: sheetVar('T'), Running: sheetVar('Running') };
})()`);
console.log("sampler:", JSON.stringify(info));

console.log("waiting for the round to reach plannedFrame ~ a few then recording...");
const rec = await evalJs(`(async () => {
  const S = window.__SY; const t0 = Date.now();
  while (Date.now() - t0 < 180000) {
    if (S.rows.length >= S.limit) break;
    await new Promise(r => setTimeout(r, 200));
  }
  const rows = S.rows;
  const modes = [...new Set(rows.map(r => r.syncMode))];
  let maxAbs = 0, maxAt = null, nSynced = 0;
  for (const r of rows) {
    if (r.clockFrame !== null && r.planned !== null && r.syncMode === 'script-clock') {
      nSynced++;
      const d = Math.abs(r.clockFrame - r.planned);
      if (d > maxAbs) { maxAbs = d; maxAt = { T: r.T, planned: r.planned, clockFrame: r.clockFrame }; }
    }
  }
  const f = rows.find(r => r.syncMode === 'script-clock');
  const l = [...rows].reverse().find(r => r.syncMode === 'script-clock');
  let clockAdvance = null, tickAdvance = null;
  if (f && l) { clockAdvance = +(l.T - f.T).toFixed(3); tickAdvance = rows.indexOf(l) - rows.indexOf(f); }
  let dmg = 0; for (let i = 1; i < rows.length; i++) if (rows[i].hp < rows[i-1].hp) dmg++;
  return { n: rows.length, err: S.err, hasT: S.hasT, syncModes: modes, syncedRows: nSynced,
           hp0: rows[0]?.hp, hpLast: rows[rows.length-1]?.hp, dmgCount: dmg,
           maxAbsClockVsPlanned: maxAbs, maxAt, clockAdvance, ticks: tickAdvance,
           eff_tick_hz: (clockAdvance && tickAdvance) ? +(tickAdvance / clockAdvance).toFixed(2) : null };
})()`, true);
console.log("RECORD:", JSON.stringify(rec, null, 2));
fs.writeFileSync(OUTFILE, await evalJs(`JSON.stringify({ rows: window.__SY.rows.slice(0, 900), err: window.__SY.err, sheets: window.__SY.sheetNames })`), "utf8");
console.log("wrote", OUTFILE);
cdp.ws.close(); process.exit(0);

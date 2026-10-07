/**
 * Per-tick probe of the sync quantities: engine tick, wall clock, script clock
 * `T`, the frame the runner derived from it, and the frame actually being
 * played. Prints consecutive deltas so the loop can be reconciled exactly.
 *
 * Usage: node tools/probe_sync_detail.mjs [ticks]
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
const TICKS = Number(process.argv[2] || 60);
class CDP {
    constructor(u) { this.ws = new WebSocket(u); this.id = 0; this.pending = new Map();
        this.ready = new Promise((res, rej) => { this.ws.addEventListener("open", () => res()); this.ws.addEventListener("error", (e) => rej(new Error("ws " + (e.message || e.type)))); });
        this.ws.addEventListener("message", (ev) => { const m = JSON.parse(ev.data); if (m.id !== undefined && this.pending.has(m.id)) { const { resolve, reject } = this.pending.get(m.id); this.pending.delete(m.id); m.error ? reject(new Error(JSON.stringify(m.error))) : resolve(m.result); } }); }
    send(method, params = {}, sessionId) { const id = ++this.id; const p = { id, method, params }; if (sessionId) p.sessionId = sessionId; this.ws.send(JSON.stringify(p));
        return new Promise((res, rej) => { this.pending.set(id, { resolve: res, reject: rej }); setTimeout(() => { if (this.pending.delete(id)) rej(new Error("timeout " + method)); }, 120000); }); }
}
const targets = await fetch(`http://127.0.0.1:${CDP_PORT}/json/list`).then(r => r.json());
const page = targets.find(t => t.type === "page" && /127\.0\.0\.1:8099\/game/.test(t.url || "")) || targets.find(t => t.type === "page" && !/chrome-extension/.test(t.url || ""));
if (!page) { console.error("no page"); process.exit(3); }
const cdp = new CDP(page.webSocketDebuggerUrl); await cdp.ready;
const { sessionId } = await cdp.send("Target.attachToTarget", { targetId: page.id, flatten: true });
const send = (m, p) => cdp.send(m, p, sessionId);
await send("Page.enable"); await send("Runtime.enable");
const evalJs = async (e, aw = false) => { const r = await send("Runtime.evaluate", { expression: e, awaitPromise: aw, returnByValue: true }); if (r.exceptionDetails) throw new Error(r.exceptionDetails.exception?.description || r.exceptionDetails.text); return r.result.value; };

const URL_GAME = `http://127.0.0.1:${HTTP_PORT}/game/index.html?mode=single&attack=sans_bonegap1&cb=sd${Date.now()}`;
console.log("navigate:", URL_GAME);
await send("Page.navigate", { url: URL_GAME });
await new Promise(r => setTimeout(r, 7000));

const res = await evalJs(`(async () => {
  const rt = (window.c2runtime || (document.getElementById('c2canvas')||{}).c2runtime);
  const proto = rt.constructor.prototype;
  const SID_T = 3521916820909801, SID_RUN = 164016619418963;
  const rows = [];
  const inner = proto.tick;
  proto.tick = function () {
    const r = inner.apply(this, arguments);
    if (rows.length < ${TICKS}) {
      const s = window.TASRunner ? window.TASRunner.getState() : null;
      rows.push({
        w: performance.now(),
        T: rt.varsBySid && rt.varsBySid[SID_T] ? rt.varsBySid[SID_T].data : null,
        Run: rt.varsBySid && rt.varsBySid[SID_RUN] ? rt.varsBySid[SID_RUN].data : null,
        planned: s ? s.plannedFrame : null,
        clockFrame: s ? s.clockFrame : null,
        clockT: s ? s.clockT : null,
        syncMode: s ? s.syncMode : null,
        hp: (() => { const o={}; (rt.all_global_vars||[]).forEach(v=>o[v.name]=v.data); return o.HP; })(),
      });
    }
    return r;
  };
  // wait until the runner is actually playing
  const t0 = Date.now();
  while (Date.now() - t0 < 180000) {
    const s = window.TASRunner ? window.TASRunner.getState() : null;
    if (s && s.isPlaying && s.actionCount > 100 && s.plannedFrame > 1) break;
    await new Promise(r => setTimeout(r, 100));
  }
  // collect a burst of consecutive ticks
  const start = rows.length;
  while (rows.length < start + ${TICKS}) await new Promise(r => setTimeout(r, 50));
  proto.tick = inner;
  return rows.slice(start);
})()`, true);
console.log("tick | dWall(ms) | T          | dT        | planned | clockFrame | syncMode     | hp");
let pw = null, pT = null, pf = null;
for (let i = 0; i < res.length; i++) {
    const r = res[i];
    const dw = pw === null ? "" : (r.w - pw).toFixed(2);
    const dT = pT === null ? "" : (r.T - pT).toFixed(5);
    console.log(`${String(i).padStart(4)} | ${String(dw).padStart(9)} | ${String(r.T).padEnd(10)} | ${String(dT).padStart(9)} | ${String(r.planned).padStart(7)} | ${String(r.clockFrame).padStart(10)} | ${String(r.syncMode).padEnd(12)} | ${r.hp}`);
    pw = r.w; pT = r.T; pf = r.planned;
}
cdp.ws.close(); process.exit(0);

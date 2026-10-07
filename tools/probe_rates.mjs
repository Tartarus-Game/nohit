/**
 * Measures the ACTUAL engine tick rate and the runner's plan-step rate.
 * Fast: no tracer, just a counter over a few seconds.
 *
 * Usage: node tools/probe_rates.mjs
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
class CDP {
    constructor(u) {
        this.ws = new WebSocket(u); this.id = 0; this.pending = new Map();
        this.ready = new Promise((res, rej) => { this.ws.addEventListener("open", () => res()); this.ws.addEventListener("error", (e) => rej(new Error("ws " + (e.message || e.type)))); });
        this.ws.addEventListener("message", (ev) => { const m = JSON.parse(ev.data); if (m.id !== undefined && this.pending.has(m.id)) { const { resolve, reject } = this.pending.get(m.id); this.pending.delete(m.id); m.error ? reject(new Error(JSON.stringify(m.error))) : resolve(m.result); } });
    }
    send(method, params = {}, sessionId) {
        const id = ++this.id; const p = { id, method, params }; if (sessionId) p.sessionId = sessionId;
        this.ws.send(JSON.stringify(p));
        return new Promise((res, rej) => { this.pending.set(id, { resolve: res, reject: rej }); setTimeout(() => { if (this.pending.delete(id)) rej(new Error("timeout " + method)); }, 120000); });
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
const URL_GAME = `http://127.0.0.1:${HTTP_PORT}/game/index.html?mode=single&attack=sans_bonegap1&cb=rt${Date.now()}`;
console.log("navigate:", URL_GAME);
await send("Page.navigate", { url: URL_GAME });
await new Promise(r => setTimeout(r, 7000));
console.log("wait for plan...");
const w = await evalJs(`(async () => {
  const t0 = Date.now(); let last=null;
  while (Date.now()-t0 < 180000) { const s = window.TASRunner ? window.TASRunner.getState() : null; last=s;
    if (s && s.actionCount > 100 && s.isPlaying) return {ok:true, s}; await new Promise(r=>setTimeout(r,400)); }
  return {ok:false, s:last};
})()`, true);
console.log("plan:", JSON.stringify(w.s));

// Count engine ticks by wrapping the CURRENT prototype.tick (which the runner
// has already wrapped) for a fixed wall-clock window, and sample rt.fps plus the
// runner's own frame counter.
const res = await evalJs(`(async () => {
  const rt = (window.c2runtime || (document.getElementById('c2canvas')||{}).c2runtime);
  const proto = rt.constructor.prototype;
  const inner = proto.tick;             // runner's wrapped version (or original)
  let ticks = 0;
  const t0 = performance.now();
  const f0 = window.TASRunner.getState().plannedFrame;
  const e0 = window.__tasEngineTickDebug === undefined ? null : window.__tasEngineTickDebug;
  proto.tick = function () { ticks++; return inner.apply(this, arguments); };
  await new Promise(r => setTimeout(r, 3000));
  proto.tick = inner;
  const dt = performance.now() - t0;
  const s = window.TASRunner.getState();
  return {
    wall_ms: Math.round(dt), ticks,
    tick_hz: +(ticks / (dt/1000)).toFixed(1),
    rt_fps: rt.fps,
    plan_frames_in_window: s.plannedFrame - f0,
    plan_hz: +((s.plannedFrame - f0) / (dt/1000)).toFixed(1),
    state: { plannedFrame: s.plannedFrame, currentFrame: s.currentFrame, isPlaying: s.isPlaying, actionCount: s.actionCount, drift: s.drift },
  };
})()`, true);
console.log("RATES:", JSON.stringify(res, null, 2));
cdp.ws.close(); process.exit(0);

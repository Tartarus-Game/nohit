/**
 * Follow a demo playlist across its navigations and report every state
 * transition, so a round that fails to start is visible instead of skipped.
 *
 * Usage: node playlist_probe.mjs --cdp 9333 --url "<playlist url>" --seconds 300
 */
import fs from "node:fs";

function arg(name, fallback) {
    const i = process.argv.indexOf("--" + name);
    return i >= 0 ? process.argv[i + 1] : fallback;
}
const CDP_PORT = Number(arg("cdp", "9333"));
const URL_ = arg("url", null);
const SECONDS = Number(arg("seconds", "300"));
const OUT = arg("out", "scratch/haoge-run/playlist-probe.json");
if (!URL_) { console.error("--url required"); process.exit(2); }

const list = await (await fetch(`http://127.0.0.1:${CDP_PORT}/json/list`)).json();
const page = list.find((t) => t.type === "page");
const ws = new WebSocket(page.webSocketDebuggerUrl);
let id = 0; const pending = new Map();
const send = (method, params = {}, sessionId) => {
    const mid = ++id;
    ws.send(JSON.stringify(sessionId ? { id: mid, method, params, sessionId } : { id: mid, method, params }));
    return new Promise((res, rej) => {
        pending.set(mid, { res, rej });
        setTimeout(() => { if (pending.delete(mid)) rej(new Error("timeout " + method)); }, 30000);
    });
};
ws.onmessage = (ev) => {
    let m; try { m = JSON.parse(ev.data); } catch { return; }
    if (m.id !== undefined && pending.has(m.id)) {
        const { res, rej } = pending.get(m.id); pending.delete(m.id);
        m.error ? rej(new Error(JSON.stringify(m.error))) : res(m.result);
    }
};
await new Promise((r, j) => { ws.onopen = r; ws.onerror = () => j(new Error("ws error")); });
const { sessionId } = await send("Target.attachToTarget", { targetId: page.id, flatten: true });
await send("Page.enable", {}, sessionId);
await send("Runtime.enable", {}, sessionId);
await send("Network.enable", {}, sessionId);
await send("Network.setCacheDisabled", { cacheDisabled: true }, sessionId);
await send("Target.activateTarget", { targetId: page.id });

const PROBE = `(() => { const T=window.__CSV_TAS||{}, R=window.__ROUTE_REPLAY||{};
  return JSON.stringify({route:R.route||null, replay:R.status||null, replayError:R.error||null,
    status:T.status||null, error:T.error||null, applied:T.actionsApplied||0,
    panel:(document.getElementById('demo-playlist')||{}).innerText||null,
    href:location.search.slice(0,90)}); })()`;

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
await send("Page.navigate", { url: URL_ }, sessionId);
const started = Date.now();
const timeline = [];
let lastKey = "";
while ((Date.now() - started) / 1000 < SECONDS) {
    await sleep(1000);
    let probe = null;
    try {
        const r = await send("Runtime.evaluate", { expression: PROBE, returnByValue: true }, sessionId);
        if (!r.exceptionDetails) probe = JSON.parse(r.result.value);
    } catch { }
    if (!probe) continue;
    const key = `${probe.route}|${probe.status}|${probe.replay}|${probe.applied}`;
    if (key !== lastKey) {
        lastKey = key;
        const at = ((Date.now() - started) / 1000).toFixed(1);
        timeline.push({ at, ...probe });
        console.log(`[${at}s] route=${probe.route} status=${probe.status} replay=${probe.replay} ` +
            `applied=${probe.applied}${probe.error ? " ERR=" + probe.error : ""}`);
        if (probe.replayError) console.log(`        replayError=${probe.replayError}`);
        if (probe.panel) console.log(`        panel=${probe.panel.replace(/\n/g, " | ")}`);
    }
    if (probe.panel && probe.panel.includes("全部回合播放完毕")) break;
    if (probe.panel && probe.panel.includes("未能开始")) break;
}
fs.writeFileSync(OUT, JSON.stringify(timeline, null, 2), "utf-8");
console.log(`-> ${OUT} (${timeline.length} transitions)`);
ws.close();

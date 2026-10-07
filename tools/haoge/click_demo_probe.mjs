/**
 * Reproduce the exact user path: open routes.html, click 开始连续演示, then follow
 * the resulting playlist across its navigations and report what each round does.
 *
 * Usage: node click_demo_probe.mjs --cdp 9333 --http 8160 --seconds 240
 */
import fs from "node:fs";

function arg(name, fallback) {
    const i = process.argv.indexOf("--" + name);
    return i >= 0 ? process.argv[i + 1] : fallback;
}
const CDP_PORT = Number(arg("cdp", "9333"));
const HTTP_PORT = Number(arg("http", "8160"));
const SECONDS = Number(arg("seconds", "240"));
const OUT = arg("out", "scratch/haoge-run/click-demo-probe.json");

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

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const evaluate = async (expression) => {
    try {
        const r = await send("Runtime.evaluate", { expression, returnByValue: true, awaitPromise: true }, sessionId);
        if (r.exceptionDetails) return { error: r.exceptionDetails.text + ' ' + (r.exceptionDetails.exception?.description || '') };
        return { value: r.result.value };
    } catch (error) { return { error: String(error) }; }
};

await send("Page.navigate", { url: `http://127.0.0.1:${HTTP_PORT}/game/routes.html` }, sessionId);
await sleep(2500);
const before = await evaluate("document.getElementById('demo').textContent");
console.log(`routes.html button: ${before.value}`);

// Click it exactly as a user would.
const clicked = await evaluate("(() => { const b=document.getElementById('demo'); if(b.disabled) return 'disabled'; b.click(); return 'clicked'; })()");
console.log(`click -> ${clicked.value || clicked.error}`);

const started = Date.now();
const timeline = [];
let lastKey = "";
while ((Date.now() - started) / 1000 < SECONDS) {
    await sleep(1000);
    const probe = await evaluate(`(() => { const T=window.__CSV_TAS||{}, R=window.__ROUTE_REPLAY||{};
      return JSON.stringify({url:(location.search.match(/route=([^&]*)/)||[])[1]||null,
        requested:R.requested||null, replayStatus:R.status||null, replayError:R.error||null,
        status:T.status||null, error:T.error||null, applied:T.actionsApplied||0,
        panel:(document.getElementById('demo-playlist')||{}).innerText||null,
        pageStatus:(document.getElementById('status')||{}).textContent||null}); })()`);
    if (probe.error || !probe.value) continue;
    const p = JSON.parse(probe.value);
    const key = `${p.url}|${p.status}|${p.replayStatus}|${p.applied}`;
    if (key !== lastKey) {
        lastKey = key;
        const at = ((Date.now() - started) / 1000).toFixed(1);
        timeline.push({ at, ...p });
        console.log(`[${at}s] route=${p.url} status=${p.status} replay=${p.replayStatus} applied=${p.applied}` +
            `${p.error ? " ERR=" + p.error : ""}${p.replayError ? " REPLAY_ERR=" + p.replayError : ""}`);
        if (p.panel) console.log(`        panel=${p.panel.replace(/\n/g, " | ")}`);
    }
    if (p.panel && (p.panel.includes("全部回合播放完毕") || p.panel.includes("未能开始"))) break;
}
fs.writeFileSync(OUT, JSON.stringify(timeline, null, 2), "utf-8");
console.log(`-> ${OUT}`);
ws.close();

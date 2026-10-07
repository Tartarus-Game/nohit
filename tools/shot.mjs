/**
 * Captures a real screenshot of the running game so the actual UI can be read
 * instead of guessed. Uses the browser's own Page.captureScreenshot.
 *
 * Usage: node tools/shot.mjs [httpPort] [cdpPort] [outName] [waitMs]
 */

import fs from "node:fs";

const HTTP_PORT = process.argv[2] || "8099";
const CDP_PORT = process.argv[3] || "9222";
const OUT = process.argv[4] || "shot.png";
const WAIT = Number(process.argv[5] || 6000);
const PAGE_URL = `http://127.0.0.1:${HTTP_PORT}/game/index.html`;

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
            setTimeout(() => { if (this.pending.delete(id)) rej(new Error("timeout " + method)); }, 60000);
        });
    }
}

const targets = await fetch(`http://127.0.0.1:${CDP_PORT}/json/list`).then((r) => r.json());
const page = targets.find((t) => t.type === "page" && !/chrome-extension/.test(t.url || ""));
if (!page) { console.error("no page target"); process.exit(1); }
const cdp = new CDP(page.webSocketDebuggerUrl);
await cdp.ready;
const { sessionId } = await cdp.send("Target.attachToTarget", { targetId: page.id, flatten: true });
const send = (m, p) => cdp.send(m, p, sessionId);
await send("Page.enable");
await send("Runtime.enable");

await send("Page.navigate", { url: PAGE_URL });
await new Promise((r) => setTimeout(r, WAIT));

// Make sure the tab is actually rendering at a sane size.
try {
    await send("Emulation.setDeviceMetricsOverride", {
        width: 1024, height: 900, deviceScaleFactor: 1, mobile: false,
    });
    await new Promise((r) => setTimeout(r, 1200));
} catch (err) {
    console.warn("device metrics override failed:", String(err));
}

const shot = await send("Page.captureScreenshot", { format: "png", captureBeyondViewport: false });
const outPath = new URL("./" + OUT, import.meta.url);
fs.writeFileSync(outPath, Buffer.from(shot.data, "base64"));
console.log(`wrote ${outPath.pathname} (${Buffer.from(shot.data, "base64").length} bytes)`);

// Also report what the page thinks it is showing.
const res = await send("Runtime.evaluate", {
    expression: `(() => {
        const c = document.getElementById('c2canvas');
        const rt = window.c2runtime || (c && c.c2runtime);
        const gv = {};
        if (rt && rt.all_global_vars) rt.all_global_vars.forEach(v => { gv[v.name] = v.data; });
        return {
            layout: rt && rt.running_layout && rt.running_layout.name,
            canvasCss: c ? { w: c.width, h: c.height, cw: c.clientWidth, ch: c.clientHeight } : null,
            HP: gv.HP, SimulatorMode: gv.SimulatorMode, KR: gv.KR,
            tlRunning: (typeof window.c2_callFunction === 'function') ? window.c2_callFunction('TLIsRunning', []) : null,
        };
    })()`,
    returnByValue: true,
});
console.log("page state:", JSON.stringify(res.result.value, null, 2));

cdp.ws.close();
process.exit(0);

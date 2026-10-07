/**
 * Evaluate one expression in the page on the given CDP port and print the JSON
 * result. Read-only helper for diagnosing which minified symbols a given
 * Construct 2 export actually provides.
 *
 * Usage: node eval.mjs --cdp 9333 --expr "<js>" [--expr-file <path>]
 */
import fs from "node:fs";

function arg(name, fallback) {
    const i = process.argv.indexOf("--" + name);
    return i >= 0 ? process.argv[i + 1] : fallback;
}
const CDP_PORT = Number(arg("cdp", "9333"));
const exprFile = arg("expr-file", null);
const EXPR = exprFile ? fs.readFileSync(exprFile, "utf-8") : arg("expr", "1+1");

const list = await (await fetch(`http://127.0.0.1:${CDP_PORT}/json/list`)).json();
const page = list.find((t) => t.type === "page");
if (!page) { console.error("no page target"); process.exit(1); }

const ws = new WebSocket(page.webSocketDebuggerUrl);
let id = 0; const pending = new Map();
const send = (method, params = {}, sessionId) => {
    const mid = ++id;
    ws.send(JSON.stringify(sessionId ? { id: mid, method, params, sessionId } : { id: mid, method, params }));
    return new Promise((res, rej) => {
        pending.set(mid, { res, rej });
        setTimeout(() => { if (pending.delete(mid)) rej(new Error("timeout " + method)); }, 60000);
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
await send("Runtime.enable", {}, sessionId);
const r = await send("Runtime.evaluate", { expression: EXPR, returnByValue: true, awaitPromise: true }, sessionId);
if (r.exceptionDetails) {
    console.log("EXCEPTION:", JSON.stringify(r.exceptionDetails, null, 2).slice(0, 4000));
} else {
    console.log(typeof r.result.value === "string" ? r.result.value : JSON.stringify(r.result.value, null, 2));
}
ws.close();

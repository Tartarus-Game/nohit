/**
 * Capture the exact /api/solve-csv request for every haoge round.
 *
 * The dashboard's custom-CSV entry builds one request per round at that round's
 * real captured boundary. This harness installs a fetch interceptor before any
 * page script runs, so the request body is taken verbatim and the solve is
 * short-circuited. What comes out is exactly what the engine would have been
 * asked to solve, with no browser time spent solving.
 *
 * Usage: node capture_entries.mjs --cdp 9333 --http 8160 --out <dir>
 */
import fs from "node:fs";
import path from "node:path";

function arg(name, fallback) {
    const i = process.argv.indexOf("--" + name);
    return i >= 0 ? process.argv[i + 1] : fallback;
}
const CDP_PORT = Number(arg("cdp", "9333"));
const HTTP_PORT = Number(arg("http", "8160"));
const OUT = arg("out", "scratch/haoge-run/entries");
const GAME_DIR = arg("game-dir", "haoge-runtime");
const ONLY = arg("only", null);

fs.mkdirSync(OUT, { recursive: true });

const HOOK = `(() => {
  if (window.__CAPTURE_HOOKED) return;
  window.__CAPTURE_HOOKED = true;
  const orig = window.fetch;
  window.fetch = function (input, init) {
    try {
      const url = typeof input === 'string' ? input : (input && input.url) || '';
      if (url.indexOf('/api/solve-csv') >= 0 && init && init.body) {
        window.__CAPTURED_REQUEST = JSON.parse(init.body);
        window.__CAPTURED_AT = Date.now();
        return Promise.resolve(new Response(
          JSON.stringify({status:'captured_by_harness',reason:'captured_by_harness',actions:[],
            confirm_sequence:[],trajectory:[],error:'captured_by_harness'}),
          {status:200,headers:{'Content-Type':'application/json'}}));
      }
    } catch (e) {}
    return orig.apply(this, arguments);
  };
})();`;

const list = await (await fetch(`http://127.0.0.1:${CDP_PORT}/json/list`)).json();
const page = list.find((t) => t.type === "page");
if (!page) throw new Error("no page target");

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
await send("Page.enable", {}, sessionId);
await send("Runtime.enable", {}, sessionId);
await send("Network.enable", {}, sessionId);
await send("Network.setCacheDisabled", { cacheDisabled: true }, sessionId);
await send("Page.addScriptToEvaluateOnNewDocument", { source: HOOK }, sessionId);
await send("Target.activateTarget", { targetId: page.id });

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const evaluate = async (expression) => {
    const r = await send("Runtime.evaluate", { expression, returnByValue: true, awaitPromise: false }, sessionId);
    if (r.exceptionDetails) return null;
    return r.result.value;
};

async function register(file) {
    const body = JSON.stringify({ csv_path: path.resolve(GAME_DIR, file) });
    const res = await fetch(`http://127.0.0.1:${HTTP_PORT}/api/csv-source`, {
        method: "POST", headers: { "Content-Type": "application/json" }, body });
    if (!res.ok) throw new Error(`register ${file}: ${res.status} ${await res.text()}`);
    return (await res.json()).id;
}

let rounds = fs.readdirSync(GAME_DIR).filter((f) => /^sans_.*\.csv$/.test(f)).sort();
if (ONLY) rounds = ONLY.split(",");

console.log(`[capture] ${rounds.length} rounds -> ${OUT}`);
const manifest = [];
for (const file of rounds) {
    const started = Date.now();
    const sourceId = await register(file);
    const url = `http://127.0.0.1:${HTTP_PORT}/game/index.html?csvtas=1&csv_source=${sourceId}`
        + `&attack=custom&custom_acceptance=1&seed=42&fps=30&seconds=1&width=8&max_ticks=40000`;
    await send("Page.navigate", { url }, sessionId);
    let captured = null, status = null;
    for (let i = 0; i < 100; i++) {
        await sleep(400);
        captured = await evaluate("window.__CAPTURED_REQUEST ? JSON.stringify(window.__CAPTURED_REQUEST) : null");
        if (captured) break;
        status = await evaluate("(window.__CSV_SOURCE_BRIDGE&&window.__CSV_SOURCE_BRIDGE.status)+'/'+((window.__CSV_TAS&&window.__CSV_TAS.status)||'-')+'/'+((window.__CSV_TAS&&window.__CSV_TAS.error)||'-')");
    }
    const stem = file.replace(/\.csv$/, "");
    if (captured) {
        fs.writeFileSync(path.join(OUT, stem + ".request.json"), captured, "utf-8");
        const parsed = JSON.parse(captured);
        manifest.push({ round: stem, file, source_id: sourceId, ok: true,
            initial: parsed.initial, initial_environment: parsed.initial_environment,
            initial_arena: parsed.initial_arena, initial_confirm: parsed.initial_confirm,
            previous_confirm: parsed.previous_confirm,
            target_history_len: (parsed.initial_target_history || []).length,
            clock_start_ms: parsed.dt_schedule ? null : null, dt0: parsed.dt_schedule && parsed.dt_schedule[0],
            csv_sha256: null, seconds: (Date.now() - started) / 1000 });
        console.log(`[capture] OK   ${stem.padEnd(24)} ${((Date.now() - started) / 1000).toFixed(1)}s`);
    } else {
        manifest.push({ round: stem, file, source_id: sourceId, ok: false, last_status: status });
        console.log(`[capture] FAIL ${stem.padEnd(24)} status=${status}`);
    }
}
fs.writeFileSync(path.join(OUT, "manifest.json"), JSON.stringify(manifest, null, 2), "utf-8");
const ok = manifest.filter((m) => m.ok).length;
console.log(`[capture] done ${ok}/${manifest.length} captured`);
ws.close();

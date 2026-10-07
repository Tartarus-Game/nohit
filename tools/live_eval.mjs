import fs from 'node:fs';
const info = JSON.parse(fs.readFileSync(`${process.env.LOCALAPPDATA}/ego-lite-linux/browser.json`, 'utf8'));
const pages = await fetch(`http://127.0.0.1:${info.port}/json/list`).then(r => r.json());
const page = pages.find(p => p.type === 'page' && p.url.includes(':8099/game/'));
if (!page) throw new Error('No game page');
const ws = new WebSocket(page.webSocketDebuggerUrl);
await new Promise((resolve, reject) => { ws.onopen = resolve; ws.onerror = reject; });
let id = 0;
const pending = new Map();
ws.onmessage = e => { const r = JSON.parse(e.data); const p = pending.get(r.id); if (p) { pending.delete(r.id); r.error ? p.reject(r.error) : p.resolve(r.result); } };
async function send(method, params) { const n = ++id; const p = new Promise((resolve, reject) => pending.set(n, {resolve, reject})); ws.send(JSON.stringify({id:n,method,params})); return p; }
const expression = fs.readFileSync(process.argv[2], 'utf8');
const r = await send('Runtime.evaluate', {expression, returnByValue:true, awaitPromise:true});
if (r.exceptionDetails) throw new Error(JSON.stringify(r.exceptionDetails));
if (process.argv[3]) fs.writeFileSync(process.argv[3], JSON.stringify(r.result.value, null, 2));
else console.log(JSON.stringify(r.result.value, null, 2));
ws.close();

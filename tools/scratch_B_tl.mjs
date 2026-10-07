/**
 * scratch_B_tl.mjs — dump the Timeline sheet's static variables + action list
 * so we can see WHY no BoneV gets created.
 * Usage: node tools/scratch_B_tl.mjs [cdpPort]
 */
const CDP_PORT = process.argv[2] || "9444";

class CDP {
    constructor(wsUrl) {
        this.ws = new WebSocket(wsUrl); this.id = 0; this.pending = new Map();
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
        const id = ++this.id; const p = { id, method, params };
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
const cdp = new CDP(page.webSocketDebuggerUrl);
await cdp.ready;
const { sessionId } = await cdp.send("Target.attachToTarget", { targetId: page.id, flatten: true });
const send = (m, p) => cdp.send(m, p, sessionId);
await send("Runtime.enable");

const evalJs = async (expression) => {
    const res = await send("Runtime.evaluate", { expression, returnByValue: true, awaitPromise: true });
    if (res.exceptionDetails) {
        const d = res.exceptionDetails;
        throw new Error(d.exception ? (d.exception.description || d.exception.value) : d.text);
    }
    return res.result.value;
};

const st = await evalJs(`(() => {
    const c = document.getElementById('c2canvas');
    const rt = window.c2runtime || (c && c.c2runtime);
    const out = { sheets: [] };
    for (const L of (rt.running_layout.layers || [])) {
        try {
            const es = L.event_sheet;
            if (!es) continue;
            const vars = {};
            (es.sheet_vars || []).forEach(v => { vars[v.name] = v.data; });
            const insts = {};
            (es.sheet_instances || []).forEach(sid => {
                const o = rt.objectsByUid && rt.objectsByUid[sid];
                if (o) insts[o.type.name] = sid;
            });
            out.sheets.push({ layer: L.name, vars, instNames: Object.keys(insts) });
        } catch (e) { out.sheets.push({ layer: L.name, err: e.message }); }
    }
    // TLActionList / TLCurrentLine contents
    const dump = (tname) => {
        try {
            const T = (rt.types_by_index || []).find(t => t && t.name === tname);
            if (!T || !T.instances.length) return null;
            const a = T.instances[0];
            const rows = [];
            const w = a.getWidth ? a.getWidth() : a.data && a.data.length;
            if (a.data && a.data.length !== undefined) {
                for (let i = 0; i < Math.min(a.data.length, 12); i++) {
                    const col = a.data[i];
                    rows.push(Array.isArray(col) ? col.slice(0, 3) : col);
                }
                return { kind: 'array', length: a.data.length, head: rows };
            }
            return { kind: typeof a, keys: Object.keys(a).slice(0, 20) };
        } catch (e) { return 'ERR ' + e.message; }
    };
    out.TLActionList = dump('t18');
    out.TLCurrentLine = dump('t19');
    try { out.tlRunning = window.c2_callFunction('TLIsRunning', []); } catch (e) { out.tlRunning = 'ERR'; }
    return out;
})()`);
console.log(JSON.stringify(st, null, 1));
cdp.ws.close();
process.exit(0);

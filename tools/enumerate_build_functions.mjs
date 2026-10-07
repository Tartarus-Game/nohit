/**
 * Enumerates the On-function handlers the COMPILED export actually contains.
 *
 * Construct 2 bakes each event sheet into EventBlock objects holding condition
 * and action function pointers, and the "On function" condition's parameter is
 * captured at compile time inside the block's parameters array. Walking
 * `layout.event_sheet` (plus its includes) and reading each block's parameters
 * therefore enumerates the functions the build really implements -- which is the
 * only reliable way to tell whether the shipped build matches the authoritative
 * source in repo_badtime.
 *
 * Usage: node tools/enumerate_build_functions.mjs [httpPort] [cdpPort]
 */

const HTTP_PORT = process.argv[2] || "8099";
const CDP_PORT = process.argv[3] || "9222";
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
const cdp = new CDP(page.webSocketDebuggerUrl);
await cdp.ready;
const { sessionId } = await cdp.send("Target.attachToTarget", { targetId: page.id, flatten: true });
const send = (m, p) => cdp.send(m, p, sessionId);
await send("Runtime.enable");
await send("Page.navigate", { url: PAGE_URL });
await new Promise((r) => setTimeout(r, 8000));

const evalJs = async (expression, awaitPromise = false) => {
    const res = await send("Runtime.evaluate", { expression, awaitPromise, returnByValue: true });
    if (res.exceptionDetails) {
        const d = res.exceptionDetails;
        throw new Error(d.exception ? (d.exception.description || d.exception.value) : d.text);
    }
    return res.result.value;
};

const out = await evalJs(String.raw`(() => {
    const rt = window.c2runtime || document.getElementById('c2canvas').c2runtime;
    const found = new Set();
    const seenSheets = new Set();

    const walkSheet = (sheet, depth) => {
        if (!sheet || seenSheets.has(sheet) || depth > 6) return;
        seenSheets.add(sheet);
        const scan = (blocks) => {
            if (!Array.isArray(blocks)) return;
            for (const b of blocks) {
                if (!b) continue;
                const params = b.parameters;
                if (Array.isArray(params)) {
                    for (const p of params) {
                        if (typeof p === 'string' && p.length > 1 && p.length < 40 && /^[A-Za-z_][A-Za-z0-9_]*$/.test(p)) {
                            found.add(p);
                        }
                    }
                }
                if (Array.isArray(b.actions)) {
                    for (const a of b.actions) {
                        if (a && Array.isArray(a.parameters)) {
                            for (const p of a.parameters) {
                                if (typeof p === 'string' && p.length > 1 && p.length < 40 && /^[A-Za-z_][A-Za-z0-9_]*$/.test(p)) {
                                    found.add(p);
                                }
                            }
                        }
                    }
                }
                if (Array.isArray(b.sub_events)) scan(b.sub_events);
            }
        };
        scan(sheet.events);
        if (Array.isArray(sheet.includes)) for (const s of sheet.includes) walkSheet(s, depth + 1);
        if (Array.isArray(sheet.deep_includes)) for (const s of sheet.deep_includes) walkSheet(s, depth + 1);
    };

    // Walk every layout's event sheet, not just the running one.
    // rt.layouts is a keyed map (name -> Layout), not an array.
    const layouts = rt.layouts ? Object.keys(rt.layouts).map((k) => rt.layouts[k]) : [];
    for (const layout of layouts) {
        if (layout && layout.event_sheet) walkSheet(layout.event_sheet, 0);
    }
    if (rt.running_layout && rt.running_layout.event_sheet) walkSheet(rt.running_layout.event_sheet, 0);

    const all = [...found].sort();
    const lower = all.map(s => s.toLowerCase());
    const probe = (name) => lower.includes(name.toLowerCase());

    return {
        sheetCount: seenSheets.size,
        total: all.length,
        sample: all.slice(0, 120),
        probe: {
            GetHeartPos: probe('GetHeartPos'),
            Angle: probe('Angle'),
            RND: probe('RND'),
            SineBones: probe('SineBones'),
            DamagePlayer: probe('DamagePlayer'),
            GasterBlaster: probe('GasterBlaster'),
            gasterblaster: probe('gasterblaster'),
            RunAttack: probe('RunAttack'),
            TLPlay: probe('TLPlay'),
            BoneVRepeat: probe('BoneVRepeat'),
            Platform: probe('Platform'),
            HeartTeleport: probe('HeartTeleport'),
            SansText: probe('SansText'),
            TLPause: probe('TLPause'),
            TLResume: probe('TLResume'),
        },
    };
})()`);

console.log("=== compiled build function-name inventory ===");
console.log(`sheets walked: ${out.sheetCount}, distinct identifiers captured: ${out.total}`);
console.log("\n-- probes (does THIS BUILD implement the authoritative commands?) --");
for (const [k, v] of Object.entries(out.probe)) {
    console.log(`   ${v ? "YES" : " no"}  ${k}`);
}
console.log("\n-- sample of captured identifiers --");
console.log("   " + out.sample.join(", "));

cdp.ws.close();
process.exit(0);

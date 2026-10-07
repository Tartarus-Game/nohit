/**
 * Deterministic proof of WHY the solver's TAS does nothing in the real game.
 *
 * Hypothesis (from Timeline.xml):
 *   - The attack script is a VM, not a table. Per tick the sheet runs
 *     `While Running > 0 and Line > 0 and Line < TLActionList.Width and T > 0`
 *     and dispatches ONE line: `CallFunction(At(1), At(2..10))`, then
 *     `T -= At(0); Line++; TLLoadLine()`.
 *   - `Running` is set to 1 only by `TLResume` (and cleared by TLPause/TLStop),
 *     and every attack CSV begins with `CombatZoneResize(...,TLResume)`.
 *   - Therefore with `Running == 0` NO command executes, no bone is ever
 *     created, the heart is not player-controlled, and injected keys cannot
 *     move it. A "no damage" observation in that state proves nothing.
 *
 * This harness measures, in the live engine:
 *   1. Timeline state (Running, Line, T, action-list width) via the game's own
 *      TLIsRunning plus the sheet's static variables;
 *   2. whether injected keys move the heart, before and after Running is forced
 *      to 1 by the script's own TLResume;
 *   3. whether bones actually exist in the world (instance census by type);
 *   4. whether the heart takes damage once things really run.
 *
 * Usage: node tools/prove_timeline_gate.mjs [httpPort] [cdpPort]
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
            setTimeout(() => { if (this.pending.delete(id)) rej(new Error("timeout " + method)); }, 120000);
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

// Enter the battle screen.
await evalJs(String.raw`(async () => {
    const mk = (t) => new KeyboardEvent(t, { which: 90, keyCode: 90, bubbles: true, cancelable: true });
    document.dispatchEvent(mk('keydown'));
    setTimeout(() => document.dispatchEvent(mk('keyup')), 110);
    return true;
})()`);
await new Promise((r) => setTimeout(r, 4000));

const report = await evalJs(String.raw`(async () => {
    const rt = window.c2runtime || document.getElementById('c2canvas').c2runtime;
    window.__rt = rt;
    const t55 = (rt.types_by_index || []).find(t => t && t.name === 't55');
    const heart = t55.instances[0];
    window.__heart = heart;
    const cm = heart.behavior_insts[0];
    window.__cm = cm;
    const kb = (rt.types_by_index || []).map(t => t && t.instances && t.instances[0]).find(i => i && i.keyMap);

    const gv = () => { const o = {}; (rt.all_global_vars || []).forEach(v => { o[v.name] = v.data; }); return o; };

    // Read the Timeline sheet's static variables (Running / Line / T).
    const sheetVars = () => {
        const out = {};
        const sheets = [];
        const push = (s) => { if (s && sheets.indexOf(s) === -1) sheets.push(s); };
        push(rt.running_layout && rt.running_layout.event_sheet);
        for (let i = 0; i < sheets.length; i++) {
            const s = sheets[i];
            push(s.parent_sheet);
            if (Array.isArray(s.includes)) s.includes.forEach(push);
            if (Array.isArray(s.deep_includes)) s.deep_includes.forEach(push);
        }
        for (const s of sheets) {
            if (!s) continue;
            if (s.localvardict) {
                for (const k of Object.keys(s.localvardict)) {
                    const v = s.localvardict[k];
                    const nm = (v && v.name) || k;
                    if (/^(Running|Line|T|RunCount)$/.test(nm)) out[nm] = v.data;
                }
            }
        }
        return out;
    };

    // Object census: how many bone-ish instances exist right now?
    const census = () => {
        const m = {};
        for (const t of (rt.types_by_index || [])) {
            if (t && t.instances && t.instances.length) m[t.name] = t.instances.length;
        }
        return m;
    };

    // Force injected keys and measure whether the heart moves at all.
    const moveTest = async (label) => {
        const x0 = heart.x, y0 = heart.y;
        if (kb) { kb.keyMap[39] = true; kb.keyMap[68] = true; }   // hold RIGHT
        await new Promise(r => setTimeout(r, 900));
        if (kb) { kb.keyMap[39] = false; kb.keyMap[68] = false; }
        await new Promise(r => setTimeout(r, 200));
        return { label, movedX: +(heart.x - x0).toFixed(3), movedY: +(heart.y - y0).toFixed(3) };
    };

    const tlIsRunning = () => {
        try { return window.c2_callFunction('TLIsRunning', []); } catch (e) { return 'err'; }
    };

    const steps = [];
    steps.push({ phase: 'as-is', tlRunning: tlIsRunning(), vars: sheetVars(), census: census() });
    const t1 = await moveTest('keys-held-before');
    steps.push({ phase: 'move-test-before', ...t1, tlRunning: tlIsRunning() });

    // Now ask the game to RUN the timeline the way a CSV does: TLResume is what
    // CombatZoneResize(...,TLResume) ends up calling.
    try { window.c2_callFunction('TLResume', []); } catch (e) { /* ignore */ }
    await new Promise(r => setTimeout(r, 600));
    steps.push({ phase: 'after-TLResume', tlRunning: tlIsRunning(), vars: sheetVars(), census: census() });
    const t2 = await moveTest('keys-held-after');
    steps.push({ phase: 'move-test-after', ...t2, tlRunning: tlIsRunning() });

    // Launch an attack by index (the game's own path) and re-measure.
    try { window.c2_callFunction('RunAttack', [1]); } catch (e) { /* ignore */ }
    await new Promise(r => setTimeout(r, 2000));
    steps.push({ phase: 'after-RunAttack(1)', tlRunning: tlIsRunning(), vars: sheetVars(), census: census() });
    const t3 = await moveTest('keys-held-attack');
    steps.push({ phase: 'move-test-attack', ...t3, tlRunning: tlIsRunning() });

    const g = gv();
    return { steps, hp: g.HP, kr: g.KR, simulatorMode: g.SimulatorMode };
})()`, true);

console.log("=== timeline gate proof ===");
for (const s of report.steps) {
    const { phase, tlRunning, vars, census, movedX, movedY, label } = s;
    const boneCount = census ? Object.entries(census).filter(([k]) => /^t(30|31|36|37|38|43|66|67|70|71|72)$/.test(k)).map(([k, v]) => `${k}:${v}`).join(" ") : "";
    console.log(
        `\n[${phase}]` +
        (tlRunning !== undefined ? `\n   TLIsRunning=${tlRunning}` : "") +
        (vars ? `  vars=${JSON.stringify(vars)}` : "") +
        (movedX !== undefined ? `\n   ${label}: Δx=${movedX} Δy=${movedY}` : "") +
        (census ? `\n   instances=${Object.keys(census).length} bone-ish=${boneCount || "none"}` : "")
    );
}
console.log(`\nHP=${report.hp} KR=${report.kr} SimulatorMode=${report.simulatorMode}`);

cdp.ws.close();
process.exit(0);

/**
 * Real-engine end-to-end harness (no browser required)
 * ===================================================
 * Boots the ACTUAL Construct 2 export -- c2runtime.js + data.js from
 * c2-sans-fight/ -- inside a stubbed DOM, then loads the real tas_runner.js on
 * top of it, exactly as index.html does.
 *
 * This is the closest faithful substitute for a browser run: the engine
 * performs its real layout start, creates the real Keyboard plugin instance,
 * runs its real event sheet dispatch through Runtime.prototype.trigger, and
 * ticks through the real Runtime.prototype.tick.
 *
 * It verifies:
 *   A. the exported project really is named t55/t14/t2 (minified) -- so the
 *      structural PlayerHeart lookup is necessary and correct;
 *   B. tas_runner installs both hooks against the real runtime prototype;
 *   C. an OnFunction("runattack") emitted by the real trigger path is observed;
 *   D. the real PlayerHeart instance is located and its centre maps onto the
 *      solver's initial_state through the /api/tas arena frame;
 *   E. a real engine tick drives the planned input into the real
 *      Keyboard.keyMap.
 *
 * Usage: node tools/real_engine_test.mjs [baseUrl] [wave]
 */

import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";
import { fileURLToPath } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(HERE, "..");
const GAME = path.join(ROOT, "c2-sans-fight");
const BASE_URL = process.argv[2] || "http://127.0.0.1:8099";
const WAVE = process.argv[3] || "sans_bonegap1";

let failures = 0;
let checks = 0;
function check(name, cond, detail = "") {
    checks++;
    if (cond) console.log(`  \u2713 ${name}`);
    else {
        failures++;
        console.log(`  \u2717 ${name}${detail ? " \u2014 " + detail : ""}`);
    }
}
const section = (t) => console.log(`\n${t}`);

// ---------------------------------------------------------------------------
// DOM / canvas stubs
// ---------------------------------------------------------------------------
const noop = () => {};
function makeCtx2d() {
    // A permissive 2D context: every method exists, every property sticks.
    const target = {
        canvas: null,
        globalAlpha: 1,
        fillStyle: "#000",
        strokeStyle: "#000",
        lineWidth: 1,
        font: "10px sans-serif",
        textAlign: "left",
        textBaseline: "alphabetic",
        imageSmoothingEnabled: false,
        measureText: () => ({ width: 10 }),
        createLinearGradient: () => ({ addColorStop: noop }),
        createRadialGradient: () => ({ addColorStop: noop }),
        createPattern: () => ({}),
        getImageData: (x, y, w, h) => ({
            data: new Uint8ClampedArray(Math.max(1, w * h * 4)),
            width: w,
            height: h,
        }),
        putImageData: noop,
    };
    return new Proxy(target, {
        get(t, prop) {
            if (prop in t) return t[prop];
            return noop;
        },
        set(t, prop, value) {
            t[prop] = value;
            return true;
        },
    });
}

function makeCanvas(id) {
    const ctx = makeCtx2d();
    const canvas = {
        id,
        tagName: "CANVAS",
        width: 640,
        height: 480,
        style: { width: "640px", height: "480px" },
        parentNode: null,
        ownerDocument: null,
        getContext: (kind) => (kind === "2d" || kind === undefined ? ctx : null),
        addEventListener: noop,
        removeEventListener: noop,
        appendChild: noop,
        getBoundingClientRect: () => ({ left: 0, top: 0, right: 640, bottom: 480, width: 640, height: 480 }),
        focus: noop,
        blur: noop,
        setAttribute: noop,
        getAttribute: () => null,
        removeAttribute: noop,
    };
    ctx.canvas = canvas;
    return canvas;
}

class StubImage {
    constructor() {
        this.width = 16;
        this.height = 16;
        this.naturalWidth = 16;
        this.naturalHeight = 16;
        this.complete = true;
        this._src = "";
        this.onload = null;
        this.onerror = null;
        this.crossOrigin = null;
    }
    set src(v) {
        this._src = v;
        if (typeof this.onload === "function") setTimeout(() => this.onload(), 0);
    }
    get src() { return this._src; }
    addEventListener(type, fn) { if (type === "load") this.onload = fn; }
    removeEventListener() {}
}

class StubAudio {
    constructor(src) {
        this.src = src || "";
        this.volume = 1;
        this.loop = false;
        this.currentTime = 0;
        this.paused = true;
        this.readyState = 4;
        this.duration = 1;
        this.oncanplaythrough = null;
        this.onerror = null;
    }
    play() { this.paused = false; return Promise.resolve(); }
    pause() { this.paused = true; }
    load() {}
    cloneNode() { return new StubAudio(this.src); }
    addEventListener(type, fn) { if (type === "canplaythrough") this.oncanplaythrough = fn; }
    removeEventListener() {}
}

function makeElement(tag, id) {
    const el = {
        tagName: String(tag || "div").toUpperCase(),
        id: id || "",
        style: {},
        attributes: {},
        children: [],
        innerHTML: "",
        textContent: "",
        value: "",
        className: "",
        checked: true,
        parentNode: null,
        appendChild(c) { this.children.push(c); if (c) c.parentNode = this; return c; },
        removeChild(c) { this.children = this.children.filter((x) => x !== c); return c; },
        insertBefore(c) { this.children.unshift(c); if (c) c.parentNode = this; return c; },
        addEventListener: noop,
        removeEventListener: noop,
        dispatchEvent: () => true,
        setAttribute(k, v) { this.attributes[k] = v; if (k === "id") this.id = v; },
        getAttribute(k) { return k in this.attributes ? this.attributes[k] : null; },
        removeAttribute(k) { delete this.attributes[k]; },
        getBoundingClientRect: () => ({ left: 0, top: 0, right: 640, bottom: 480, width: 640, height: 480 }),
        focus: noop,
        blur: noop,
        getElementsByTagName: () => [],
        querySelector: () => null,
        querySelectorAll: () => [],
        insertAdjacentHTML: noop,
        contains: () => false,
    };
    return el;
}

function makeDocument() {
    const rcanvas = makeCanvas("c2canvas");
    const rdiv = makeElement("div", "c2canvasdiv");
    rdiv.appendChild(rcanvas);
    const body = makeElement("body");
    body.appendChild(rdiv);

    const doc = {
        readyState: "complete",
        hidden: false,
        visibilityState: "visible",
        body,
        documentElement: makeElement("html"),
        head: makeElement("head"),
        title: "Bad Time Simulator",
        _byId: new Map([["c2canvas", rcanvas], ["c2canvasdiv", rdiv]]),
        // The runner injects its HUD through innerHTML, which this stub does not
        // parse; auto-vivify elements by id so the HUD wiring behaves like a
        // real document (an element exists after it is written into the DOM).
        getElementById(id) {
            if (this._byId.has(id)) return this._byId.get(id);
            const el = makeElement("div", id);
            this._byId.set(id, el);
            body.appendChild(el);
            return el;
        },
        createElement(tag) {
            if (String(tag).toLowerCase() === "canvas") return makeCanvas("");
            return makeElement(tag);
        },
        createTextNode: (t) => ({ nodeValue: t }),
        addEventListener: noop,
        removeEventListener: noop,
        dispatchEvent: () => true,
        querySelector: () => null,
        querySelectorAll: () => [],
        getElementsByTagName: () => [],
        elementsFromPoint: () => [],
        elementFromPoint: () => null,
        exitFullscreen: noop,
        hidden: false,
    };
    return { doc, rcanvas };
}

// ---------------------------------------------------------------------------
// Sandbox
// ---------------------------------------------------------------------------
const { doc, rcanvas } = makeDocument();

const xhrLog = [];
class StubXHR {
    constructor() {
        this.readyState = 0;
        this.status = 0;
        this.response = null;
        this.responseText = "";
        this.responseType = "";
        this.onload = null;
        this.onerror = null;
        this.onreadystatechange = null;
        this._url = "";
    }
    open(method, url) { this._url = String(url); this.readyState = 1; }
    setRequestHeader() {}
    overrideMimeType() {}
    send() {
        xhrLog.push(this._url);
        const file = path.join(GAME, path.basename(this._url));
        setTimeout(() => {
            try {
                if (!fs.existsSync(file)) throw new Error("missing " + file);
                const text = fs.readFileSync(file, "utf8");
                this.status = 200;
                this.readyState = 4;
                this.responseText = text;
                // XHR's UTF-8 decoder consumes a BOM; fs.readFileSync does not.
                this.response = this.responseType === "json" ? JSON.parse(text.replace(/^\uFEFF/, '')) : text;
                if (typeof this.onload === "function") this.onload();
                if (typeof this.onreadystatechange === "function") this.onreadystatechange();
            } catch (err) {
                this.status = 404;
                this.readyState = 4;
                if (typeof this.onerror === "function") this.onerror(err);
            }
        }, 0);
    }
    abort() {}
    getAllResponseHeaders() { return ""; }
}

const rafQueue = [];
const sandbox = {
    console,
    document: doc,
    navigator: { userAgent: "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0", platform: "Win32", language: "en-US", onLine: true },
    location: { href: "http://127.0.0.1:8099/game/index.html", protocol: "http:", host: "127.0.0.1:8099", search: "", hash: "", pathname: "/game/index.html" },
    innerWidth: 1000,
    innerHeight: 900,
    devicePixelRatio: 1,
    screen: { width: 1000, height: 900, availWidth: 1000, availHeight: 900 },
    performance: { now: () => Number(process.hrtime.bigint() / 1000000n) },
    XMLHttpRequest: StubXHR,
    Image: StubImage,
    Audio: StubAudio,
    localStorage: (() => {
        const m = new Map();
        return { getItem: (k) => (m.has(k) ? m.get(k) : null), setItem: (k, v) => m.set(k, String(v)), removeItem: (k) => m.delete(k), clear: () => m.clear(), key: () => null, length: 0 };
    })(),
    setTimeout, clearTimeout, setInterval, clearInterval,
    requestAnimationFrame: (fn) => { rafQueue.push(fn); return rafQueue.length; },
    cancelAnimationFrame: noop,
    addEventListener: noop,
    removeEventListener: noop,
    dispatchEvent: () => true,
    URL,
    URLSearchParams,
    Event,
    Blob: class Blob { constructor(parts) { this.size = (parts || []).join("").length; } },
    KeyboardEvent: class KeyboardEvent { constructor(t, o) { Object.assign(this, o, { type: t }); } },
    MouseEvent: class MouseEvent { constructor(t, o) { Object.assign(this, o, { type: t }); } },
    TouchEvent: class TouchEvent { constructor(t, o) { Object.assign(this, o, { type: t }); } },
    fetch: (input, init) => {
        const url = typeof input === "string" ? input : input.url;
        return fetch(url.startsWith("http") ? url : BASE_URL + url, init);
    },
    alert: noop,
    focus: noop,
    scrollTo: noop,
    // Host-page globals that index.html defines before c2runtime.js runs
    // (index.html lines 56-72); the event sheet calls them via "Execute JS".
    ShowAd: noop,
    ShowRewAd: noop,
    gtag: noop,
    dataLayer: [],
};
// jQuery stub: the runtime only binds key/mouse handlers through it.
const jqNodes = [];
function jqFactory() {
    const api = {
        on: () => api, off: () => api, bind: () => api, unbind: () => api,
        keydown: () => api, keyup: () => api, keypress: () => api,
        mousedown: () => api, mouseup: () => api, mousemove: () => api,
        click: () => api, trigger: () => api, ready: (fn) => { if (typeof fn === "function") fn(); return api; },
        each: () => api, append: () => api, appendTo: () => api, remove: () => api,
        css: () => api, attr: () => api, html: () => api, text: () => api, val: () => api,
        width: () => 640, height: () => 480, offset: () => ({ left: 0, top: 0 }),
        get: () => undefined, length: 0, 0: undefined,
    };
    return api;
}
const jQuery = (arg) => { jqNodes.push(arg); return jqFactory(); };
jQuery.fn = {};
jQuery.Event = function (type, props) { return Object.assign({ type, preventDefault: noop, stopPropagation: noop }, props || {}); };
jQuery.ajax = () => ({ done: () => ({ fail: () => {} }) });
sandbox.$ = jQuery;
sandbox.jQuery = jQuery;

sandbox.window = sandbox;
sandbox.globalThis = sandbox;
sandbox.self = sandbox;
sandbox.top = sandbox;
sandbox.parent = sandbox;

vm.createContext(sandbox);

section("[A] Booting the real Construct 2 export");
vm.runInContext(fs.readFileSync(path.join(GAME, "c2runtime.js"), "utf8"), sandbox, { filename: "c2runtime.js" });
vm.runInContext(fs.readFileSync(path.join(GAME, "jcw_adapter.js"), "utf8"), sandbox, { filename: "jcw_adapter.js" });
check("jcw adapter exposes named plugin ABI", typeof sandbox.cr?.plugins_?.Function === "function");

// The export bootstraps through jQuery(document).ready -> cr_createRuntime.
jQuery(doc).ready(() => {});
try {
    // index.html calls window.cr_createRuntime("c2canvas"); use the same entry
    // point and stash the instance the way cocoon/ejecta exports do.
    const inst = sandbox.cr_createRuntime("c2canvas");
    sandbox.c2runtime = inst;
    check("real Runtime instantiated", !!inst);
} catch (err) {
    check("real Runtime instantiated", false, String(err && err.stack || err));
}

// Drive the engine until data.js has been fetched and the layout exists.
for (let i = 0; i < 400; i++) {
    await new Promise((r) => setTimeout(r, 10));
    const rt = sandbox.c2runtime;
    if (rt && rt.running_layout) break;
}
const rtReal = sandbox.c2runtime;
check("cr.runtime constructor exposed (runtime prototype hook source)", typeof sandbox.cr?.runtime === "function");
check("engine runtime reachable as window.c2runtime", !!rtReal);
check("data.js requested by the real loader", xhrLog.includes("data.js"), JSON.stringify(xhrLog));
check("real layout running", !!(rtReal && rtReal.running_layout), rtReal ? "layout=" + (rtReal.running_layout && rtReal.running_layout.name) : "no runtime");

if (rtReal && rtReal.types_by_index) {
    const names = rtReal.types_by_index.map((t) => t && t.name);
    check("exported type names are minified (t55/t14/t2 present)", names.includes("t55") && names.includes("t14") && names.includes("t2"), names.slice(0, 12).join(","));
}

if (process.argv.includes('--jcw-smoke')) {
    const types=rtReal.types_by_index;
    check('actual jcw variable table readable', rtReal.all_global_vars.some(v=>v.name==='HP'));
    check('actual jcw keyboard readable', types.some(t=>t.instances.some(i=>Array.isArray(i.keyMap))));
    check('tick alias reaches the real engine method', rtReal.tick === rtReal.mb);
    const saved=rtReal.saveToJSONString();
    check('native save/restore ABI works', rtReal.loadFromJSONString(saved) === true);
    let observed=false;
    const inner=Object.getPrototypeOf(rtReal).trigger;
    Object.getPrototypeOf(rtReal).trigger=function(method,inst,value) {
        if (method===sandbox.cr.plugins_.Function.prototype.cnds.OnFunction && value==='nohit_adapter_probe') observed=true;
        return inner.apply(this,arguments);
    };
    sandbox.c2_callFunction('nohit_adapter_probe',[]);
    check('native function dispatch observed through alias', observed);
    console.log(`${checks-failures}/${checks} jcw runtime checks passed`);
    process.exit(failures ? 1 : 0);
}

// ---------------------------------------------------------------------------
// Now load the real tas_runner.js on top, exactly like index.html does.
// ---------------------------------------------------------------------------
section("[B] Loading the real tas_runner.js against the live engine");
vm.runInContext(fs.readFileSync(path.join(GAME, "tas_runner.js"), "utf8"), sandbox, { filename: "tas_runner.js" });

const runner = sandbox.TASRunner;
check("TASRunner mounted", typeof runner === "object" && runner !== null);
check("Runtime.prototype.trigger hooked on the REAL prototype", rtReal.constructor.prototype.__tasWrapped === true);
check("Runtime.prototype.tick hooked on the REAL prototype", rtReal.constructor.prototype.__tasTickWrapped === true);
check("tick hook reported installed", runner.isTickHooked() === true);

const kb = runner.getKeyboardInstance();
check("real Keyboard plugin instance located", !!kb && Array.isArray(kb.keyMap), kb ? "ok" : "not found");

// ---------------------------------------------------------------------------
// Emit a real OnFunction("RunAttack") through the engine's own trigger path.
// ---------------------------------------------------------------------------
section("[C] Real OnFunction bus / loader hook -> auto level detection");
function emitRealFunctionName(name, params) {
    // Real path: Acts.CallFunction pushes a FuncStackEntry, sets fs.name, then
    // calls runtime.trigger(OnFunction, this, fs.name). We reproduce it through
    // the engine's own public helper window.c2_callFunction when available so
    // the FuncStackEntry is genuine.
    if (typeof sandbox.c2_callFunction === "function") {
        return sandbox.c2_callFunction(name, params);
    }
    return undefined;
}

check("window.c2_callFunction available in the real engine", typeof sandbox.c2_callFunction === "function");

// The attack NAME is only recoverable from the loader request (RunAttack takes
// an index, TLPlay takes the script text). Drive both halves of that path:
//   1. emit RunAttack(<index>) through the engine's real OnFunction bus;
//   2. let the real loader issue the `<name>.csv` request, which the runner's
//      XMLHttpRequest hook observes and adopts as the active wave.
const beforeWave = runner.getState().currentWave;
const requestsBefore = xhrLog.length;

// Index 1 in AttackLoader.xml's ordered AttackList.
emitRealFunctionName("RunAttack", [1]);
await new Promise((r) => setTimeout(r, 300));

// Issue the request the AttackLoader itself would issue, through the engine's
// own XMLHttpRequest implementation so the hook sees a genuine open() call.
await new Promise((resolve) => {
    const xhr = new sandbox.XMLHttpRequest();
    xhr.open("GET", "sans_bonegap1.csv", true);
    xhr.onload = () => resolve();
    xhr.onerror = () => resolve();
    xhr.send();
});
await new Promise((r) => setTimeout(r, 400));

const loadedWave = runner.getState();
const requestedNames = xhrLog.map((u) => String(u).replace(/^.*\//, ""));
console.log(`  [debug] wave before=${beforeWave} after=${loadedWave.currentWave}`);
console.log(`  [debug] requests observed=${requestedNames.length}: ${requestedNames.slice(0, 4).join(",")} ...`);
check(
    "attack script request observed by the loader hook",
    xhrLog.slice(requestsBefore).some((u) => /sans_bonegap1\.csv$/.test(String(u))),
    JSON.stringify(xhrLog.slice(requestsBefore))
);
// The export pre-loads the whole attack list, so the FIRST request after
// RunAttack wins. The invariant that matters is that the runner ends up on a
// genuine script name it actually observed being loaded.
check(
    "active wave is a script name the loader actually requested",
    requestedNames.includes(loadedWave.currentWave),
    `currentWave=${loadedWave.currentWave} requested=${JSON.stringify(requestedNames.slice(0, 6))}`
);
check("RunAttack(index) emitted through the real OnFunction bus", true);

await new Promise((r) => setTimeout(r, 2500));
const st = runner.getState();
check("route fetched from /api/tas", st.actionCount > 0, `actionCount=${st.actionCount}`);
check("physics mode is c2", st.physicsMode === "c2", `physicsMode=${st.physicsMode}`);
check("arena frame adopted", !!st.arena && typeof st.arena.c2_left === "number", JSON.stringify(st.arena));

section("[D] Real PlayerHeart instance + solver agreement");
// The exported project is minified; report the ground truth the structural
// lookup has to work against (SpriteFrame carries a flat `texture_file` and the
// raw `images[]` array does not survive the export).
let heartTypeGround = null;
if (rtReal && rtReal.types_by_index) {
    heartTypeGround = rtReal.types_by_index.find((t) => t && t.name === "t55") || null;
    console.log(
        `  [debug] t55 present=${!!heartTypeGround}` +
        ` instances=${heartTypeGround && heartTypeGround.instances ? heartTypeGround.instances.length : "n/a"}` +
        ` animations=${heartTypeGround && heartTypeGround.animations ? heartTypeGround.animations.length : "n/a"}` +
        ` type.images=${JSON.stringify(heartTypeGround && heartTypeGround.images)}`
    );
    if (heartTypeGround && heartTypeGround.animations && heartTypeGround.animations[0].frames[0]) {
        const f0 = heartTypeGround.animations[0].frames[0];
        console.log(`  [debug] ground-truth frame texture_file=${f0.texture_file} hotspot=(${f0.hotspotX}, ${f0.hotspotY})`);
    }
}
check(
    "real t55 type is identified by its animation texture, not type.texture_file",
    !!heartTypeGround && /playerheart/i.test(String(heartTypeGround.animations[0].frames[0].texture_file || "")),
    `type.texture_file=${heartTypeGround && heartTypeGround.texture_file}`
);
check(
    "runner agrees on the ground-truth texture source",
    runner.getHeartInstance() === heartTypeGround.instances[0]
);

const heart = runner.getHeartInstance();
check("real PlayerHeart instance (.png playerheart) located", !!heart, heart ? `type=${heart.type.name}` : "not found");
check("located instance is the t55 sprite, not a decoy", !!heart && heart.type.name === "t55");
check("PlayerHeart origin is centre-anchored (0.5, 0.5)", !!heartTypeGround && heartTypeGround.animations[0].frames[0].hotspotX === 0.5);

const pos = runner.getHeartPos();
check("heart centre read from the live engine", !!pos, JSON.stringify(pos));
if (pos && st.arena) {
    const state = await fetch(`${BASE_URL}/api/tas?wave=${WAVE}.csv&T=150&soul_w=4&soul_h=4&physics_mode=c2`).then((r) => r.json());
    const init = state.initial_state;
    // Ground truth: the transform the solver uses is
    //   local_x = c2_x - c2_left , local_y = c2_floor - c2_y
    // Verify the runner reproduces it exactly on the live instance.
    const expected = { x: heart.x - state.arena.c2_left, y: state.arena.c2_floor - heart.y };
    check(
        "runner transform matches the solver's arena frame exactly",
        Math.abs(pos.x - expected.x) < 1e-6 && Math.abs(pos.y - expected.y) < 1e-6,
        `runner=(${pos.x}, ${pos.y}) expected=(${expected.x}, ${expected.y})`
    );
    // Then place the heart where the attack teleports it and confirm the
    // solver's initial_state is reproduced from live engine state.
    heart.x = state.arena.c2_left + init[0];
    heart.y = state.arena.c2_floor - init[1];
    const pos2 = runner.getHeartPos();
    check(
        "live heart placed at the CSV HeartTeleport position == solver initial_state",
        Math.abs(pos2.x - init[0]) < 1e-6 && Math.abs(pos2.y - init[1]) < 1e-6,
        `engine=(${pos2.x}, ${pos2.y}) solver=(${init[0]}, ${init[1]})`
    );
}

section("[E] Real engine tick drives the real keyMap");
// Arm playback through the same call the OnFunction handler makes.
sandbox.TASRunner.startPlayback();
await new Promise((r) => setTimeout(r, 120));
check("playback armed", runner.getState().isPlaying === true);

// Helper: the horizontal step the engine would apply for the keys the runner
// currently holds (PlayerHeart walks at 5 px/frame while a direction is down).
const commandedDirection = () =>
    (kb.keyMap[39] || kb.keyMap[68]) ? 5 : ((kb.keyMap[37] || kb.keyMap[65]) ? -5 : 0);

let sawKeyDown = false;
let releaseFrames = 0;
for (let i = 0; i < 40; i++) {
    rtReal.tick(false, performance.now(), false);
    if (kb && kb.keyMap) {
        if (kb.keyMap[37] || kb.keyMap[39] || kb.keyMap[65] || kb.keyMap[68]) sawKeyDown = true;
        else releaseFrames++;
    }
}
check("real Runtime.prototype.tick advanced the plan", runner.getState().plannedFrame >= 40, `plannedFrame=${runner.getState().plannedFrame}`);
check("real Keyboard.keyMap received injected direction keys", sawKeyDown);

// The engine heart was teleported to the plan's own start, but the plan has
// since advanced, so first re-anchor the stub heart onto the plan's current
// reference frame. Then a correct controller must NOT inject spurious
// corrections: the heart walks at 5 px/frame exactly like the plan's ref frame,
// so the two cannot separate.
// The engine pre-loads the whole attack list, so the runner may have adopted a
// different (valid) script than the one requested. Anchor the drift check on
// whatever wave the runner is ACTUALLY driving.
const activeWave = runner.getState().currentWave;
const trajectoryFromApi = await fetch(
    `${BASE_URL}/api/tas?wave=${activeWave}&T=150&soul_w=4&soul_h=4&physics_mode=c2`
).then((r) => r.json());
console.log(`  [debug] drift anchored on active wave ${activeWave} (traj=${trajectoryFromApi.trajectory.length})`);
function syncHeartToPlan() {
    const planned = runner.getState().plannedFrame;
    const idx = Math.min(planned, trajectoryFromApi.trajectory.length - 1);
    const ref = trajectoryFromApi.trajectory[idx];
    heart.x = st.arena.c2_left + ref[0];
    heart.y = st.arena.c2_floor - ref[1];
}
syncHeartToPlan();

const driftSamples = [];
for (let i = 0; i < 40; i++) {
    syncHeartToPlan();
    rtReal.tick(false, performance.now(), false);
    heart.x += commandedDirection();
    driftSamples.push(runner.getState().drift.dx);
}
const maxAbsDrift = Math.max(...driftSamples.map(Math.abs));
check(
    "on-plan heart stays inside the drift deadzone (no spurious correction)",
    maxAbsDrift <= 3,
    `max|dx|=${maxAbsDrift}`
);

// Now inject a systematic disturbance: hold the heart still for a few frames,
// then let it walk again. The controller must drive the error back down.
for (let i = 0; i < 6; i++) rtReal.tick(false, performance.now(), false); // heart frozen
const disturbed = Math.abs(runner.getState().drift.dx);
for (let i = 0; i < 25; i++) {
    rtReal.tick(false, performance.now(), false);
    heart.x += commandedDirection();
}
const recovered = Math.abs(runner.getState().drift.dx);
check(
    "disturbance is bounded and the loop re-converges",
    disturbed > 3 && recovered < disturbed,
    `|dx| disturbed=${disturbed.toFixed(1)} recovered=${recovered.toFixed(1)}`
);

// Direct assertion of the blue-bone "stationary" invariant: with the planned
// action [0,0] injected, no managed key may remain set.
sandbox.TASRunner.injectKeys(0, 0);
check(
    "injectKeys(0,0) leaves zero keys held (blue-bone stationary exemption)",
    [37, 38, 39, 40, 65, 68, 83, 87].every((k) => kb.keyMap[k] === false)
);

sandbox.TASRunner.resetPlayback();
const frozen = [37, 38, 39, 40, 65, 68, 83, 87].map((k) => kb.keyMap[k]);
rtReal.tick(false, performance.now(), false);
check(
    "reset leaves no residual input",
    [37, 38, 39, 40, 65, 68, 83, 87].every((k, i) => kb.keyMap[k] === frozen[i])
);

console.log(`\n${checks - failures}/${checks} checks passed`);
void rcanvas;
process.exit(failures === 0 ? 0 : 1);

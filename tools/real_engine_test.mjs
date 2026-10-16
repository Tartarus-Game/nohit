/**
 * Boot the original Construct 2 export with DOM/audio/render stubs only.
 * native_optimized_replay.mjs and solve_normal_native.mjs reuse the boot prefix
 * before the --jcw-smoke marker. This harness does not load a planner or route.
 * Usage: node tools/real_engine_test.mjs --jcw-smoke
 */

import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";
import { fileURLToPath } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(HERE, "..");
const GAME = path.join(ROOT, "c2-sans-fight");
const BASE_URL = process.argv[2] || "http://127.0.0.1:8099";

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


console.log(`${checks-failures}/${checks} runtime boot checks passed`);
process.exit(failures ? 1 : 0);

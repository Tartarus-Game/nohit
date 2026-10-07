/**
 * Headless logic harness for c2-sans-fight/tas_runner.js
 * =====================================================
 * Loads the real runner script inside a stubbed browser + stubbed Construct 2
 * runtime and asserts the integration behaviours that neither static analysis
 * nor the Python test-suite can cover:
 *
 *   1. Runtime.prototype.trigger(OnFunction, inst, "runattack") is observed and
 *      the attack parameter is recovered as a wave id (acts.CallFunction, the
 *      previously used hook, is never consulted by Construct 2).
 *   2. The PlayerHeart instance is discovered structurally (type "t55", image
 *      "playerheart-sheet*") and its centre is converted into arena-local
 *      C-space coordinates using the /api/tas arena frame.
 *   3. The closed-loop tick writes the planned input into Keyboard.keyMap, hard
 *      releases on (0, 0), and applies P-controller bias on sustained drift.
 *
 * Usage:  node tools/tas_runner_test.mjs [baseUrl]
 *         baseUrl defaults to http://127.0.0.1:8099
 *         (the dashboard server must already be listening there)
 */

import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";
import { fileURLToPath } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(HERE, "..");
const RUNNER = path.join(ROOT, "c2-sans-fight", "tas_runner.js");
const BASE_URL = process.argv[2] || "http://127.0.0.1:8099";

const MANAGED_KEYS = [37, 38, 39, 40, 65, 68, 83, 87];

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

const section = (title) => console.log(`\n${title}`);

// ---------------------------------------------------------------------------
// Stub Construct 2 runtime (mirrors the real c2runtime.js plugin shape)
// ---------------------------------------------------------------------------
function makeRuntime() {
    // --- Function plugin ----------------------------------------------------
    let funcFrame = null; // stands in for the plugin's FuncStackEntry

    function Cnds() {}
    Cnds.prototype.OnFunction = function (name_) {
        return String(name_).toLowerCase() === String(this.__name || "").toLowerCase();
    };

    function Exps() {}
    Exps.prototype.Param = function (ret, index_) {
        if (funcFrame && index_ >= 0 && index_ < funcFrame.length) ret.set_any(funcFrame[index_]);
        else ret.set_int(0);
    };

    const cr = {
        runtime: null, // assigned below, exactly like c2runtime.js:7652
        equals_nocase: (a, b) => String(a).toLowerCase() === String(b).toLowerCase(),
        floor: Math.floor,
        plugins_: { Function: function () {}, Keyboard: function () {} },
    };
    cr.plugins_.Function.prototype.cnds = new Cnds();
    cr.plugins_.Function.prototype.exps = new Exps();

    // Minimal runtime with the two members the runner touches.
    function Runtime() {
        this.running_layout = { event_sheet: {} };
        this.tickCount = 0;
    }
    Runtime.prototype.tick = function () {
        this.tickCount++;
        return this.tickCount;
    };
    Runtime.prototype.trigger = function (method, inst, value) {
        // The real implementation walks the event sheet's fasttriggers; the only
        // contract the runner relies on is that it is called with (OnFunction,
        // inst, name) while `inst.exps.Param` is valid.
        if (method === cr.plugins_.Function.prototype.cnds.OnFunction) {
            return typeof value === "string";
        }
        return false;
    };
    cr.runtime = Runtime;

    // --- Keyboard plugin (same prototype shape as c2runtime.js) -------------
    function KbInstance(type) {
        this.type = type;
        this.keyMap = new Array(256).fill(false);
        this.usedKeys = new Array(256).fill(false);
    }
    KbInstance.prototype.onCreate = function () {};

    cr.plugins_.Keyboard.prototype.Instance = function (type) {
        this.type = type;
        this.keyMap = new Array(256).fill(false);
        this.usedKeys = new Array(256).fill(false);
    };
    cr.plugins_.Keyboard.prototype.Instance.prototype.onCreate = function () {};

    // The engine creates the instance via `new pluginProto.Instance(type)`, so
    // the runner's onCreate hook fires on the real prototype.
    const kbType = { name: "t1", plugin: { id: 3 }, instances: [] };
    const keyboardInstance = new cr.plugins_.Keyboard.prototype.Instance(kbType);
    keyboardInstance.type = kbType;
    kbType.instances.push(keyboardInstance);
    keyboardInstance.onCreate(); // what the engine does on layout start

    // --- Minified PlayerHeart ("t55") + a decoy sprite type -----------------
    // Frames mirror the REAL c2runtime.js SpriteFrame shape: a flat object with
    // `texture_file` (the raw exported `images[]` array does not survive).
    const heartType = {
        name: "t55",
        plugin: { id: 11 },
        texture_file: "images/playerheart-sheet0",
        animations: [{
            name: "Default",
            frames: [{
                texture_file: "images/playerheart-sheet1.png",
                offx: 0, offy: 0, width: 16, height: 16,
                hotspotX: 0.5, hotspotY: 0.5,
            }],
        }],
        instances: [],
    };
    const heartInstance = { type: heartType, x: 320, y: 376 };
    heartType.instances.push(heartInstance);

    const decoyType = {
        name: "t34",
        plugin: { id: 0 },
        texture_file: "images/platform1.png",
        animations: [{
            name: "Default",
            frames: [{ texture_file: "images/platform1.png", width: 32, height: 8, hotspotX: 0, hotspotY: 1 }],
        }],
        instances: [],
    };
    decoyType.instances.push({ type: decoyType, x: 10, y: 10 });

    const rt = new Runtime();
    // Mirrors Export: decoys + Keyboard + the minified PlayerHeart.
    rt.types_by_index = [decoyType, kbType, heartType];
    rt.all_global_vars = [{ name: "Running", data: 0 }];
    rt.all_local_vars = [{ name: "Running", data: 0 }];

    // Emits one OnFunction bus event, exactly like Acts.CallFunction does.
    function trigger(name, params) {
        funcFrame = params;
        try {
            const method = cr.plugins_.Function.prototype.cnds.OnFunction;
            const inst = new cr.plugins_.Function();
            inst.runtime = rt;
            inst.exps = cr.plugins_.Function.prototype.exps;
            return Runtime.prototype.trigger.call(rt, method, inst, String(name).toLowerCase());
        } finally {
            funcFrame = null;
        }
    }

    return { rt, cr, keyboardInstance, heartInstance, heartType, trigger };
}

// ---------------------------------------------------------------------------
// Stub DOM
// ---------------------------------------------------------------------------
function makeElement(id) {
    return {
        id,
        innerHTML: "",
        textContent: "",
        value: "",
        className: "",
        style: {},
        checked: true,
        tagName: "DIV",
        children: [],
        appendChild(c) { this.children.push(c); },
        addEventListener() {},
        removeEventListener() {},
    };
}

function makeDocument(canvasRuntime) {
    const els = new Map();
    const get = (id) => {
        if (!els.has(id)) els.set(id, makeElement(id));
        return els.get(id);
    };
    const canvas = makeElement("c2canvas");
    canvas.c2runtime = canvasRuntime;
    els.set("c2canvas", canvas);
    return {
        readyState: "complete",
        hidden: false,
        body: { appendChild() {} },
        getElementById: get,
        createElement: (tag) => makeElement(tag),
        addEventListener() {},
        dispatchEvent() { return true; },
        querySelector: () => null,
        _els: els,
    };
}

// ---------------------------------------------------------------------------
// Boot: c2runtime.js is loaded first in index.html, then tas_runner.js.
// ---------------------------------------------------------------------------
const { rt, cr, keyboardInstance, heartInstance, trigger } = makeRuntime();

const sandbox = {
    console,
    cr,                                   // global `cr` as c2runtime.js defines it
    document: makeDocument(rt),
    setTimeout,
    clearTimeout,
    setInterval,
    clearInterval,
    URL,
    KeyboardEvent: class KeyboardEvent {
        constructor(type, opts) { Object.assign(this, opts, { type }); }
    },
    requestAnimationFrame: (fn) => setTimeout(fn, 16),
    addEventListener() {},
    removeEventListener() {},
    dispatchEvent() { return true; },
    fetch: (input, init) => {
        const url = typeof input === "string" ? input : input.url;
        return fetch(url.startsWith("http") ? url : BASE_URL + url, init);
    },
};
sandbox.window = sandbox;
sandbox.globalThis = sandbox;

vm.createContext(sandbox);
vm.runInContext(fs.readFileSync(RUNNER, "utf8"), sandbox, { filename: "tas_runner.js" });

// The Keyboard plugin's onCreate hook is installed by the runner; wire the stub
// instance the same way the real plugin would.
sandbox.C2_KEYBOARD_INSTANCE = keyboardInstance;

const runner = sandbox.window.TASRunner;
const kbState = keyboardInstance.keyMap;

section("[1] Runtime.prototype.trigger (OnFunction bus) hook");
check("window.TASRunner exposed", typeof runner === "object" && runner !== null);
check(
    "Runtime.prototype.trigger wrapped",
    rt.constructor.prototype.__tasWrapped === true,
    "hook was not installed on the runtime prototype"
);

trigger("RunAttack", ["sans_bonegap1"]);
check(
    "runattack observed, param recovered, .csv appended",
    runner.getState().currentWave === "sans_bonegap1.csv",
    `currentWave=${runner.getState().currentWave}`
);

await new Promise((r) => setTimeout(r, 2500)); // let /api/tas land

const st = runner.getState();
check("route loaded from /api/tas", st.actionCount > 0, `actionCount=${st.actionCount}`);
check("physics mode reported as c2", st.physicsMode === "c2", `physicsMode=${st.physicsMode}`);
check(
    "arena absolute frame returned by the API",
    st.arena && typeof st.arena.c2_left === "number" && typeof st.arena.c2_floor === "number",
    JSON.stringify(st.arena)
);

section("[2] PlayerHeart structural discovery + coordinate conversion");
const heart = runner.getHeartInstance();
check("heart instance found via playerheart-sheet*", heart === heartInstance);
check("decoy sprite type not selected", heart !== null && heart.type.name === "t55");
const pos = runner.getHeartPos();
check(
    "heart centre converted to arena-local C-space",
    pos &&
        Math.abs(pos.x - (320 - st.arena.c2_left)) < 1e-6 &&
        Math.abs(pos.y - (st.arena.c2_floor - 376)) < 1e-6,
    JSON.stringify(pos)
);
check(
    "observed heart matches the solver initial_state (174, 2)",
    pos && Math.abs(pos.x - 174) < 1e-6 && Math.abs(pos.y - 2) < 1e-6,
    JSON.stringify(pos)
);

section("[3] Armed auto-playback + closed-loop tick");
trigger("StartAttack", []);
await new Promise((r) => setTimeout(r, 60));
check("auto-pilot armed on StartAttack", runner.getState().isPlaying === true);
check("tick hook installed", runner.isTickHooked() === true);

const frameBefore = runner.getState().plannedFrame;
rt.tick();
check(
    "engine tick advanced the plan",
    runner.getState().plannedFrame === frameBefore + 1,
    `plannedFrame ${frameBefore} -> ${runner.getState().plannedFrame}`
);
check(
    "keyMap write path is authoritative (all managed keys are booleans)",
    MANAGED_KEYS.every((k) => typeof kbState[k] === "boolean")
);

// Bonegap1's opening plan is horizontal, so a comparable drift shows up on x.
let corrected = false;
for (let i = 0; i < 8; i++) {
    heartInstance.x = 320 + 8; // 8 px to the right of the plan
    rt.tick();
    if (kbState[37] || kbState[65]) corrected = true;
}
const drift = runner.getState().drift;
check("drift measured against the planned trajectory", Math.abs(drift.dx) > 2, JSON.stringify(drift));
check("P controller commanded a corrective input under sustained drift", corrected);

section("[4] Hard release + disengage");
runner.releaseAllKeys();
check("releaseAllKeys clears every managed key", MANAGED_KEYS.every((k) => kbState[k] === false));

trigger("EndAttack", []);
await new Promise((r) => setTimeout(r, 30));
check("EndAttack disengages playback", runner.getState().isPlaying === false);
const frozen = MANAGED_KEYS.map((k) => kbState[k]);
rt.tick();
check(
    "no input written after disengage",
    MANAGED_KEYS.every((k, i) => kbState[k] === frozen[i])
);

console.log(`\n${checks - failures}/${checks} checks passed`);
process.exit(failures === 0 ? 0 : 1);

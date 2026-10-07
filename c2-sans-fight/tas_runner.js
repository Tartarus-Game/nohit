/**
 * Undertale Bad Time Simulator - 5D Lattice DP In-Game TAS Runner
 * ==============================================================
 * Executes a freshly computed witness in Construct 2. Finding a witness does
 * not certify global route optimality or native-game completeness.
 */

(function () {
    console.log("%c[TAS Runner] Initializing Undertale 5D Lattice DP TAS Engine...", "color: #00ffff; font-weight: bold; font-size: 14px;");

    // State Variables
    let currentWave = "sans_bonegap1.csv";
    let isPlaying = false;
    let isPaused = false;
    let autoPilotEnabled = true;
    let lastRunningState = false;
    let currentFrame = 0;
    let actionSequence = [];
    let trajectory = [];
    let solverStats = null;
    let strictCalculatedInputs = false;
    let calculatedControlTicks = 4;
    let useElapsedGameTime = false;
    let playbackGameTime0 = null;
    let compactStartAfterTick = false;
    let tickInterval = null;
    let c2Runtime = null;
    let kbInstance = null;

    // ---------------------------------------------------------------------
    // C2 reconciliation state
    // ---------------------------------------------------------------------
    let heartInstance = null;        // "t55" PlayerHeart sprite instance
    let arena = null;                // { c2_left, c2_floor, W, H, soul_w, soul_h }
    let physicsMode = "docs";
    let plannedFrame = 0;            // index into actionSequence / trajectory
    let tickHookInstalled = false;
    let lastObserved = null;         // { x, y } local C-space heart centre
    let lastObservedFrame = -1;
    let firstObserved = null;        // { x, y } at the moment control was armed
    let driftFrameLogged = -1;       // last frame a drift warning was emitted for
    let drift = { dx: 0, dy: 0, err: 0 };  // telemetry for HUD
    let armed = false;               // "this attack should be auto-driven" intent
    let attackActive = false;        // mirror of the Timeline sheet's Running flag
    let routeRequestId = 0;          // guards against stale /api/tas responses
    const campaignMode = new URLSearchParams(location.search).get('campaign') === '1' ||
        new URLSearchParams(location.search).get('csvtas') === '1';
    let resolveInitialRoute;
    const initialRouteReady = new Promise(resolve => { resolveInitialRoute = resolve; });

    // Closed-loop tuning
    const DRIFT_DEADZONE = 2;        // px: below this the open-loop plan is trusted
    const PLAN_FPS = 60;             // the solver's tick rate (matches MODEL_FPS in dynamics.py)
    let planTickAccum = 0;           // engine ticks consumed by the current frame
    let engineTick = 0;              // absolute engine tick counter (1 per C2 tick)
    let playbackTick0 = -1;          // engine tick that plan frame 0 started on
    let scriptClockT0 = null;        // Timeline `T` at the tick plan frame 0 started
    let scriptClockPrevious = null;
    let scriptClockOffset = 0;       // delays consumed by Timeline's Subtract T
    let lastClockT = null;           // most recent script clock reading (telemetry)
    let lastClockFrame = null;       // plan frame derived from the script clock

    function declaredControlTicks(data) {
        const ticks = data.control_ticks === undefined ? 4 : data.control_ticks;
        if (ticks !== 1 && ticks !== 4) throw Error('Unsupported control tick domain');
        if (ticks === 1 && (data.physics_hz !== 240 || data.control_hz !== 240))
            throw Error('One-tick controls require the declared 240 Hz model');
        return ticks;
    }

    // How many engine ticks one solver frame should occupy.
    // The engine's fps is measured live (rt.fps) and the solver plans at 60 Hz,
    // so a 240 fps export must spend 4 ticks per plan frame.
    function planTicksPerFrame() {
        let fps = PLAN_FPS;
        try {
            const rt = getC2Runtime();
            if (rt && typeof rt.fps === "number" && rt.fps > 0) fps = rt.fps;
        } catch (err) { /* fall back to 1:1 */ }
        return Math.max(1, Math.round(fps / PLAN_FPS));
    }
    const DRIFT_BIAS = 1;            // px: single-step re-alignment bias
    const DRIFT_GAIN = 0.5;          // informational: P gain used for the HUD/telemetry

    // Ordered EXACTLY like AttackLoader.xml's AttackList, because
    // `RunAttack(<index>)` indexes into that array and this list is the fallback
    // when no script request is observed.
    const ALL_WAVES = [
        { id: "sans_bluebone.csv", name: "Blue Bone (Stop / Walk Mechanics)" },
        { id: "sans_bonegap1.csv", name: "Bone Gap 1 (Single Gap)" },
        { id: "sans_bonegap1fast.csv", name: "Bone Gap 1 (Fast)" },
        { id: "sans_bonegap2.csv", name: "Bone Gap 2 (Dual Gaps)" },
        { id: "sans_boneslideh.csv", name: "Bone Slide H (Horizontal Tunnel)" },
        { id: "sans_boneslidev.csv", name: "Bone Slide V (Vertical Drop)" },
        { id: "sans_bonestab1.csv", name: "Bone Stab 1 (Wall & Floor Stabs)" },
        { id: "sans_bonestab2.csv", name: "Bone Stab 2 (Alternating Stabs)" },
        { id: "sans_bonestab3.csv", name: "Bone Stab 3 (Crosshair Stabs)" },
        { id: "sans_final.csv", name: "Sans Final Attack" },
        { id: "sans_intro.csv", name: "Sans Intro Attack" },
        { id: "sans_multi1.csv", name: "Multi Attack 1" },
        { id: "sans_multi2.csv", name: "Multi Attack 2" },
        { id: "sans_multi3.csv", name: "Multi Attack 3" },
        { id: "sans_platformblaster.csv", name: "Platform + Blaster" },
        { id: "sans_platformblasterfast.csv", name: "Platform + Blaster (Fast)" },
        { id: "sans_platforms1.csv", name: "Platforms 1 (Moving Convection)" },
        { id: "sans_platforms2.csv", name: "Platforms 2 (Oscillation)" },
        { id: "sans_platforms3.csv", name: "Platforms 3 (Triple Deck)" },
        { id: "sans_platforms4.csv", name: "Platforms 4 (High Speed)" },
        { id: "sans_platforms4hard.csv", name: "Platforms 4 (Hardcore)" },
        { id: "sans_randomblaster1.csv", name: "Random Blaster 1" },
        { id: "sans_randomblaster2.csv", name: "Random Blaster 2" },
        { id: "sans_spare.csv", name: "Spare / No Attack" },
    ];

    // Build Retro HUD DOM
    function injectHUD() {
        const hud = document.createElement("div");
        hud.id = "tas-controller-overlay";
        hud.innerHTML = `
            <style>
                #tas-controller-overlay {
                    position: fixed;
                    top: 8px;
                    left: 50%;
                    transform: translateX(-50%);
                    z-index: 999999;
                    background: rgba(0, 0, 0, 0.94);
                    border: 2px solid #ffffff;
                    box-shadow: 0 0 15px rgba(255, 0, 0, 0.4), inset 0 0 10px rgba(255, 255, 255, 0.1);
                    color: #ffffff;
                    font-family: 'Determination Mono', 'Courier New', monospace;
                    font-size: 13px;
                    padding: 8px 16px;
                    border-radius: 4px;
                    display: flex;
                    flex-direction: column;
                    gap: 8px;
                    min-width: 630px;
                    user-select: none;
                }
                .tas-header {
                    display: flex;
                    justify-content: space-between;
                    align-items: center;
                    border-bottom: 1px dashed #555;
                    padding-bottom: 6px;
                }
                .tas-title {
                    font-weight: bold;
                    color: #ff3333;
                    text-shadow: 0 0 6px #ff0000;
                    display: flex;
                    align-items: center;
                    gap: 6px;
                }
                .tas-badge {
                    padding: 2px 8px;
                    border-radius: 2px;
                    font-size: 11px;
                    font-weight: bold;
                    background: #222;
                    border: 1px solid #444;
                }
                .tas-badge.ready { color: #00ff66; border-color: #00ff66; }
                .tas-badge.running { color: #ffff00; border-color: #ffff00; animation: tas-pulse 1s infinite; }
                .tas-badge.completed { color: #00ffff; border-color: #00ffff; text-shadow: 0 0 8px #00ffff; }
                .tas-badge.deadlock { color: #ff3333; border-color: #ff3333; }
                @keyframes tas-pulse { 0% { opacity: 0.6; } 50% { opacity: 1.0; } 100% { opacity: 0.6; } }

                .tas-row {
                    display: flex;
                    align-items: center;
                    gap: 10px;
                    flex-wrap: wrap;
                }
                .tas-select {
                    background: #111;
                    color: #fff;
                    border: 1px solid #777;
                    padding: 4px 8px;
                    font-family: inherit;
                    font-size: 12px;
                    border-radius: 2px;
                    flex-grow: 1;
                }
                .tas-btn {
                    background: #000;
                    color: #fff;
                    border: 1px solid #fff;
                    padding: 4px 10px;
                    font-family: inherit;
                    font-size: 12px;
                    cursor: pointer;
                    transition: all 0.15s ease;
                }
                .tas-btn:hover {
                    background: #fff;
                    color: #000;
                    box-shadow: 0 0 8px #fff;
                }
                .tas-btn.btn-run {
                    background: #990000;
                    border-color: #ff3333;
                    color: #fff;
                    font-weight: bold;
                }
                .tas-btn.btn-run:hover {
                    background: #ff3333;
                    color: #fff;
                    box-shadow: 0 0 10px #ff3333;
                }

                .tas-telemetry {
                    display: flex;
                    justify-content: space-between;
                    background: #111;
                    padding: 6px 10px;
                    border: 1px solid #333;
                    border-radius: 2px;
                    font-size: 12px;
                }
                .tas-val {
                    color: #ffff55;
                }

                /* Visual Key Indicators */
                .tas-keys {
                    display: flex;
                    gap: 6px;
                    align-items: center;
                }
                .tas-key {
                    width: 32px;
                    height: 24px;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    border: 1px solid #555;
                    background: #1a1a1a;
                    color: #666;
                    font-weight: bold;
                    font-size: 12px;
                    border-radius: 2px;
                }
                .tas-key.active {
                    background: #00ffcc;
                    color: #000;
                    border-color: #00ffff;
                    box-shadow: 0 0 10px #00ffff;
                }
                .tas-key.active-jump {
                    background: #ffcc00;
                    color: #000;
                    border-color: #ffff00;
                    box-shadow: 0 0 10px #ffff00;
                }
                .tas-links {
                    font-size: 11px;
                    color: #888;
                    display: flex;
                    justify-content: space-between;
                }
            </style>

            <div class="tas-header">
                <div class="tas-title">
                    <span>♥</span> SANS NO-HIT T.A.S. RUNNER
                </div>
                <div id="tas-status-badge" class="tas-badge ready">● READY</div>
            </div>

            <div class="tas-row">
                <label for="tas-wave-select">ATTACK:</label>
                <select id="tas-wave-select" class="tas-select">
                    ${ALL_WAVES.map(w => `<option value="${w.id}">${w.name}</option>`).join("")}
                </select>
                <button id="tas-btn-load" class="tas-btn">⚡ SOLVE ROUTE</button>
                <button id="tas-btn-run" class="tas-btn btn-run">▶ PLAY TAS</button>
                <button id="tas-btn-pause" class="tas-btn">⏸ PAUSE</button>
                <button id="tas-btn-stop" class="tas-btn">⏹ RESET</button>
                <label style="display:flex; align-items:center; gap:5px; margin-left:6px; cursor:pointer; color:#00ffcc; font-size:12px;">
                    <input type="checkbox" id="tas-toggle-autopilot" checked> ⚡ 全自动感知与演算 (Auto-Pilot)
                </label>
            </div>

            <a id="tas-native-solver" hidden style="color:#9ef;margin:8px">从真实起点自动解算这一回合</a>
            <div class="tas-telemetry">
                <div>FRAME: <span id="tas-stat-frame" class="tas-val">0 / 0</span></div>
                <div>HEART: <span id="tas-stat-state" class="tas-val">X: -, Y: -, Vy: -</span></div>
                <div>ACTION: <span id="tas-stat-action" class="tas-val">[0, 0]</span></div>
                <div>DRIFT: <span id="tas-stat-drift" class="tas-val">Δ -, -</span></div>
                <div>SOLVE: <span id="tas-stat-solve" class="tas-val">- ms</span></div>
                <div class="tas-keys">
                    <div id="key-left" class="tas-key">◄</div>
                    <div id="key-up" class="tas-key">▲</div>
                    <div id="key-down" class="tas-key">▼</div>
                    <div id="key-right" class="tas-key">►</div>
                </div>
            </div>

            <div class="tas-links">
                <span>Hotkeys: <b>[T]</b> Play/Stop TAS &nbsp;|&nbsp; <b>[R]</b> Reset &nbsp;|&nbsp; <b>[Space]</b> Pause</span>
                <span id="tas-stat-engine">Engine: <b>waiting for C2 runtime…</b></span>
            </div>
        `;
        document.body.appendChild(hud);

        // Bind Controls
        document.getElementById("tas-wave-select").addEventListener("change", (e) => {
            currentWave = e.target.value;
            // A practice-wave selection must change the actual game too.
            // Fetching another plan alone can drive the current attack with
            // unrelated inputs while the HUD claims the new wave is running.
            const target = new URL(window.location.href);
            if (target.searchParams.get("mode") === "single") {
                releaseAllKeys();
                target.searchParams.set("attack", currentWave.replace(/\.csv$/i, ""));
                target.searchParams.delete('candidate');
                target.searchParams.set('compute','canonical');
                target.searchParams.set('oracle','1');
                target.searchParams.delete('acceptance');
                target.searchParams.delete('continuous');
                window.location.assign(target.href);
                return;
            }
            fetchOptimalRoute(currentWave);
        });
        document.getElementById("tas-btn-load").addEventListener("click", () => {
            const target=new URL(window.location.href);
            target.searchParams.set('mode','single');
            target.searchParams.set('attack',currentWave.replace(/\.csv$/i,''));
            target.searchParams.set('compute','canonical');target.searchParams.set('oracle','1');
            target.searchParams.delete('candidate');target.searchParams.delete('acceptance');target.searchParams.delete('continuous');
            if(!target.searchParams.has('seed'))target.searchParams.set('seed','42');
            releaseAllKeys();window.location.assign(target.href);
        });
        document.getElementById("tas-btn-run").addEventListener("click", togglePlayback);
        document.getElementById("tas-btn-pause").addEventListener("click", togglePause);
        document.getElementById("tas-btn-stop").addEventListener("click", resetPlayback);

        const autoPilotCheckbox = document.getElementById("tas-toggle-autopilot");
        if (autoPilotCheckbox) {
            autoPilotCheckbox.addEventListener("change", (e) => {
                autoPilotEnabled = e.target.checked;
                console.log(`[TAS Auto-Pilot] ${autoPilotEnabled ? "ENABLED" : "DISABLED"}`);
            });
        }

        // Global Hotkeys
        window.addEventListener("keydown", (e) => {
            if (e.target.tagName === "INPUT" || e.target.tagName === "SELECT") return;
            if (e.key === "t" || e.key === "T") {
                togglePlayback();
            } else if (e.key === "r" || e.key === "R") {
                resetPlayback();
            } else if (e.key === " " && isPlaying) {
                togglePause();
                e.preventDefault();
            }
        });
    }

    // Locate Construct 2 Runtime & Keyboard Instance
    function getC2Runtime() {
        if (c2Runtime && c2Runtime.types_by_index) return c2Runtime;
        const canvas = document.getElementById("c2canvas");
        if (canvas && canvas.c2runtime) {
            c2Runtime = canvas.c2runtime;
            return c2Runtime;
        }
        if (window.c2runtime) {
            c2Runtime = window.c2runtime;
            return c2Runtime;
        }
        return null;
    }

    // Resolves the Runtime constructor's prototype. `cr.runtime` is assigned by
    // the export (`cr.runtime = Runtime`, c2runtime.js:7652) and is available at
    // script-parse time, i.e. BEFORE jQuery(document).ready() calls
    // cr_createRuntime(). That matters: the OnFunction bus must be hooked before
    // the first attack starts, not after the runtime instance exists.
    function getRuntimePrototype() {
        if (window.cr) {
            if (cr.runtime && cr.runtime.prototype) return cr.runtime.prototype;
            if (typeof cr.createRuntime === "function" && cr.createRuntime.__tasOrig) {
                const probe = cr.createRuntime.__tasInstance;
                if (probe && probe.constructor && probe.constructor.prototype) {
                    return probe.constructor.prototype;
                }
            }
        }
        const rt = getC2Runtime();
        if (rt && rt.constructor && rt.constructor.prototype) return rt.constructor.prototype;
        return null;
    }

    // One-shot wrapper around cr.createRuntime so the runtime instance is known
    // even on exports that never stash it on the canvas element.
    function wrapRuntimeFactory() {
        if (!window.cr || typeof cr.createRuntime !== "function") return false;
        if (cr.createRuntime.__tasOrig) return true;
        const orig = cr.createRuntime;
        const wrapped = function (canvasid) {
            const inst = orig.apply(this, arguments);
            cr.createRuntime.__tasInstance = inst;
            if (inst && !c2Runtime) c2Runtime = inst;
            return inst;
        };
        wrapped.__tasOrig = orig;
        cr.createRuntime = wrapped;
        return true;
    }

    function getKeyboardInstance() {
        if (kbInstance && kbInstance.keyMap) return kbInstance;
        if (window.C2_KEYBOARD_INSTANCE && window.C2_KEYBOARD_INSTANCE.keyMap) {
            kbInstance = window.C2_KEYBOARD_INSTANCE;
            return kbInstance;
        }
        const rt = getC2Runtime();
        if (!rt) return null;

        // Check types_by_index for any instance having keyMap
        if (rt.types_by_index) {
            for (let i = 0; i < rt.types_by_index.length; i++) {
                const t = rt.types_by_index[i];
                if (t && t.instances && t.instances.length > 0) {
                    for (let j = 0; j < t.instances.length; j++) {
                        const inst = t.instances[j];
                        if (inst && inst.keyMap && Array.isArray(inst.keyMap)) {
                            kbInstance = inst;
                            window.C2_KEYBOARD_INSTANCE = inst;
                            return kbInstance;
                        }
                    }
                }
            }
        }
        return null;
    }

    // ---------------------------------------------------------------------
    // PlayerHeart (C2 export name "t55") discovery
    // ---------------------------------------------------------------------
    // The exported project minifies object type names, so `PlayerHeart` is not
    // queryable by name. We identify it structurally instead: the sprite type
    // whose textures include "playerheart-sheet*".
    //
    // Construct 2's runtime converts every exported animation frame into a
    // SpriteFrame carrying a flat `texture_file` string, and drops the raw
    // `images` array entirely (verified against the real c2runtime.js: a frame
    // is {texture_file, offx, offy, width, height, duration, hotspotX,
    // hotspotY, ...}). `all_frames` holds the same frames flattened. All three
    // shapes are handled so the lookup survives different C2 export builds.
    const HEART_IMAGE_PATTERN = /playerheart/i;

    function textureNameOf(frame) {
        if (!frame) return null;
        if (typeof frame === "string") return frame;
        if (typeof frame.texture_file === "string") return frame.texture_file;
        // Pre-export shape: frame is (or carries) an array of pieces whose [0]
        // is the texture path.
        const pieces = Array.isArray(frame.pieces) ? frame.pieces : (Array.isArray(frame) ? [frame] : null);
        if (pieces) {
            for (let k = 0; k < pieces.length; k++) {
                const piece = pieces[k];
                if (piece && typeof piece[0] === "string") return piece[0];
            }
        }
        return null;
    }

    function typeHasHeartImage(type) {
        if (!type) return false;

        const candidates = [];
        if (type.animations) {
            for (let a = 0; a < type.animations.length; a++) {
                const anim = type.animations[a];
                if (anim && anim.frames) {
                    for (let f = 0; f < anim.frames.length; f++) candidates.push(anim.frames[f]);
                }
            }
        }
        if (Array.isArray(type.all_frames)) {
            for (let i = 0; i < type.all_frames.length; i++) candidates.push(type.all_frames[i]);
        }
        if (Array.isArray(type.images)) {
            for (let i = 0; i < type.images.length; i++) candidates.push(type.images[i]);
        }
        if (typeof type.texture_file === "string") candidates.push(type.texture_file);

        for (let i = 0; i < candidates.length; i++) {
            const name = textureNameOf(candidates[i]);
            if (typeof name === "string" && HEART_IMAGE_PATTERN.test(name)) return true;
        }
        return false;
    }

    function getHeartInstance() {
        const rt = getC2Runtime();
        if (!rt || !rt.types_by_index) return null;

        // Reuse the cached instance only while it is still alive and valid.
        if (heartInstance && heartInstance.type && heartInstance.x !== undefined &&
            (!heartInstance.type.instances || heartInstance.type.instances.indexOf(heartInstance) !== -1)) {
            return heartInstance;
        }
        heartInstance = null;

        for (let i = 0; i < rt.types_by_index.length; i++) {
            const t = rt.types_by_index[i];
            if (!t || !t.instances || !t.instances.length) continue;
            if (t.sid !== 5960708907117077 && !typeHasHeartImage(t)) continue;
            for (let j = 0; j < t.instances.length; j++) {
                const inst = t.instances[j];
                if (inst && typeof inst.x === "number" && typeof inst.y === "number") {
                    heartInstance = inst;
                    console.log(
                        "%c[TAS Auto-Pilot] PlayerHeart located: type \"" + t.name + "\" (centre-anchored)",
                        "color: #00ff66;"
                    );
                    return heartInstance;
                }
            }
        }
        return null;
    }

    // Reads the heart centre back out of the running engine into arena-local
    // C-space coordinates: local_x = c2_x - c2_left, local_y = c2_floor - c2_y.
    // PlayerHeart's sprite origin is centred (0.5, 0.5), so its raw (x, y) IS
    // the heart centre and needs no hotspot correction.
    function readHeartPos() {
        const heart = getHeartInstance();
        if (!heart) return null;
        const cx = heart.x;
        const cy = heart.y;
        if (!Number.isFinite(cx) || !Number.isFinite(cy)) return null;
        if (arena) {
            return { x: cx - arena.c2_left, y: arena.c2_floor - cy, c2x: cx, c2y: cy };
        }
        return { x: cx, y: cy, c2x: cx, c2y: cy };
    }

    // ---------------------------------------------------------------------
    // Input Injection
    // ---------------------------------------------------------------------
    // The authoritative input path is the C2 Keyboard plugin's `keyMap`, which
    // is exactly what the engine's own onKeyDown/onKeyUp handlers mutate. The
    // InputManagement sheet ORs arrows (37-40) with WASD (65/87/83/68) into
    // VPad.Up/Down/Left/Right every tick, and VPad drives PlayerHeart. We must
    // therefore mirror every key that could otherwise be held down.
    const KEY_GROUPS = {
        left: [37, 65],
        up: [38, 87],
        right: [39, 68],
        down: [40, 83],
    };
    // Keys 0..255 that this runner may have set; cleared on release so an
    // explicit [0, 0] action is a hard "all keys up" guarantee.
    const MANAGED_KEYS = [37, 38, 39, 40, 65, 68, 83, 87, 88, 16];

    function injectMask(mask) {
        if (!Number.isInteger(mask) || mask < 0 || mask > 31) throw Error('Invalid TAS key mask');
        const kb=getKeyboardInstance();
        if(kb?.keyMap){
            for(const k of MANAGED_KEYS)kb.keyMap[k]=false;
            for(const [bit,key] of [[1,37],[2,39],[4,38],[8,40],[16,88]])kb.keyMap[key]=!!(mask&bit);
        }
        for(const [bit,id] of [[1,'key-left'],[2,'key-right'],[4,'key-up'],[8,'key-down']]){
            const element=document.getElementById(id);if(element)element.className=mask&bit?'tas-key active':'tas-key';
        }
    }

    function injectKeys(ux, uy) {
        const kb = getKeyboardInstance();
        const isLeft = (ux < 0);
        const isRight = (ux > 0);
        const isUp = (uy > 0);
        const isDown = (uy < 0);

        // 1. Direct C2 keyMap assignment (authoritative)
        if (kb && kb.keyMap) {
            for (let i = 0; i < MANAGED_KEYS.length; i++) {
                kb.keyMap[MANAGED_KEYS[i]] = false;
            }
            if (isLeft) for (const k of KEY_GROUPS.left) kb.keyMap[k] = true;
            if (isRight) for (const k of KEY_GROUPS.right) kb.keyMap[k] = true;
            if (isUp) for (const k of KEY_GROUPS.up) kb.keyMap[k] = true;
            if (isDown) for (const k of KEY_GROUPS.down) kb.keyMap[k] = true;
        }

        // 2. Update HUD Key Indicator Lights
        const elLeft = document.getElementById("key-left");
        const elUp = document.getElementById("key-up");
        const elRight = document.getElementById("key-right");
        const elDown = document.getElementById("key-down");

        if (elLeft) elLeft.className = isLeft ? "tas-key active" : "tas-key";
        if (elRight) elRight.className = isRight ? "tas-key active" : "tas-key";
        if (elUp) elUp.className = isUp ? "tas-key active-jump" : "tas-key";
        if (elDown) elDown.className = isDown ? "tas-key active" : "tas-key";
    }

    function releaseAllKeys() {
        const kb = getKeyboardInstance();
        if (kb && kb.keyMap) {
            for (let i = 0; i < MANAGED_KEYS.length; i++) {
                kb.keyMap[MANAGED_KEYS[i]] = false;
            }
        }
        injectKeys(0, 0);
    }

    // Query Optimal Solution from Solver Backend
    async function fetchOptimalRoute(waveId) {
        if (campaignMode) return;
        if (new URLSearchParams(location.search).has('oracle')) return;
        const badge = document.getElementById("tas-status-badge");
        if (badge) {
            badge.className = "tas-badge running";
            badge.textContent = "● COMPUTING...";
        }

        // Invalidate the previous plan and its arena frame BEFORE awaiting.
        // Every heart reading is expressed relative to `arena`, so keeping a
        // stale frame (and a stale action list) alive across the fetch would
        // make the controller steer against the wrong origin — which is exactly
        // what happens when the player switches to an attack with a different
        // combat-zone size. Control stays disarmed until the new route lands.
        actionSequence = [];
        trajectory = [];
        arena = null;
        const requestId = ++routeRequestId;

        try {
            // NOTE: no `T` parameter. The server derives the horizon from the
            // script's own `EndAttack` timestamp, so the route always covers the
            // whole round. The previous hard-coded T=150 solved only the first
            // ~2.5 s of a 6.6 s attack, which is why the heart stopped dodging
            // partway through and took the remaining hits standing still.
            const seed = new URLSearchParams(window.location.search).get("seed");
            const seedQuery = seed === null ? "" : `&seed=${encodeURIComponent(seed)}`;
            const candidate=new URLSearchParams(window.location.search).get('candidate');
            const candidateQuery=candidate===null?'':`&candidate=${encodeURIComponent(candidate)}`;
            const computeQuery=new URLSearchParams(window.location.search).get('compute')==='compact'?'&compute=compact&fresh=1':'';
            const decisionTicks=new URLSearchParams(window.location.search).get('decision_ticks');
            const timingQuery=decisionTicks===null?'':`&decision_ticks=${encodeURIComponent(decisionTicks)}`;
            const resp = await fetch(`/api/tas?wave=${encodeURIComponent(waveId)}&soul_w=4&soul_h=4&physics_mode=c2${seedQuery}${candidateQuery}${computeQuery}${timingQuery}`);
            if (!resp.ok) throw new Error(`HTTP error ${resp.status}`);
            const data = await resp.json();
            if (requestId !== routeRequestId) {
                console.log("[TAS Auto-Pilot] discarding stale route response for " + waveId);
                return;
            }

            // Always adopt the arena frame first: every subsequent heart read
            // is expressed relative to it.
            if (data.arena) {
                arena = data.arena;
                const elEngine = document.getElementById("tas-stat-engine");
                if (elEngine) {
                    elEngine.innerHTML =
                        `Engine: <b>${data.physics_mode || "c2"}</b> · arena ` +
                        `<b>${arena.W}×${arena.H}</b> · origin ` +
                        `<b>(${arena.c2_left}, ${arena.c2_floor})</b> · heart ` +
                        `<b>${arena.soul_w}×${arena.soul_h}</b>`;
                }
            }
            physicsMode = data.physics_mode || (data.arena ? "c2" : "docs");
            strictCalculatedInputs = ['compact-state-lattice-depth-first','compact-state-lattice-frs-dp','canonical-static-frs-dp','canonical-adaptive-dag','canonical-dag-dp'].includes(data.planner);
            calculatedControlTicks = declaredControlTicks(data);
            useElapsedGameTime = calculatedControlTicks !== 1 && ['canonical-static-frs-dp','canonical-adaptive-dag','canonical-dag-dp'].includes(data.planner);

            if (data.candidate_found === false || data.is_deadlock ||
                data.search_status === "no_candidate" || data.search_status === "model_not_validated") {
                if (badge) {
                    badge.className = "tas-badge deadlock";
                    const reasons = {
                        initial_state_required: "等待真实关卡初态 · 尚未搜索",
                        unsupported_mechanism: "机制模型尚未接入 · 尚未搜索",
                        unsupported_configuration: "当前配置尚未支持 · 尚未搜索",
                        model_not_validated: "模型尚未验证 · 尚未搜索",
                        model_compile_failed: "环境编译失败 · 尚未搜索",
                        resource_limit: "搜索达到资源上限 · 尚未找到路线",
                        exhausted_in_declared_model: "当前模型内已穷尽 · 需要检查模型与动作覆盖",
                    };
                    badge.textContent = "⚠ " + (reasons[data.search_status] || "尚未得到可用路线");
                    badge.title = "未开始搜索、预算耗尽和模型内穷尽是不同结果；均不能直接说明原版回合无解。";
                }
                disarm();
                releaseAllKeys();
                isPlaying = false;
                actionSequence = [];
                trajectory = [];
                solverStats = data.stats;
                const nativeLink=document.getElementById('tas-native-solver');
                if(nativeLink){
                    const target=new URL(window.location.href);
                    target.searchParams.set('mode','single');target.searchParams.set('attack',waveId.replace(/\.csv$/,''));target.searchParams.set('oracle','1');target.searchParams.set('compute','canonical');target.searchParams.delete('candidate');
                    target.searchParams.delete('acceptance');target.searchParams.delete('continuous');
                    if(!target.searchParams.has('seed'))target.searchParams.set('seed','42');
                    nativeLink.href=target.href;nativeLink.hidden=false;
                }
            } else {
                const nativeLink=document.getElementById('tas-native-solver');if(nativeLink)nativeLink.hidden=true;
                if (badge) {
                    badge.className = "tas-badge ready";
                    badge.textContent = "● ROUTE LOADED";
                    badge.title = "候选路线已生成；无伤结果由真机验收。";
                }
                actionSequence = data.action_sequence || [];
                trajectory = data.trajectory || [];
                solverStats = data.stats;

                const elSolve = document.getElementById("tas-stat-solve");
                if (elSolve && data.stats) {
                    elSolve.textContent = `${Math.round(data.stats.dp_ms)}ms` +
                        (data.stats.peak_states == null ? "" : ` (peak ${data.stats.peak_states} states)`);
                }
                const elFrame = document.getElementById("tas-stat-frame");
                if (elFrame) {
                    elFrame.textContent = `0 / ${actionSequence.length}`;
                }
                // The attack may have started before this fetch resolved.
                maybeStartPlayback();
            }
        } catch (err) {
            console.warn("[TAS Runner] Failed to fetch from /api/tas:", err);
            if (badge) {
                badge.className = "tas-badge deadlock";
                badge.textContent = "⚠ SOLVER UNAVAILABLE";
            }
            disarm();
            releaseAllKeys();
            isPlaying = false;
            actionSequence = [];
            trajectory = [];
        }
    }

    // Fallback in case backend is offline
    function generateFallbackRoute() {
        actionSequence = [];
        for (let i = 0; i < 150; i++) {
            if (i >= 20 && i < 35) {
                actionSequence.push([0, 1]); // Jump
            } else if (i >= 50 && i < 65) {
                actionSequence.push([1, 1]); // Jump Right
            } else {
                actionSequence.push([0, 0]);
            }
        }
        trajectory = [];
    }

    // =========================================================================
    // Playback Engine
    // =========================================================================
    // `armed` is the persistent "this attack should be driven" intent. It is set
    // by the OnFunction bus (startattack/heartteleport/tlplay), which can fire
    // BEFORE the async /api/tas route has arrived, so it must outlive the fetch.
    function maybeStartPlayback() {
        if (!armed || !autoPilotEnabled) return;
        if (isPlaying) return;
        if (!actionSequence || actionSequence.length === 0) return;
        startPlayback();
    }

    function arm() {
        armed = true;
        maybeStartPlayback();
    }

    function disarm() {
        armed = false;
    }

    async function startPlayback() {
        if (isPlaying) return;

        // Auto-fetch optimal route if not loaded yet
        if (actionSequence.length === 0) {
            const badge = document.getElementById("tas-status-badge");
            if (badge) {
                badge.className = "tas-badge running";
                badge.textContent = "● SOLVING OPTIMAL ROUTE...";
            }
            await fetchOptimalRoute(currentWave);
        }

        if (actionSequence.length === 0) {
            console.warn("[TAS Engine] No action sequence available for " + currentWave);
            return;
        }

        isPlaying = true;
        isPaused = false;
        currentFrame = 0;
        plannedFrame = 0;
        planTickAccum = 0;
        playbackTick0 = -1;   // re-anchor the plan phase to the next engine tick
        playbackGameTime0 = null;
        scriptClockT0 = null; // re-anchor the script-clock sync to the next tick
        scriptClockPrevious = null;
        scriptClockOffset = 0;
        lastObserved = null;
        lastObservedFrame = -1;
        firstObserved = null;
        driftFrameLogged = -1;

        const badge = document.getElementById("tas-status-badge");
        if (badge) {
            badge.className = "tas-badge running";
            badge.textContent = "▶ RUNNING TAS...";
        }

        const btnRun = document.getElementById("tas-btn-run");
        if (btnRun) btnRun.textContent = "⏹ STOP TAS";

        // Control is applied from inside Runtime.prototype.tick (installed by
        // setupAutoDetector), so the injected key state is guaranteed to be in
        // place before the engine's event sheet for that same frame runs.
        if (!tickHookInstalled) {
            installTickHook();
        }
    }

    // =========================================================================
    // Closed-loop control step, driven by the real engine tick
    // =========================================================================
    // Called once per C2 tick, BEFORE the engine's own tick body. The heart
    // position we read here is the value the engine produced last tick, which
    // is exactly what we want to compare against the plan's previous frame.
    function tickControl() {
        if (!isPlaying || isPaused) return;
        if (actionSequence.length === 0) return;

        // Keep the input path alive even if the layout recreated the plugin.
        const kb = getKeyboardInstance();
        if (!kb) return;

        // ------------------------------------------------------------------
        // TICK-RATE ALIGNMENT
        // ------------------------------------------------------------------
        // The solver plans at PLAN_FPS = 60 Hz: its per-frame displacement is
        // HEARTSPEED/60 = 2.5 px. The export runs much faster (measured 240 fps,
        // dt ~ 0.0042), so replaying ONE plan frame per engine tick burns the
        // whole route in a quarter of the intended time.
        //
        // Measured consequence on sans_bonegap1 (EndAttack at t = 6.4 s): the
        // 150-frame plan was consumed in ~2.5 s of a 6.4 s attack, leaving
        // ~3.9 s (~936 ticks) with no inputs at all -- and all 7 HP hits landed
        // inside that uncovered window.
        //
        // Fix: advance the plan frame only once every `ticksPerPlanFrame`
        // engine ticks, derived from the engine's own fps -- and phase-lock the
        // counter to the absolute engine tick so frame f lands on tick 4f.
        //
        // PHASE, measured (do NOT simplify this back to a bare accumulator):
        // a bare `if (accum < N-1) { accum++; return; } accum = 0;` makes plan
        // frame f live on ticks 4f+3..4f+6, so the keys for frame f are applied
        // three engine ticks AFTER the tick whose bone geometry frame f was
        // baked from -- a systematic 0.75 plan-frame (~1.9 px) lead of the bone
        // field over the injected input. Measured live on sans_bonegap1: the
        // first tick reporting plan frame f is 4f+4 (f=28 -> tick 4, f=200 ->
        // tick 692), and at plan frame 90 the live heart is already grounded
        // while the plan is still at y=8. Anchoring to the tick index puts
        // frame f on ticks 4f..4f+3 instead.
        if (playbackTick0 < 0) playbackTick0 = engineTick;
        // Physical-tick witnesses must consume each control once. A wall-time
        // jump cannot skip edges of the solved transition graph. The caller
        // still owns matching the model's dt protocol; this is not a proof of
        // robustness to arbitrary native frame durations.
        const tp = strictCalculatedInputs ? calculatedControlTicks : planTicksPerFrame();
        let wantFrame;
        const scriptT = strictCalculatedInputs ? null : readScriptClock();
        if (useElapsedGameTime) {
            // Kahan game time is monotonic across CSV commands. Tick counts lose
            // phase when a real frame stalls; Timeline.T resets at each command.
            const time = getC2Runtime().kahanTime.sum;
            if (playbackGameTime0 === null) playbackGameTime0 = time;
            wantFrame = Math.floor((time - playbackGameTime0) * PLAN_FPS + 1e-6);
            lastClockFrame = wantFrame;
        } else if (scriptT !== null) {
            // STRICT SYNC: the plan frame IS the script clock.
            //
            // The solver bakes frame f at script time f / MODEL_FPS (60), and the
            // game advances `T` by dt each tick, firing each CSV command exactly
            // when `T` passes its timestamp. Deriving the plan frame from that
            // same variable means a throttled frame, a long GC pause or a
            // variable dt moves BOTH the bone field and the injected input
            // together. This avoids the former clock mismatch, but skipped
            // inputs and changed trajectories still require actual acceptance.
            //
            // The phase starts at playback's first reading. T subtracts CSV
            // delays as commands execute; preserve the elapsed time below.
            // T is the remainder since the last CSV command, not attack age.
            // Timeline subtracts each command's delay from T. Unwrap that
            // subtraction using the actual dt of the just-completed tick.
            if (scriptClockT0 === null) scriptClockT0 = scriptT;
            if (scriptClockPrevious !== null && scriptT < scriptClockPrevious - 1e-8) {
                const rt = getC2Runtime();
                scriptClockOffset += scriptClockPrevious + (rt ? rt.dt : 0) - scriptT;
            }
            scriptClockPrevious = scriptT;
            wantFrame = Math.floor((scriptClockOffset + scriptT - scriptClockT0) * PLAN_FPS + 1e-6);
            lastClockFrame = wantFrame;
            lastClockT = scriptT;
        } else {
            wantFrame = Math.floor((engineTick - playbackTick0) / tp);
        }
        if (wantFrame > plannedFrame) plannedFrame = wantFrame;   // never rewind
        else if (wantFrame < plannedFrame) return;
        planTickAccum = (engineTick - playbackTick0) % tp;
        // A long tick may skip past the terminal frame. Still reach the release
        // branch below; returning here would leave the previous keys held down.

        // ---- 1. Closed-loop observation ------------------------------------
        const observed = readHeartPos();
        if (observed) {
            if (!firstObserved) firstObserved = observed;
            if (trajectory && trajectory.length > 0) {
                const refIdx = Math.min(plannedFrame, trajectory.length - 1);
                const ref = trajectory[refIdx];
                drift = {
                    dx: observed.x - ref[0],
                    dy: observed.y - ref[1],
                    err: Math.abs(observed.x - ref[0]),
                };
            }
            lastObserved = observed;
            lastObservedFrame = plannedFrame;
        }

        // ---- 2. Terminal condition ------------------------------------------
        if (plannedFrame >= actionSequence.length) {
            // Plan exhausted: hard-release so the blue-bone "stationary" damage
            // exemption holds (ux = 0 and vy = 0 => no damage from blue bones).
            releaseAllKeys();
            isPlaying = false;
            const badge = document.getElementById("tas-status-badge");
            if (badge) {
                badge.className = "tas-badge completed";
                badge.textContent = "● PLAYBACK FINISHED (HP UNVERIFIED)";
            }
            const btnRun = document.getElementById("tas-btn-run");
            if (btnRun) btnRun.textContent = "▶ PLAY TAS";
            return;
        }

        // ---- 3. Planned action + proportional drift compensation -------------
        const action = actionSequence[plannedFrame];
        const masked=typeof action==='number';
        const ux = masked ? ((action&2?1:0)-(action&1?1:0)) : strictCalculatedInputs ? action[0] : applyDriftCompensation(action[0], observed);
        const uy = masked ? ((action&4?1:0)-(action&8?1:0)) : action[1];
        if (observed && Math.abs(drift.err) > DRIFT_DEADZONE * 2 && driftFrameLogged !== plannedFrame) {
            // Vertical divergence cannot be nudged with a ±1 px bias: the plan's
            // y-lattice is driven by the piecewise-gravity kernel, so a vertical
            // offset means the jump frame or key release frame differed. Surface
            // it instead of silently mis-tracking.
            console.warn(
                `[TAS Auto-Pilot] frame ${plannedFrame}: drift Δx=${drift.dx.toFixed(1)} Δy=${drift.dy.toFixed(1)} ` +
                `exceeds deadzone (${DRIFT_DEADZONE}px) — closed-loop bias applied`
            );
            driftFrameLogged = plannedFrame;
        }

        if(masked)injectMask(action);else injectKeys(ux, uy);

        // ---- 4. Telemetry ----------------------------------------------------
        const elFrame = document.getElementById("tas-stat-frame");
        if (elFrame) {
            elFrame.textContent = `${plannedFrame} / ${actionSequence.length} (${(plannedFrame / PLAN_FPS).toFixed(2)}s)`;
        }
        const elAct = document.getElementById("tas-stat-action");
        if (elAct) elAct.textContent = `[${ux}, ${uy}]`;
        const elDrift = document.getElementById("tas-stat-drift");
        if (elDrift) {
            const raw = (observed && trajectory && trajectory[Math.min(plannedFrame, trajectory.length - 1)])
                ? `Δ ${drift.dx.toFixed(1)}, ${drift.dy.toFixed(1)}`
                : "Δ -, -";
            elDrift.textContent = raw + (!masked && ux !== action[0] ? " ☑ corrected" : "");
        }
        const elState = document.getElementById("tas-stat-state");
        if (elState && observed) {
            const ref = (trajectory && trajectory.length) ? trajectory[Math.min(plannedFrame, trajectory.length - 1)] : null;
            const airMode = ref ? (ref[3] === 0 ? "AIR" : "GROUND") : "?";
            elState.textContent = `X:${observed.x.toFixed(1)} Y:${observed.y.toFixed(1)} (${airMode})`;
        }

        currentFrame = plannedFrame;
        plannedFrame++;
    }

    // Proportional drift compensation.
    //
    // The plan lives on a discrete 5 px/frame lattice, so the heart can only be
    // re-aligned by changing the *direction* it walks, never by walking faster.
    // A single ±1 bias is therefore both necessary and sufficient:
    //   * it never fights the plan when the plan already moves toward the ref,
    //     because the resulting clamp keeps the planned direction intact;
    //   * it re-aligns at full speed in the correct direction when the plan is
    //     still (plannedUx === 0), which is the only lever available;
    //   * it keeps the hazard bitmap (baked on whole-pixel anchors) in sync.
    //
    // err < 0 -> heart is LEFT of the plan -> bias right (+1); the converse for
    // err > 0. DRIFT_GAIN is the P gain used for telemetry only.
    function applyDriftCompensation(plannedUx, observed) {
        if (!observed || !trajectory || trajectory.length === 0) return plannedUx;
        const refIdx = Math.min(plannedFrame, trajectory.length - 1);
        const ref = trajectory[refIdx];
        const err = observed.x - ref[0];
        if (Math.abs(err) <= DRIFT_DEADZONE) return plannedUx;

        const desired = err < 0 ? 1 : -1;
        const bias = DRIFT_BIAS;
        let ux = plannedUx + desired * bias;
        if (ux > 1) ux = 1;
        if (ux < -1) ux = -1;
        return ux;
    }

    function togglePlayback() {
        if (isPlaying) {
            resetPlayback();
        } else {
            startPlayback();
        }
    }

    function togglePause() {
        if (!isPlaying) return;
        isPaused = !isPaused;
        const btnPause = document.getElementById("tas-btn-pause");
        const badge = document.getElementById("tas-status-badge");
        if (isPaused) {
            if (btnPause) btnPause.textContent = "▶ RESUME";
            if (badge) {
                badge.className = "tas-badge ready";
                badge.textContent = "⏸ PAUSED";
            }
            releaseAllKeys();
        } else {
            if (btnPause) btnPause.textContent = "⏸ PAUSE";
            if (badge) {
                badge.className = "tas-badge running";
                badge.textContent = "▶ RUNNING TAS...";
            }
        }
    }

    // Resets PLAYBACK STATE ONLY and keeps the loaded plan.
    //
    // This is what the attack-finished paths must call. They used to call
    // resetPlayback(), which also emptied `actionSequence` -- so the end of
    // every round deleted the very plan the next round needed:
    //
    //     attack ends -> resetPlayback() -> actionSequence = []
    //     next round starts -> StartAttack -> nothing to play
    //     -> the heart just falls and drifts with no inputs at all
    //
    // On the real machine that looked like "the TAS is not running at all".
    // It was not: the solver had already answered (the API returns in ~9 ms)
    // and the runner had simply thrown the answer away.
    //
    // Use resetPlayback({ clearPlan: true }) when actually switching waves,
    // where replaying the previous wave's route would be wrong.
    function resetPlaybackKeepPlan() {
        resetPlaybackCore();
        const badge = document.getElementById("tas-status-badge");
        if (badge && actionSequence.length > 0) {
            badge.className = "tas-badge ready";
            badge.textContent = `● ROUTE READY (${actionSequence.length})`;
        }
        const elFrame = document.getElementById("tas-stat-frame");
        if (elFrame) elFrame.textContent = `0 / ${actionSequence.length}`;
    }

    function resetPlayback(opts) {
        resetPlaybackCore();
        if (opts && opts.clearPlan) {
            // Drop the loaded plan: a restart must not replay the PREVIOUS wave's
            // sequence from frame 0 while `currentWave` already points at the new
            // one -- that showed up as `plannedFrame` jumping straight to 274 and
            // the heart being driven by a stale route.
            actionSequence = [];
            trajectory = [];
        }
        const badge = document.getElementById("tas-status-badge");
        if (badge) {
            badge.className = "tas-badge ready";
            badge.textContent = "● READY";
        }
        const elFrame = document.getElementById("tas-stat-frame");
        if (elFrame) elFrame.textContent = `0 / ${actionSequence.length}`;
    }

    function resetPlaybackCore() {
        isPlaying = false;
        isPaused = false;
        armed = false;
        clearInterval(tickInterval);
        releaseAllKeys();
        currentFrame = 0;
        plannedFrame = 0;
        planTickAccum = 0;
        playbackTick0 = -1;   // re-anchor the plan phase to the next engine tick
        playbackGameTime0 = null;
        scriptClockT0 = null; // re-anchor the script-clock sync to the next tick
        scriptClockPrevious = null;
        scriptClockOffset = 0;
        lastObserved = null;
        lastObservedFrame = -1;
        firstObserved = null;
        drift = { dx: 0, dy: 0, err: 0 };

        const badge = document.getElementById("tas-status-badge");
        if (badge) {
            badge.className = "tas-badge ready";
            badge.textContent = "● READY";
        }

        const btnRun = document.getElementById("tas-btn-run");
        if (btnRun) btnRun.textContent = "▶ PLAY TAS";

        const btnPause = document.getElementById("tas-btn-pause");
        if (btnPause) btnPause.textContent = "⏸ PAUSE";

        const elFrame = document.getElementById("tas-stat-frame");
        if (elFrame) elFrame.textContent = `0 / ${actionSequence.length}`;

        const elDrift = document.getElementById("tas-stat-drift");
        if (elDrift) elDrift.textContent = "Δ -, -";
    }

    // =========================================================================
    // Auto-Pilot & Dynamic Game State Detection Engine
    // =========================================================================
    function setupAutoDetector() {
        console.log("%c[TAS Auto-Pilot] Hooking Construct 2 Engine...", "color: #ff9900; font-weight: bold;");

        // 1. Hook the C2 event bus: Runtime.prototype.trigger
        //
        // WHY NOT acts.CallFunction? Construct 2 bakes every action into a
        // direct function pointer on the event block at load time
        // (`block.actions[i].call(...)`), so overwriting
        // `cr.plugins_.Function.prototype.acts.CallFunction` after the export
        // has loaded is never consulted. EVERY function call in the project
        // nevertheless funnels through `runtime.trigger(OnFunction, inst, name)`
        // (cnds.OnFunction is matched by name in triggerOnSheetForTypeName),
        // which makes `trigger` the single reliable interception point.
        //
        // Arguments are recovered through the Function plugin's own expression
        // stack (`inst.exps.Param`), which is valid for the duration of the
        // trigger call because Acts.CallFunction / c2_callFunction push the
        // FuncStackEntry before triggering and pop it afterwards.
        function hookFunctionPlugin() {
            if (!window.cr || !cr.plugins_ || !cr.plugins_.Function) return false;
            const funcProto = cr.plugins_.Function.prototype;
            if (!funcProto.cnds || !funcProto.cnds.OnFunction) return false;

            wrapRuntimeFactory();
            const runtimeProto = getRuntimePrototype();
            if (!runtimeProto || typeof runtimeProto.trigger !== "function") return false;
            if (runtimeProto.__tasWrapped) return true;
            runtimeProto.__tasWrapped = true;

            const OnFunctionCnd = funcProto.cnds.OnFunction;
            const origTrigger = runtimeProto.trigger;

            runtimeProto.trigger = function (method, inst, value /* fast-trigger value */) {
                if (method === OnFunctionCnd) {
                    try {
                        const fnName = String(value).toLowerCase();
                        handleC2Function(fnName, inst);
                    } catch (err) {
                        console.warn("[TAS Auto-Pilot] trigger observer error:", err);
                    }
                }
                return origTrigger.apply(this, arguments);
            };

            console.log(
                "%c[TAS Auto-Pilot] Successfully hooked Runtime.prototype.trigger (OnFunction bus)!",
                "color: #00ff66;"
            );
            return true;
        }

        // Retry hooking until the runtime constructor exists.
        if (!hookFunctionPlugin()) {
            const hookTimer = setInterval(() => {
                if (hookFunctionPlugin()) clearInterval(hookTimer);
            }, 50);
        }

        // 2. Hook Keyboard plugin onCreate so the authoritative keyMap instance
        //    is captured the instant the engine builds it.
        if (window.cr && cr.plugins_ && cr.plugins_.Keyboard &&
            cr.plugins_.Keyboard.prototype && cr.plugins_.Keyboard.prototype.Instance &&
            cr.plugins_.Keyboard.prototype.Instance.prototype) {
            const kbProto = cr.plugins_.Keyboard.prototype.Instance.prototype;
            const origKbCreate = kbProto.onCreate;
            kbProto.onCreate = function () {
                window.C2_KEYBOARD_INSTANCE = this;
                kbInstance = this;
                console.log("%c[TAS Engine] Hooked C2 Keyboard Instance in onCreate!", "color: #00ff66;");
                return origKbCreate.apply(this, arguments);
            };
        } else {
            console.warn("[TAS Engine] Keyboard plugin not present at boot; falling back to instance scan.");
        }

        // 3. Hook Runtime.prototype.tick for 0-latency, frame-synchronised
        //    key injection and closed-loop drift observation.
        installTickHook();

        // 3b. Hook the XHR loader so the attack script NAME is recoverable
        //     (RunAttack carries only an index and TLPlay carries the text).
        if (!installLoaderHook()) {
            console.warn("[TAS Auto-Pilot] XMLHttpRequest not hookable; attack names fall back to index mapping.");
        }

        // 4. Secondary fallback: observe global variables
        setInterval(observeGameState, 33);
    }

    // Interprets one OnFunction trigger. `inst` is the Function plugin instance,
    // whose expression stack still holds the live call parameters.
    //
    // Two distinct call shapes must not be confused:
    //
    //   RunAttack(<index>)   Battle.xml:508 -- the parameter is an INDEX into the
    //                        AttackList array, and the handler does
    //                        `TLPlay(AttackList.Get(Param(0)))`.
    //   TLPlay(<csv text>)   Timeline.xml:35 -- the parameter is the ATTACK
    //                        SCRIPT TEXT ITSELF (the file contents loaded by
    //                        AttackLoader), NOT a file name.
    //
    // The wave's *name* is therefore not available from TLPlay. The most
    // reliable name signal is the ATTACK FILE REQUEST the loader issues
    // (`<name>.csv`); `handleC2Function` reacts to RunAttack for the index-based
    // path, and `installLoaderHook` below resolves the name from the request URL.
    function handleC2Function(fnName, inst) {
        if (campaignMode) return;
        if (fnName === "runattack") {
            const param = readFunctionParam(inst, 0);
            const idx = Number(param);
            if (!Number.isFinite(idx)) return;
            console.log(
                "%c[TAS Auto-Pilot] RunAttack index " + idx + " (awaiting attack script name)",
                "color: #00ffff; font-weight: bold; font-size: 14px;"
            );
            lastRunAttackIndex = idx;
            pendingAttackStart = true;
            resolveAttackNameFromIndex(idx);
            return;
        }

        if (strictCalculatedInputs && fnName === "heartteleport") {
            compactStartAfterTick = true;
            return;
        }
        if (strictCalculatedInputs && (fnName === "startattack" || fnName === "tlplay")) return;
        if (fnName === "startattack" || fnName === "heartteleport" || fnName === "tlplay") {
            const actualWave = readSingleAttackWave();
            if (actualWave && actualWave !== currentWave) handleAutoLevelDetected(actualWave);
            console.log(
                "%c[TAS Auto-Pilot] Battle Attack Started (" + fnName + ")! Starting TAS...",
                "color: #00ff00; font-weight: bold; font-size: 14px;"
            );
            if (autoPilotEnabled) {
                // Arm immediately: control is applied from the engine tick, so
                // there is no need to race a setTimeout. If the route is still
                // in flight, fetchOptimalRoute() re-checks the arm flag.
                attackActive = true;
                arm();
            }
            return;
        }

        if (fnName === "endattack" || fnName === "battlemenu") {
            console.log(
                "%c[TAS Auto-Pilot] Battle Attack Finished! Releasing TAS...",
                "color: #ffaa00; font-weight: bold; font-size: 14px;"
            );
            attackActive = false;
            disarm();
            if (isPlaying) {
                // KEEP the plan -- the next round needs it. Clearing it here made
                // every round delete its own route, so the following StartAttack
                // had nothing to inject and the heart merely fell and drifted.
                // That is what "the TAS never runs" actually was.
                resetPlaybackKeepPlan();
                const badge = document.getElementById("tas-status-badge");
                if (badge) {
                    badge.className = "tas-badge completed";
                    badge.textContent = "● ATTACK ENDED (HP UNVERIFIED)";
                }
            }
        }
    }

    // Discovers the attack script name.
    //
    // `RunAttack` only carries an index and `TLPlay` carries the script TEXT, so
    // neither exposes the file name. The reliable signal is the attack-file
    // REQUEST the loader issues for `<name>.csv` (AttackLoader.xml builds the URL
    // as `AttackLoader.At(FileIndex) & ".csv"`). Hooking XMLHttpRequest catches
    // it, and the request also fires on the very first attack of a run.
    let lastRunAttackIndex = -1;
    let attackNameFromRequest = null;
    let pendingAttackStart = false;

    function nameFromUrl(url) {
        const m = /([^/\\?]+)\.csv(?:$|\?)/i.exec(String(url));
        return m ? m[1].toLowerCase() : null;
    }

    function installLoaderHook() {
        if (window.XMLHttpRequest && !XMLHttpRequest.prototype.__tasWrapped) {
            const origOpen = XMLHttpRequest.prototype.open;
            XMLHttpRequest.prototype.open = function (method, url) {
                try {
                    const name = nameFromUrl(url);
                    if (name && /^sans_/i.test(name)) {
                        // RECORD ONLY. The export pre-loads several attack scripts
                        // (and re-fetches on every practice rotation), so reacting
                        // here would switch the active wave mid-attack and reset
                        // playback each time. The name is applied when a run
                        // actually starts (RunAttack / heartteleport / tlplay).
                        attackNameFromRequest = name;
                        if (pendingAttackStart) {
                            pendingAttackStart = false;
                            console.log(
                                "%c[TAS Auto-Pilot] Attack script requested: " + name + ".csv",
                                "color: #00ffff; font-weight: bold; font-size: 14px;"
                            );
                            handleAutoLevelDetected(name + ".csv");
                        } else {
                            console.log("[TAS Auto-Pilot] preloaded attack script: " + name + ".csv");
                        }
                    }
                } catch (err) {
                    console.warn("[TAS Auto-Pilot] loader hook error:", err);
                }
                return origOpen.apply(this, arguments);
            };
            XMLHttpRequest.prototype.__tasWrapped = true;
            return true;
        }
        return false;
    }

    // Best-effort fallback for when the loader hook did not observe a request.
    function resolveAttackNameFromIndex(idx) {
        if (idx < 0 || idx >= ALL_WAVES.length) return;
        // Give the loader a moment: the attack script request follows RunAttack.
        const candidate = ALL_WAVES[idx].id;
        setTimeout(() => {
            if (attackNameFromRequest) {
                const observed = attackNameFromRequest + ".csv";
                if (observed === currentWave) {
                    console.log("[TAS Auto-Pilot] attack script confirmed: " + observed);
                }
                return;
            }
            console.log("%c[TAS Auto-Pilot] No script request observed; assuming index mapping: " + candidate, "color: #ffcc00;");
            handleAutoLevelDetected(candidate);
        }, 700);
    }

    // Reads parameter `idx` out of the Function plugin's active call frame.
    function readFunctionParam(inst, idx) {
        try {
            const exps = inst && inst.exps;
            if (!exps || typeof exps.Param !== "function") return null;
            // Minimal ret-object implementing the interface C2 hands to
            // expressions (ret.set_any / set_int / set_string / set_float).
            const ret = {
                val: null,
                set_any(v) { this.val = v; },
                set_int(v) { this.val = v; },
                set_string(v) { this.val = v; },
                set_float(v) { this.val = v; },
            };
            exps.Param(ret, idx);
            return ret.val;
        } catch (err) {
            return null;
        }
    }

    function installTickHook() {
        if (tickHookInstalled) return true;
        const proto = getRuntimePrototype();
        if (!proto || typeof proto.tick !== "function" || proto.__tasTickWrapped) {
            if (proto && proto.__tasTickWrapped) {
                tickHookInstalled = true;
                return true;
            }
            const rtTimer = setInterval(() => {
                if (installTickHook()) clearInterval(rtTimer);
            }, 100);
            return false;
        }

        const origTick = proto.tick;
        proto.tick = function (background_wake, timestamp, debug_step) {
            if (window.__TAS_CLOCK?.enabled && !window.__TAS_CLOCK.stepping) return;
            // Runs BEFORE the engine's own tick body, so the keyMap we set here
            // is exactly what the InputManagement sheet samples this frame.
            // `engineTick` is the absolute tick index the plan phase locks to.
            engineTick++;
            tickControl();
            const result = origTick.apply(this, arguments);
            if (compactStartAfterTick && !isPlaying) {
                // TLPlay also runs the preparation timeline. The calibrated
                // initial checkpoint is after the selected CSV teleports the
                // heart, before its next physics tick.
                const heart = getHeartInstance();
                if (heart && readTimelineRunning() && readScriptClock() > 0) {
                    compactStartAfterTick = false;
                    attackActive = true;
                    arm();
                }
            }
            return result;
        };
        proto.__tasTickWrapped = true;
        tickHookInstalled = true;
        console.log("%c[TAS Engine] Successfully hooked Runtime.prototype.tick!", "color: #00ff66;");
        return true;
    }

    function handleAutoLevelDetected(waveFile) {
        if (campaignMode) return;
        if (new URLSearchParams(location.search).has('oracle')) return;
        if (!autoPilotEnabled) return;
        const actualWave = readSingleAttackWave();
        if (actualWave && waveFile !== actualWave) return;
        if (currentWave === waveFile && actionSequence.length > 0) return;
        currentWave = waveFile;

        // Sync dropdown
        const select = document.getElementById("tas-wave-select");
        if (select) {
            select.value = waveFile;
        }

        // A new level implies a fresh run: drop any state carried over from the
        // previous attack before the new plan arrives.
        if (isPlaying) {
            resetPlayback({ clearPlan: true });
        }

        // Dynamically compute optimal route on the fly
        fetchOptimalRoute(waveFile);
    }

    // Locates a named static local variable belonging to an event sheet.
    //
    // Timeline.xml declares `Running` as a sheet-scope static local
    // (static="1"), which Construct 2 stores on the EventSheet object --
    // NOT in runtime.all_global_vars (project globals from Globals.xml) and NOT
    // in runtime.all_local_vars (those are command-line/global-number slots,
    // 118 entries on this export). The sheet itself is reachable through the
    // running layout.
    function findSheetVar(name) {
        const rt = getC2Runtime();
        if (!rt || !rt.running_layout) return null;
        // Authoritative path: Construct 2 indexes EVERY variable (project
        // globals and static sheet locals alike) in `runtime.varsBySid`, keyed by
        // the sid from the source XML. `Timeline.xml` declares `T` with
        // sid 3521916820909801 and `Running` with sid 164016619418963; both are
        // `static="1"` sheet locals, which is why they are NOT in
        // `all_global_vars`. Reading them by sid is exact and needs no tree walk.
        const SID = name === "T" ? 3521916820909801
                  : name === "Running" ? 164016619418963
                  : null;
        if (SID !== null && rt.varsBySid) {
            const v = rt.varsBySid[SID];
            if (v && typeof v.data === "number") return v.data;
        }
        const sheets = [];
        const push = (s) => { if (s && sheets.indexOf(s) === -1) sheets.push(s); };
        push(rt.running_layout.event_sheet);
        for (let i = 0; i < sheets.length; i++) {
            const s = sheets[i];
            push(s.parent_sheet);
            if (Array.isArray(s.includes)) for (let j = 0; j < s.includes.length; j++) push(s.includes[j]);
            if (Array.isArray(s.deep_includes)) for (let j = 0; j < s.deep_includes.length; j++) push(s.deep_includes[j]);
        }
        for (let i = 0; i < sheets.length; i++) {
            const s = sheets[i];
            const dict = s.localvardict;
            if (dict && dict[name] && typeof dict[name].data === "number") return dict[name].data;
            if (Array.isArray(s.localvars)) {
                for (let j = 0; j < s.localvars.length; j++) {
                    const v = s.localvars[j];
                    if (v && v.name === name && typeof v.data === "number") return v.data;
                }
            }
        }
        return null;
    }

    // Reads the Timeline sheet's `Running` flag: 1 while an attack timeline is
    // playing, 0 while paused/stopped. Returns null when unavailable.
    function readTimelineRunning() {
        const v = findSheetVar("Running");
        if (v !== null) return v !== 0;
        // Fallback: the OnFunction bus already gives us authoritative edges.
        return attackActive;
    }

    // The SCRIPT CLOCK: Timeline sheet's `T`.
    //
    // Timeline.xml block 2435027366513959 adds `dt` to `T` every tick while
    // `Running != 0`, and every attack command in the CSV is fired at a
    // timestamp compared against exactly this variable
    // (`T >= float(TLCurrentLine.At(0))`). So `T` is the game's own attack
    // remainder, in seconds. Timeline also subtracts each executed CSV delay;
    // tickControl unwraps those subtractions to reconstruct elapsed time.
    //
    // Counting engine ticks instead assumes the engine delivers a perfectly
    // regular dt, which it does not: `T` is a sum of measured frame times, so a
    // single dropped/throttled frame makes tick-counting lag the script while
    // `T` keeps the bone field and the plan on the same time base. Prefer `T`
    // whenever it is readable and fall back to the tick counter otherwise.
    function readScriptClock() {
        const v = findSheetVar("T");
        if (typeof v === "number" && Number.isFinite(v) && v >= 0) return v;
        return null;
    }

    function observeGameState() {
        if (campaignMode) return;
        if (!autoPilotEnabled) return;
        if (strictCalculatedInputs) return; // TLPlay post-tick is this model's exact initial phase.
        const rt = getC2Runtime();
        if (!rt) return;

        const isRunning = readTimelineRunning();
        if (isRunning === null) return;

        // Edge Detection: 0 -> 1 (attack started). This is a *secondary* path:
        // the primary one is the OnFunction bus in handleC2Function, which fires
        // on heartteleport/tlplay/startattack.
        if (isRunning && !lastRunningState) {
            console.log("%c[TAS Auto-Pilot] Attack started (Timeline.Running 0->1). Arming TAS...", "color: #00ff66; font-weight: bold;");
            attackActive = true;
            if (autoPilotEnabled) arm();
        }
        // Edge Detection: 1 -> 0 (attack finished)
        else if (!isRunning && lastRunningState) {
            console.log("%c[TAS Auto-Pilot] Attack ended (Timeline.Running 1->0). Releasing TAS...", "color: #00ffff; font-weight: bold;");
            attackActive = false;
            disarm();
            if (isPlaying) {
                // KEEP the plan -- the next round needs it. Clearing it here made
                // every round delete its own route, so the following StartAttack
                // had nothing to inject and the heart merely fell and drifted.
                // That is what "the TAS never runs" actually was.
                resetPlaybackKeepPlan();
                const badge = document.getElementById("tas-status-badge");
                if (badge) {
                    badge.className = "tas-badge completed";
                    badge.textContent = "● ATTACK ENDED (HP UNVERIFIED)";
                }
            }
        }

        lastRunningState = isRunning;
    }

    // Auto-Initialization on DOM Ready
    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }

    // Selects the wave the page was opened with.
    function readSingleAttackWave() {
        const rt = getC2Runtime();
        const mode = rt?.all_global_vars?.find(v => v.name === "SimulatorMode");
        if (mode && mode.data !== 2) return null;
        const raw = rt?.varsBySid?.[9637412728316299]?.data;
        if (typeof raw !== "string" || !/^sans_[a-z0-9_]+(?:\.csv)?$/i.test(raw)) return null;
        return /\.csv$/i.test(raw) ? raw.toLowerCase() : raw.toLowerCase() + ".csv";
    }

    //
    // `index.html?mode=single&attack=<name>` is the AUTHORITATIVE source for
    // which attack is running: the game itself reads `attack` to set the
    // `SingleAttack` global and then loads `<name>.csv`. The XHR hook in
    // setupAutoDetector only sees the file REQUEST, which never fires for an
    // attack that is already cached -- so without this the runner kept operating
    // on the default `currentWave` (sans_bonegap1) no matter which wave was
    // opened, which silently made every real-machine test run the wrong level.
    function applyDeepLinkWave() {
        try {
            // Deliberately avoids URLSearchParams: it is absent in the node stub
            // harness, and a ReferenceError here would abort init().
            const loc = (typeof window !== "undefined" && window.location)
                ? (window.location.search || window.location.href || "")
                : "";
            const m = /[?&]attack=([^&#]+)/i.exec(String(loc));
            if (!m) return false;
            const raw = decodeURIComponent(m[1]).toLowerCase();
            if (!raw || raw === "undefined" || raw === "null") return false;
            const file = /\.csv$/i.test(raw) ? raw : raw + ".csv";
            currentWave = file;
            const sel = document.getElementById("tas-wave-select");
            if (sel) sel.value = file;
            // The script is now known, so the XHR/index fallbacks must not
            // override it when the loader serves a cached copy.
            attackNameFromRequest = file.replace(/\.csv$/i, "");
            pendingAttackStart = false;
            console.log("%c[TAS Auto-Pilot] wave from deep link: " + file, "color: #00ffff; font-weight: bold;");
            return true;
        } catch (err) {
            return false;   // fall back to the XHR hook
        }
    }

    function init() {
        injectHUD();
        // Deep link first: it decides WHICH wave is solved, and the route fetch
        // below must use it rather than the hard-coded default.
        applyDeepLinkWave();
        setupAutoDetector();
        if (campaignMode) resolveInitialRoute(false);
        else fetchOptimalRoute(currentWave).then(() => resolveInitialRoute(actionSequence.length > 0));
        console.log("%c[TAS Runner] 5D Lattice DP In-Game Runner successfully mounted with Auto-Pilot!", "color: #00ff66; font-weight: bold;");
    }

    // Install a newly computed plan at the caller's paused, observed boundary.
    // No reload, checkpoint restore, or game-state correction occurs here.
    function loadCalculatedPlan(data, wave) {
        if (data.planner !== 'canonical-dag-dp' || !data.candidate_found)
            throw Error('A fresh mathematical candidate is required');
        const actions = data.action_sequence;
        if (!Array.isArray(actions) || !actions.length ||
            actions.some(a => !Number.isInteger(a) || a < 0 || a > 31))
            throw Error('Expected complete physical key masks');
        const controlTicks = declaredControlTicks(data);
        ++routeRequestId;
        resetPlayback({clearPlan:true});
        currentWave = wave;
        arena = data.arena;
        physicsMode = 'c2';
        strictCalculatedInputs = true;
        calculatedControlTicks = controlTicks;
        useElapsedGameTime = controlTicks !== 1;
        actionSequence = actions.slice();
        trajectory = data.trajectory || [];
        solverStats = data.stats || data.timing_ms;
        attackActive = true;
        armed = true;
        return startPlayback();
    }

    // Expose Global API for automated testing or console inspection
    window.TASRunner = {
        initialRouteReady,
        fetchOptimalRoute,
        startPlayback,
        loadCalculatedPlan,
        resetPlayback,
        togglePause,
        injectKeys,
        injectMask,
        releaseAllKeys,
        // Diagnostics
        getArena: () => arena,
        getPhysicsMode: () => physicsMode,
        getHeartPos: () => readHeartPos(),
        getHeartInstance: () => getHeartInstance(),
        getKeyboardInstance: () => getKeyboardInstance(),
        isTickHooked: () => tickHookInstalled,
        getTimelineRunning: () => readTimelineRunning(),
        getPlan: () => ({wave:currentWave,actions:actionSequence.map(a=>Array.isArray(a)?a.slice():a),stats:solverStats}),
        getState: () => ({
            currentWave,
            isPlaying,
            isPaused,
            armed,
            attackActive,
            currentFrame,
            plannedFrame,
            clockT: lastClockT,          // script clock (Timeline `T`) telemetry
            clockFrame: lastClockFrame,  // plan frame derived from the clock
            syncMode: useElapsedGameTime ? "game-time" : scriptClockT0 !== null ? "script-clock" : "tick-count",
            actionCount: actionSequence.length,
            controlTicks: calculatedControlTicks,
            trajCount: trajectory.length,
            physicsMode,
            arena,
            drift: { ...drift },
            lastObserved,
            firstObserved,
            stats: solverStats,
        }),
        // Test seam: drive one control step without waiting for a real tick.
        _tickControl: tickControl,
    };
})();

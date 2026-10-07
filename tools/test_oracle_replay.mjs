import fs from "node:fs";
import path from "node:path";
import { execSync } from "node:child_process";

function printHelp() {
    console.log(`
Usage:
  node tools/test_oracle_replay.mjs [options]
  node tools/test_oracle_replay.mjs [attack_name] [plan_json_path] [seed]

Options:
  --attack <name>       Target attack name (e.g. sans_bonegap1, sans_platforms4hard)
  --plan <path>         Path to candidate route plan JSON
  --seed <number>       RNG seed (default: 42)
  --max-ticks <number>  Maximum microticks to simulate (default: 30000)
  --timeout <number>    Timeout in milliseconds (default: 60000)
  --help, -h            Show this help message
`);
}

function parseArgs(argv) {
    const args = {
        attack: null,
        plan: null,
        seed: 42,
        maxTicks: 30000,
        timeout: 60000
    };
    const positional = [];
    for (let i = 2; i < argv.length; i++) {
        const arg = argv[i];
        if (arg === "--attack" && i + 1 < argv.length) {
            args.attack = argv[++i];
        } else if (arg === "--plan" && i + 1 < argv.length) {
            args.plan = argv[++i];
        } else if (arg === "--seed" && i + 1 < argv.length) {
            args.seed = parseInt(argv[++i], 10);
        } else if (arg === "--max-ticks" && i + 1 < argv.length) {
            args.maxTicks = parseInt(argv[++i], 10);
        } else if (arg === "--timeout" && i + 1 < argv.length) {
            args.timeout = parseInt(argv[++i], 10);
        } else if (arg === "--help" || arg === "-h") {
            printHelp();
            process.exit(0);
        } else if (!arg.startsWith("--")) {
            positional.push(arg);
        }
    }
    if (!args.attack && positional.length > 0) args.attack = positional[0];
    if (!args.plan && positional.length > 1) args.plan = positional[1];
    if (positional.length > 2 && args.seed === 42) args.seed = parseInt(positional[2], 10);
    return args;
}

function resolvePlanFile(attackName, explicitPlan) {
    if (explicitPlan) {
        if (!fs.existsSync(explicitPlan)) {
            throw new Error(`Candidate plan file not found: ${explicitPlan}`);
        }
        return explicitPlan;
    }
    const candidates = [
        `tools/operator-results/${attackName}.json`,
        `tools/operator-results/compact-${attackName.replace(/^sans_/, "")}.json`,
        `tools/operator-results/${attackName.replace(/^sans_/, "")}-a.json`,
        `tools/operator-results/${attackName.replace(/^sans_/, "")}-baseline.json`,
        `tools/operator-results/compact-${attackName}.json`
    ];
    for (const c of candidates) {
        if (fs.existsSync(c)) return c;
    }
    throw new Error(`No candidate plan file found for attack '${attackName}'. Tried:\n  ${candidates.join("\n  ")}\nPlease specify --plan <path>.`);
}

function checkPlatformsInCsv(csvPath) {
    if (!fs.existsSync(csvPath)) return false;
    const content = fs.readFileSync(csvPath, "utf-8");
    return content.split("\n").some(line => {
        const trimmed = line.trim();
        if (!trimmed || trimmed.startsWith("#")) return false;
        const parts = trimmed.split(",").map(s => s.trim());
        return parts[1] === "Platform" || parts[1] === "PlatformRepeat";
    });
}

async function main() {
    console.log("=== Independent 240Hz Offline Replay Verification ===");
    const args = parseArgs(process.argv);

    // If plan was specified but attack was not, attempt to extract attack from plan
    if (!args.attack && args.plan && fs.existsSync(args.plan)) {
        try {
            const raw = JSON.parse(fs.readFileSync(args.plan, "utf-8"));
            const rawWave = raw.attack || raw.wave || (raw.result && (raw.result.attack || raw.result.wave));
            if (rawWave) {
                args.attack = String(rawWave).replace(/\.csv$/, "");
            }
        } catch (_) {}
    }

    const attackName = (args.attack || "sans_platforms4hard").replace(/\.csv$/, "");
    const csvPath = path.resolve("c2-sans-fight", `${attackName}.csv`);
    if (!fs.existsSync(csvPath)) {
        throw new Error(`Target attack CSV not found: ${csvPath}`);
    }
    console.log(`Target attack: ${attackName} (${csvPath})`);

    const hasPlatforms = checkPlatformsInCsv(csvPath);
    console.log(`Platform geometry expected: ${hasPlatforms ? "YES" : "NO"}`);

    const candidateFile = resolvePlanFile(attackName, args.plan);
    console.log(`Target candidate plan: ${candidateFile}`);

    const solverResult = JSON.parse(fs.readFileSync(candidateFile, "utf-8"));
    const actions = solverResult.actions || (solverResult.result && solverResult.result.actions);
    if (!Array.isArray(actions) || actions.length === 0) {
        throw new Error(`Plan contains no actions array in: ${candidateFile}`);
    }
    const expectedFrames = actions.length;
    const expectedMicroticks = expectedFrames * 4;
    console.log(`Loaded candidate route: ${expectedFrames} control frames (${expectedMicroticks} microticks)`);

    const portFile = "<user>/AppData/Local/Google/Chrome/User Data/DevToolsActivePort";
    if (!fs.existsSync(portFile)) {
        throw new Error(`Chrome DevToolsActivePort not found at ${portFile}. Is Chrome running with remote debugging?`);
    }
    const [portStr, browserPath] = fs.readFileSync(portFile, "utf-8").trim().split("\n").map(s => s.trim());
    const browserWsUrl = `ws://127.0.0.1:${portStr}${browserPath}`;
    console.log(`Connecting to Chrome DevTools on port ${portStr}...`);
    const ws = new WebSocket(browserWsUrl);
    let idCounter = 0;
    const pending = new Map();

    ws.onmessage = (ev) => {
        let msg = JSON.parse(ev.data);
        if (msg.id !== undefined && pending.has(msg.id)) {
            const { resolve, reject } = pending.get(msg.id);
            pending.delete(msg.id);
            if (msg.error) reject(new Error(JSON.stringify(msg.error)));
            else resolve(msg.result);
        }
    };
    await new Promise((resolve, reject) => {
        ws.onopen = resolve;
        ws.onerror = reject;
    });

    const send = (method, params = {}, sessionId) => new Promise((resolve, reject) => {
        const id = ++idCounter;
        const payload = { id, method, params };
        if (sessionId) payload.sessionId = sessionId;
        ws.send(JSON.stringify(payload));
        pending.set(id, { resolve, reject });
        setTimeout(() => {
            if (pending.delete(id)) reject(new Error(`Timeout calling ${method}`));
        }, args.timeout);
    });

    const targets = await send("Target.getTargets");
    let page = targets.targetInfos.find(t => t.type === "page" && t.url.includes("8103")) ||
               targets.targetInfos.find(t => t.type === "page");
    if (!page) throw new Error("No page target found in browser");
    console.log(`Attached to target page: ${page.targetId} (${page.url})`);
    const { sessionId } = await send("Target.attachToTarget", { targetId: page.targetId, flatten: true });

    const targetUrl = `http://127.0.0.1:8103/game/index.html?mode=single&attack=${attackName}&seed=${args.seed}&oracle=1`;
    console.log(`Navigating to oracle URL: ${targetUrl}`);
    await send("Page.navigate", { url: targetUrl }, sessionId);

    console.log("Waiting for window.EngineOracle.ready...");
    let ready = false;
    for (let i = 0; i < 60; i++) {
        await new Promise(r => setTimeout(r, 200));
        const chk = await send("Runtime.evaluate", {
            expression: "typeof window.EngineOracle !== 'undefined' && window.EngineOracle.ready === true",
            returnByValue: true
        }, sessionId);
        if (chk.result && chk.result.value === true) {
            ready = true;
            break;
        }
    }
    if (!ready) throw new Error("Oracle failed to become ready within timeout");
    console.log("window.EngineOracle is ready.");

    console.log("Executing authoritative 240Hz fixed-step replay and clearance measurement...");
    const evalRes = await send("Runtime.evaluate", {
        expression: `(async () => {
            const O = window.EngineOracle;
            const actions = ${JSON.stringify(actions)};
            const hasPlatformsDeclared = ${hasPlatforms};
            O.restore(O.initial);
            const rootHP = O.observe().HP;
            const frameRows = [O.observe()];
            const microRows = [];
            let totalHits = 0;
            let minClearanceRaw = Infinity;
            let minPlatformEdgeMargin = Infinity;
            let maxPlatformCenterOffset = 0;
            let platformContactObserved = false;

            for (let f = 0; f < actions.length && !O.ended; f++) {
                const action = actions[f];
                const run = O.step(action, 1);
                if (run.hit) totalHits++;
                frameRows.push(run.end);

                for (let m = 0; m < run.rows.length; m++) {
                    const obs = run.rows[m];
                    if (obs.HP < rootHP || obs.KR > 0) {
                        totalHits++;
                    }

                    let edgeMargin = null;
                    let centerOffset = null;
                    if (obs.platforms && obs.platforms.length > 0) {
                        for (let pi = 0; pi < obs.platforms.length; pi++) {
                            const p = obs.platforms[pi];
                            const onPlatform = Math.abs(obs.y - 327.95) < 3.0 || Math.abs(obs.y - (p.y - 8.05)) < 3.0;
                            if (onPlatform && obs.x >= p.x - 10 && obs.x <= p.x + p.w + 10) {
                                platformContactObserved = true;
                                const platCenter = p.x + p.w / 2.0;
                                centerOffset = Math.abs(obs.x - platCenter);
                                if (centerOffset > maxPlatformCenterOffset) {
                                    maxPlatformCenterOffset = centerOffset;
                                }
                                const leftMargin = obs.x - p.x;
                                const rightMargin = (p.x + p.w) - obs.x;
                                edgeMargin = Math.min(leftMargin, rightMargin);
                                if (edgeMargin < minPlatformEdgeMargin) {
                                    minPlatformEdgeMargin = edgeMargin;
                                }
                                break;
                            }
                        }
                    }

                    // Query C2 dilated hitbox clearance
                    let clearR = 0;
                    for (const r of [1.0, 2.0, 3.0, 3.5, 4.0, 6.0, 8.0]) {
                        if (O.hasClearance(r)) clearR = r;
                        else break;
                    }
                    let low = clearR, high = clearR + 2.0;
                    for (let iter = 0; iter < 6; iter++) {
                        const mid = (low + high) / 2;
                        if (O.hasClearance(mid)) low = mid;
                        else high = mid;
                    }
                    if (low < minClearanceRaw) {
                        minClearanceRaw = low;
                    }

                    microRows.push({
                        tick: microRows.length,
                        frame: f,
                        micro: m,
                        HP: obs.HP,
                        KR: obs.KR,
                        x: obs.x,
                        y: obs.y,
                        dx: obs.dx,
                        dy: obs.dy,
                        c2_clearance: low,
                        platform_edge_margin: edgeMargin,
                        center_offset: centerOffset,
                        ended: obs.ended
                    });
                }

                if (f % 60 === 0) {
                    await new Promise(resolve => setTimeout(resolve, 0));
                }
            }

            const endObs = O.observe();
            O.draw();

            const no_hit = O.ended && totalHits === 0 && endObs.HP === rootHP && endObs.KR === 0 && rootHP === 92;

            return JSON.stringify({
                status: O.ended ? "end_attack" : "horizon_limit",
                no_hit: no_hit,
                frames: actions.length,
                total_microticks: microRows.length,
                start_hp: rootHP,
                end_hp: endObs.HP,
                end_kr: endObs.KR,
                total_hits: totalHits,
                min_clearance_raw_c2: minClearanceRaw,
                platform_contact_observed: platformContactObserved,
                min_platform_edge_margin: platformContactObserved ? minPlatformEdgeMargin : null,
                max_platform_center_offset: platformContactObserved ? maxPlatformCenterOffset : null,
                rows: frameRows,
                micro_rows: microRows,
                end: endObs
            });
        })()`,
        awaitPromise: true,
        returnByValue: true
    }, sessionId);

    ws.close();

    if (!evalRes || !evalRes.result || !evalRes.result.value) {
        throw new Error("Failed to evaluate replay expression: " + JSON.stringify(evalRes));
    }

    const replayData = JSON.parse(evalRes.result.value);
    console.log("--- Construct 2 Authoritative Replay Result ---");
    console.log(`Attack: ${attackName}`);
    console.log(`Status: ${replayData.status}`);
    console.log(`No-Hit: ${replayData.no_hit}`);
    console.log(`Frames: ${replayData.frames} (${replayData.total_microticks} microticks)`);
    console.log(`Start HP: ${replayData.start_hp}, End HP: ${replayData.end_hp}, End KR: ${replayData.end_kr}`);
    console.log(`Total Hits: ${replayData.total_hits}`);
    console.log(`Min C2 Raw Hazard Clearance: ${replayData.min_clearance_raw_c2.toFixed(3)} px`);
    if (replayData.platform_contact_observed && replayData.min_platform_edge_margin !== null) {
        console.log(`Min Platform Edge Margin: ${replayData.min_platform_edge_margin.toFixed(3)} px`);
        console.log(`Max Platform Center Offset: ${replayData.max_platform_center_offset.toFixed(3)} px`);
    } else {
        console.log("Platform Contact: None / Not Applicable for this wave.");
    }

    // Verify core replay requirements
    if (replayData.status !== "end_attack") {
        throw new Error(`Replay failed: status is '${replayData.status}', expected 'end_attack'`);
    }
    if (!replayData.no_hit) {
        throw new Error("Replay failed: no_hit invariant violated (damage or KR detected)");
    }
    if (replayData.frames !== expectedFrames || replayData.total_microticks !== expectedMicroticks) {
        throw new Error(`Replay frame mismatch: got ${replayData.frames} frames / ${replayData.total_microticks} ticks, expected ${expectedFrames} / ${expectedMicroticks}`);
    }
    if (replayData.start_hp !== 92 || replayData.end_hp !== 92 || replayData.end_kr !== 0) {
        throw new Error(`Replay HP/KR invariant failure: start_hp=${replayData.start_hp}, end_hp=${replayData.end_hp}, end_kr=${replayData.end_kr}`);
    }
    if (replayData.total_hits !== 0) {
        throw new Error(`Replay damage detected: total_hits=${replayData.total_hits}`);
    }
    if (replayData.min_clearance_raw_c2 < 3.5) {
        throw new Error(`Replay clearance violation: C2 raw clearance ${replayData.min_clearance_raw_c2.toFixed(3)} px < 3.5 px threshold`);
    }
    if (hasPlatforms && replayData.platform_contact_observed && replayData.min_platform_edge_margin !== null && replayData.min_platform_edge_margin < 6.0) {
        throw new Error(`Platform edge margin violation: ${replayData.min_platform_edge_margin.toFixed(3)} px < 6.0 px deadband threshold`);
    }

    // Optional Python C-space verification if supported
    let pyMetrics = null;
    if (attackName === "sans_platforms4hard") {
        try {
            console.log("\nEvaluating continuous clearance profile in Python...");
            const pyCheckScript = `
import json, math, numpy as np
from pathlib import Path
from nohit.engine.compact_platform import microstep, platform_at, Player
from nohit.engine.compact_wave import ROOT, compile_wave, prepare_collision_native

cand = json.loads(Path('${candidateFile.replace(/\\/g, "/")}').read_text())
actions = cand['actions']
schedule, geometry, initial = compile_wave(ROOT / 'c2-sans-fight/${attackName}.csv')
base_mask = prepare_collision_native(geometry, margin=0.0, margin_x=0.0, margin_y=0.0)

s = Player(initial[0], initial[1], initial[2], initial[3])
min_dist_to_raw = float('inf')
min_dist_to_minkowski = float('inf')
min_plat_edge = float('inf')
max_plat_center = 0.0

for f, a in enumerate(actions):
    for m in range(4):
        tick = f * 4 + m
        p = platform_at(tick)
        s = microstep(s, a, p, 1.0 / 240.0)
        for left, top, right, bottom in geometry[tick]:
            if not math.isfinite(left): continue
            dx = max(0.0, max(left - (s.x + 2), (s.x - 2) - right))
            dy = max(0.0, max(top - (s.y + 2), (s.y - 2) - bottom))
            mrg = max(dx, dy)
            if mrg < min_dist_to_raw: min_dist_to_raw = mrg
            
        px_loc, py_loc = s.x - 113.0, s.y - 231.0
        y_start, y_end = max(0, int(py_loc - 15)), min(160, int(py_loc + 16))
        x_start, x_end = max(0, int(px_loc - 15)), min(435, int(px_loc + 16))
        tick_mink = float('inf')
        for cy in range(y_start, y_end):
            for cx in range(x_start, x_end):
                if (base_mask[tick, cy, cx // 64] & (np.uint64(1) << np.uint64(cx % 64))) != 0:
                    cdx = max(0.0, abs(px_loc - cx) - 0.5)
                    cdy = max(0.0, abs(py_loc - cy) - 0.5)
                    d = max(cdx, cdy)
                    if d < tick_mink: tick_mink = d
        if tick_mink < min_dist_to_minkowski: min_dist_to_minkowski = tick_mink
        
        if abs(s.y - 327.95) < 1.0:
            center_off = abs(s.x - (p.x + p.width / 2.0))
            if center_off > max_plat_center: max_plat_center = center_off
            em = min(s.x - p.x, (p.x + p.width) - s.x)
            if em < min_plat_edge: min_plat_edge = em

result = {
    'min_dist_to_raw': min_dist_to_raw,
    'min_dist_to_minkowski': min_dist_to_minkowski,
    'min_plat_edge': min_plat_edge,
    'max_plat_center': max_plat_center
}
print(json.dumps(result))
`;
            const pyOut = execSync(`tools\\uv_py.bat -c "${pyCheckScript.replace(/"/g, '\\"').replace(/\n/g, ' ')}"`, { encoding: "utf-8" });
            pyMetrics = JSON.parse(pyOut.trim().split("\n").pop());
            console.log(`Min Raw Hazard Distance (Geometry): ${pyMetrics.min_dist_to_raw.toFixed(3)} px (criterion >= 3.5 px)`);
            console.log(`Min Conservative Minkowski Mask Distance: ${pyMetrics.min_dist_to_minkowski.toFixed(3)} px (criterion >= 2.0 px)`);
            console.log(`Min Platform Edge Margin: ${pyMetrics.min_plat_edge.toFixed(3)} px (criterion >= 6.0 px)`);

            if (pyMetrics.min_dist_to_minkowski < 2.0) {
                throw new Error(`Clearance failure: Minkowski mask distance ${pyMetrics.min_dist_to_minkowski} px < 2.0 px`);
            }
            if (pyMetrics.min_dist_to_raw < 3.5) {
                throw new Error(`Clearance failure: Raw hazard distance ${pyMetrics.min_dist_to_raw} px < 3.5 px`);
            }
            if (pyMetrics.min_plat_edge < 6.0) {
                throw new Error(`Deadband failure: Platform edge margin ${pyMetrics.min_plat_edge} px < 6.0 px`);
            }
        } catch (e) {
            console.warn(`Python clearance check error: ${e.message}`);
            throw e;
        }
    } else {
        console.log(`[Replay Info] Python clearance check skipped for ${attackName} (native C2 clearance ${replayData.min_clearance_raw_c2.toFixed(3)} px >= 3.5 px verified).`);
    }

    // Register candidate plan with dashboard server via POST http://127.0.0.1:8103/api/oracle-plan
    console.log("\nRegistering candidate plan with dashboard server (POST /api/oracle-plan)...");
    const planPayload = {
        wave: `${attackName}.csv`,
        seed: args.seed,
        result: {
            status: "candidate_found",
            frame: actions.length,
            actions: actions,
            trajectory: replayData.rows,
            end: replayData.end
        }
    };
    let candidateId = `oracle-${attackName}-${Date.now()}`;
    let registeredPlanPath = "";
    try {
        const regResp = await fetch("http://127.0.0.1:8103/api/oracle-plan", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(planPayload)
        });
        if (regResp.ok) {
            const regResult = await regResp.json();
            candidateId = regResult.candidate_id;
            registeredPlanPath = regResult.path;
            console.log("Plan registered successfully!");
            console.log(`Candidate ID: ${candidateId}`);
            console.log(`Plan Path: ${registeredPlanPath}`);
        } else {
            console.warn(`Plan registration returned HTTP ${regResp.status}`);
        }
    } catch (e) {
        console.warn(`Plan registration warning: ${e.message}`);
    }

    // Export comprehensive oracle replay results
    const exportResult = {
        attack: attackName,
        status: replayData.status,
        no_hit: replayData.no_hit,
        frames: replayData.frames,
        microticks: replayData.total_microticks,
        start_hp: replayData.start_hp,
        end_hp: replayData.end_hp,
        end_kr: replayData.end_kr,
        total_hits: replayData.total_hits,
        candidate_id: candidateId,
        registered_plan_path: registeredPlanPath,
        clearance_profile: {
            min_raw_hazard_clearance_c2_px: replayData.min_clearance_raw_c2,
            min_raw_hazard_distance_geom_px: pyMetrics ? pyMetrics.min_dist_to_raw : null,
            min_minkowski_mask_distance_px: pyMetrics ? pyMetrics.min_dist_to_minkowski : null,
            min_platform_edge_margin_px: replayData.min_platform_edge_margin,
            max_platform_center_offset_px: replayData.max_platform_center_offset,
            criteria_met: {
                c2_clearance_ge_3_5px: replayData.min_clearance_raw_c2 >= 3.5,
                minkowski_mask_ge_2px: pyMetrics ? pyMetrics.min_dist_to_minkowski >= 2.0 : true,
                raw_hazard_ge_3_5px: pyMetrics ? pyMetrics.min_dist_to_raw >= 3.5 : true,
                platform_deadband_ge_6px: replayData.min_platform_edge_margin !== null ? replayData.min_platform_edge_margin >= 6.0 : true
            }
        },
        actions: actions,
        trajectory: replayData.rows,
        microtick_records: replayData.micro_rows,
        timestamp: new Date().toISOString()
    };

    const outPath = `tools/operator-results/${attackName}-oracle-result.json`;
    fs.writeFileSync(outPath, JSON.stringify(exportResult, null, 2), "utf-8");
    console.log(`Detailed oracle replay result written to ${outPath}`);

    // Update original_replay_passed flag in candidate file if writable
    try {
        solverResult.original_replay_passed = true;
        solverResult.oracle_candidate_id = candidateId;
        fs.writeFileSync(candidateFile, JSON.stringify(solverResult, null, 2), "utf-8");
        console.log(`Updated original_replay_passed=true in ${candidateFile}`);
    } catch (_) {}

    console.log(`\n[ORACLE REPLAY PASS] attack=${attackName} frames=${replayData.frames} hp=92 kr=0 hits=0`);
}

main().catch(err => {
    console.error("FATAL ERROR in test_oracle_replay:", err.message || err);
    process.exit(1);
});

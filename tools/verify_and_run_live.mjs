import fs from "node:fs";
import path from "node:path";
import {assertLiveRuns} from './acceptance_verdict.mjs';

function printHelp() {
    console.log(`
Usage:
  node tools/verify_and_run_live.mjs [options]
  node tools/verify_and_run_live.mjs [attack_name] [plan_json_path] [continuous_rounds] [seed]

Options:
  --attack <name>       Target attack name (e.g. sans_bonegap1, sans_platforms4hard)
  --plan <path>         Path to candidate route plan JSON
  --continuous <number> Number of continuous live rounds to verify (default: 3)
  --seed <number>       RNG seed (default: 42)
  --timeout <number>    Total live acceptance timeout in milliseconds (default: 180000)
  --help, -h            Show this help message
`);
}

function parseArgs(argv) {
    const args = {
        attack: null,
        plan: null,
        continuous: 3,
        seed: 42,
        timeout: 180000
    };
    const positional = [];
    for (let i = 2; i < argv.length; i++) {
        const arg = argv[i];
        if (arg === "--attack" && i + 1 < argv.length) {
            args.attack = argv[++i];
        } else if (arg === "--plan" && i + 1 < argv.length) {
            args.plan = argv[++i];
        } else if (arg === "--continuous" && i + 1 < argv.length) {
            args.continuous = parseInt(argv[++i], 10);
        } else if (arg === "--seed" && i + 1 < argv.length) {
            args.seed = parseInt(argv[++i], 10);
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
    if (positional.length > 2) args.continuous = parseInt(positional[2], 10);
    if (positional.length > 3) args.seed = parseInt(positional[3], 10);
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

async function locateBrowserWsUrl() {
    const candidateFiles = [
        "<user>/AppData/Local/Google/Chrome/User Data/DevToolsActivePort",
        "<user>/AppData/Local/Google/Chrome/TASProfile/DevToolsActivePort"
    ];
    for (const portFile of candidateFiles) {
        if (fs.existsSync(portFile)) {
            try {
                const [portStr, browserPath] = fs.readFileSync(portFile, "utf-8").trim().split("\n").map(s => s.trim());
                if (portStr && browserPath) {
                    return `ws://127.0.0.1:${portStr}${browserPath}`;
                }
            } catch (_) {}
        }
    }

    // Try HTTP fallback to port 9222
    try {
        const resp = await fetch("http://127.0.0.1:9222/json/version");
        if (resp.ok) {
            const data = await resp.json();
            if (data.webSocketDebuggerUrl) return data.webSocketDebuggerUrl;
        }
    } catch (_) {}

    throw new Error("Chrome DevToolsActivePort not found and port 9222 is unreachable. Please ensure visible Chrome is running with --remote-debugging-port=9222.");
}

async function main() {
    console.log("=== Parameterized Foreground Desktop Chrome Live Acceptance ===");
    const args = parseArgs(process.argv);

    if (!args.attack && args.plan && fs.existsSync(args.plan)) {
        try {
            const raw = JSON.parse(fs.readFileSync(args.plan, "utf-8"));
            const rawWave = raw.attack || raw.wave || (raw.result && (raw.result.attack || raw.result.wave));
            if (rawWave) args.attack = String(rawWave).replace(/\.csv$/, "");
        } catch (_) {}
    }

    const attackName = (args.attack || "sans_platforms4hard").replace(/\.csv$/, "");
    const candidateFile = resolvePlanFile(attackName, args.plan);
    const continuousCount = args.continuous || 3;
    const seed = args.seed || 42;

    console.log(`Attack: ${attackName}`);
    console.log(`Candidate Plan: ${candidateFile}`);
    console.log(`Target Continuous Rounds: ${continuousCount}`);
    console.log(`Random Seed: ${seed}`);

    const solverResult = JSON.parse(fs.readFileSync(candidateFile, "utf-8"));
    const actions = solverResult.actions || (solverResult.result && solverResult.result.actions);
    if (!Array.isArray(actions) || actions.length === 0) {
        throw new Error(`Plan contains no actions in: ${candidateFile}`);
    }
    console.log(`Loaded solver route: ${actions.length} actions.`);

    const browserWsUrl = await locateBrowserWsUrl();
    console.log("Connecting to visible browser at:", browserWsUrl);

    const ws = new WebSocket(browserWsUrl);
    let idCounter = 0;
    const pending = new Map();

    ws.onmessage = (ev) => {
        let msg;
        try { msg = JSON.parse(ev.data); } catch { return; }
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

    function send(method, params = {}, sessionId) {
        const id = ++idCounter;
        const payload = { id, method, params };
        if (sessionId) payload.sessionId = sessionId;
        ws.send(JSON.stringify(payload));
        return new Promise((resolve, reject) => {
            pending.set(id, { resolve, reject });
            setTimeout(() => {
                if (pending.delete(id)) reject(new Error(`Timeout calling ${method}`));
            }, 60000);
        });
    }

    const targets = await send("Target.getTargets");
    let page = targets.targetInfos.find(t => t.type === "page" && t.url.includes("8103")) ||
               targets.targetInfos.find(t => t.type === "page");
    if (!page) {
        page = await send("Target.createTarget", { url: "about:blank" });
    }
    console.log("Using visible target:", page.targetId, page.url);

    // Bring visible desktop Chrome window to foreground
    try {
        await send("Target.activateTarget", { targetId: page.targetId });
        const win = await send("Browser.getWindowForTarget", { targetId: page.targetId });
        await send("Browser.setWindowBounds", {
            windowId: win.windowId,
            bounds: { windowState: "normal", width: 1280, height: 800 }
        });
        console.log("Brought visible Chrome to foreground and resized to 1280x800.");
    } catch (e) {
        console.warn("Window activation warning:", e.message);
    }

    const { sessionId } = await send("Target.attachToTarget", { targetId: page.targetId, flatten: true });
    await send("Page.enable", {}, sessionId);
    await send("Runtime.enable", {}, sessionId);

    // Step 1: 240Hz Independent Offline Replay in Oracle mode
    console.log("\n=== STEP 1: Running 240Hz Independent Offline Replay in Oracle ===");
    const oracleUrl = `http://127.0.0.1:8103/game/index.html?mode=single&attack=${attackName}&seed=${seed}&oracle=1`;
    await send("Page.navigate", { url: oracleUrl }, sessionId);

    // Wait for EngineOracle to be ready
    let oracleReady = false;
    for (let i = 0; i < 60; i++) {
        await new Promise(r => setTimeout(r, 200));
        const res = await send("Runtime.evaluate", {
            expression: "typeof window.EngineOracle !== 'undefined' && window.EngineOracle.ready === true",
            returnByValue: true
        }, sessionId);
        if (res.result && res.result.value === true) {
            oracleReady = true;
            break;
        }
    }
    if (!oracleReady) throw new Error("Timed out waiting for EngineOracle on oracle page.");
    console.log("EngineOracle is ready.");

    // Evaluate replay
    console.log("Executing O.replay(actions)...");
    const replayRes = await send("Runtime.evaluate", {
        expression: `(async () => {
            const O = window.EngineOracle;
            const res = await O.replay(${JSON.stringify(actions)});
            return {
                status: res.status,
                no_hit: res.no_hit,
                frames: res.frames,
                rows_count: res.rows ? res.rows.length : 0,
                start_hp: res.rows ? res.rows[0].HP : null,
                end_hp: res.rows ? res.rows[res.rows.length-1].HP : null,
                end_kr: res.rows ? res.rows[res.rows.length-1].KR : null,
                rows: res.rows
            };
        })()`,
        awaitPromise: true,
        returnByValue: true
    }, sessionId);

    const replayData = replayRes.result.value;
    console.log("Replay Verdict:", {
        status: replayData.status,
        no_hit: replayData.no_hit,
        start_hp: replayData.start_hp,
        end_hp: replayData.end_hp,
        end_kr: replayData.end_kr,
        frames: replayData.frames
    });

    if (!replayData.no_hit || replayData.end_hp !== 92 || replayData.end_kr !== 0 || replayData.status !== 'end_attack') {
        throw new Error("240Hz Offline Replay FAILED: route took damage or did not end attack!");
    }
    console.log(">>> STEP 1 PASSED: 240Hz Independent Replay 100% No-Hit! <<<");

    // Save candidate via API
    console.log("\n=== Registering Candidate via /api/oracle-plan ===");
    const regExpr = `(async () => {
        const O = window.EngineOracle;
        const result = {
            status: 'candidate_found',
            actions: ${JSON.stringify(actions)},
            trajectory: ${JSON.stringify(replayData.rows)},
            end: ${JSON.stringify(replayData.rows[replayData.rows.length - 1])}
        };
        const resp = await fetch('/api/oracle-plan', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                wave: '${attackName}.csv',
                seed: ${seed},
                result: result
            })
        });
        return await resp.json();
    })()`;

    const regRes = await send("Runtime.evaluate", {
        expression: regExpr,
        awaitPromise: true,
        returnByValue: true
    }, sessionId);

    const candidateId = regRes.result.value.candidate_id;
    console.log("Candidate Registered! candidate_id =", candidateId);

    // Step 2: Live Desktop Browser Non-Headless Acceptance Run
    console.log(`\n=== STEP 2: Live Visible Browser Run (${continuousCount} Rounds @ Normal Speed) ===`);
    const liveUrl = `http://127.0.0.1:8103/game/index.html?mode=single&attack=${attackName}&seed=${seed}&acceptance=1&continuous=1&candidate=${candidateId}`;
    console.log("Navigating visible browser to:", liveUrl);
    await send("Page.navigate", { url: liveUrl }, sessionId);

    console.log(`Monitoring ${continuousCount} consecutive live rounds on user screen...`);
    let completed = false;
    let finalRuns = [];
    let lastRound = 0;
    const startTime = Date.now();

    while (Date.now() - startTime < args.timeout) {
        await new Promise(r => setTimeout(r, 1000));
        const statusRes = await send("Runtime.evaluate", {
            expression: `(() => {
                const acc = window.__LIVE_ACC;
                if (!acc) return { ready: false };
                return {
                    ready: true,
                    runsCount: acc.runs.length,
                    passed: acc.result ? acc.result.passed : false,
                    runs: acc.runs.map((r, i) => ({
                        round: i + 1,
                        startHP: r.startHP,
                        minHP: r.rows && r.rows.length ? Math.min(...r.rows.map(x => x.HP)) : r.startHP,
                        endHP: r.end ? r.end.HP : null,
                        maxKR: r.rows && r.rows.length ? Math.max(...r.rows.map(x => x.KR)) : 0,
                        hits: r.hits ? r.hits.length : 0,
                        endAttackObserved: r.end ? r.end.endAttackObserved : false,
                        rows: r.rows ? r.rows.length : 0
                    }))
                };
            })()`,
            returnByValue: true
        }, sessionId);

        const val = statusRes.result.value;
        if (val && val.ready) {
            if (val.runsCount !== lastRound && val.runsCount > 0) {
                lastRound = val.runsCount;
                console.log(`[Live Progress] Completed round ${lastRound}/${continuousCount}. Telemetry:`, val.runs[lastRound - 1]);
            }
            if (val.runsCount >= continuousCount && val.runs[continuousCount - 1].endAttackObserved) {
                assertLiveRuns(val.runs, continuousCount);
                finalRuns = val.runs.slice(0, continuousCount);
                completed = true;
                console.log(`\nAll ${continuousCount} rounds completed! Final Telemetry:`, JSON.stringify(val.runs, null, 2));
                break;
            }
        }
    }

    if (!completed) {
        throw new Error(`Timed out waiting for ${continuousCount} live rounds to complete.`);
    }

    // Check HUD Status Badge
    const badgeRes = await send("Runtime.evaluate", {
        expression: `(() => {
            const b = document.getElementById('tas-status-badge');
            return b ? b.textContent : '';
        })()`,
        returnByValue: true
    }, sessionId);
    const badgeText = badgeRes.result.value || "";
    console.log(`HUD Badge Status Text: "${badgeText}"`);

    // Capture screen of visible game
    const ss = await send("Page.captureScreenshot", { format: "png" }, sessionId);
    const ssBuffer = Buffer.from(ss.data, "base64");
    fs.writeFileSync("tools/live_game_screen.png", ssBuffer);
    const specificScreenPath = `tools/operator-results/${attackName}_live_acceptance.png`;
    fs.writeFileSync(specificScreenPath, ssBuffer);
    console.log(`Screenshot saved to tools/live_game_screen.png and ${specificScreenPath}`);

    // Persist telemetry
    const telemetryPath = `tools/operator-results/${attackName}_live_telemetry.json`;
    fs.writeFileSync(telemetryPath, JSON.stringify({
        attack: attackName,
        candidate_id: candidateId,
        continuous_rounds: continuousCount,
        runs: finalRuns,
        badge_text: badgeText,
        timestamp: new Date().toISOString()
    }, null, 2));
    console.log(`Telemetry persisted to ${telemetryPath}`);

    ws.close();
    console.log(`\n>>> [LIVE ACCEPTANCE PASS] attack=${attackName} rounds=${continuousCount} hp=92 kr=0 hits=0 <<<`);
}

main().catch(err => {
    console.error("FATAL ERROR in verify_and_run_live:", err.message || err);
    process.exit(1);
});

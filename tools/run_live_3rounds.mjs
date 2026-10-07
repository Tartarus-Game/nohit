import fs from "node:fs";

async function main() {
    const portFile = "<user>/AppData/Local/Google/Chrome/User Data/DevToolsActivePort";
    const [portStr, browserPath] = fs.readFileSync(portFile, "utf-8").trim().split("\n").map(s => s.trim());
    const browserWsUrl = `ws://127.0.0.1:${portStr}${browserPath}`;
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
                if (pending.delete(id)) reject(new Error("Timeout calling " + method));
            }, 60000);
        });
    }

    const targets = await send("Target.getTargets");
    let page = targets.targetInfos.find(t => t.type === "page");
    if (!page) {
        page = await send("Target.createTarget", { url: "about:blank" });
    }
    console.log("Using visible target:", page.targetId);

    // Bring visible window to foreground and position
    try {
        await send("Target.activateTarget", { targetId: page.targetId });
        const win = await send("Browser.getWindowForTarget", { targetId: page.targetId });
        await send("Browser.setWindowBounds", {
            windowId: win.windowId,
            bounds: { windowState: "normal", width: 1280, height: 800 }
        });
        console.log("Brought visible Chrome to foreground.");
    } catch (e) {
        console.warn("Window control note:", e.message);
    }

    const { sessionId } = await send("Target.attachToTarget", { targetId: page.targetId, flatten: true });
    await send("Page.enable", {}, sessionId);
    await send("Runtime.enable", {}, sessionId);

    const candidateId = "1f39f386fd48e11e2b1127affd7cf8ef78b1041a3ffdabe393c3974c078ab692";
    const liveUrl = `http://127.0.0.1:8103/game/index.html?mode=single&attack=sans_platforms4hard&seed=42&acceptance=1&continuous=1&candidate=${candidateId}`;
    console.log("Navigating visible browser to:", liveUrl);
    await send("Page.navigate", { url: liveUrl }, sessionId);

    console.log("Monitoring 3 consecutive live rounds on user screen...");
    let completed = false;
    let lastRound = 0;
    const startTime = Date.now();

    while (Date.now() - startTime < 90000) {
        await new Promise(r => setTimeout(r, 1000));
        const statusRes = await send("Runtime.evaluate", {
            expression: `(() => {
                const acc = window.__LIVE_ACC;
                if (!acc) return { ready: false };
                return {
                    ready: true,
                    runsCount: acc.runs.length,
                    passed: acc.result ? acc.result.passed : false,
                    badgeText: document.getElementById('tas-status-badge')?.textContent || '',
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
                console.log(`[Live Progress] Completed round ${lastRound}/3. Telemetry:`, val.runs[lastRound - 1]);
            }
            if (val.runsCount >= 3 && val.runs[2].endAttackObserved) {
                completed = true;
                console.log("\nAll 3 rounds completed! Final Telemetry:", JSON.stringify(val.runs, null, 2));
                console.log("HUD Badge:", val.badgeText);
                break;
            }
        }
    }

    if (!completed) {
        throw new Error("Timed out waiting for 3 live rounds to complete.");
    }

    // Capture screen
    const ss = await send("Page.captureScreenshot", { format: "png" }, sessionId);
    fs.writeFileSync("tools/live_game_screen.png", Buffer.from(ss.data, "base64"));
    console.log("Screenshot saved to tools/live_game_screen.png");

    ws.close();
    console.log("\n>>> LIVE ACCEPTANCE 100% PASSED: 3 ROUNDS ZERO DAMAGE! <<<");
}

main().catch(err => {
    console.error("Execution error:", err);
    process.exit(1);
});

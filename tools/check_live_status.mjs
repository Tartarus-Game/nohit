import fs from "node:fs";

async function main() {
    const portFile = "<user>/AppData/Local/Google/Chrome/User Data/DevToolsActivePort";
    const [portStr, browserPath] = fs.readFileSync(portFile, "utf-8").trim().split("\n").map(s => s.trim());
    const browserWsUrl = `ws://127.0.0.1:${portStr}${browserPath}`;

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

    await new Promise((resolve) => ws.onopen = resolve);

    const send = (method, params = {}, sessionId) => new Promise((resolve, reject) => {
        const id = ++idCounter;
        const payload = { id, method, params };
        if (sessionId) payload.sessionId = sessionId;
        ws.send(JSON.stringify(payload));
        pending.set(id, { resolve, reject });
    });

    const targets = await send("Target.getTargets");
    let page = targets.targetInfos.find(t => t.type === "page");
    const { sessionId } = await send("Target.attachToTarget", { targetId: page.targetId, flatten: true });

    const runsRes = await send("Runtime.evaluate", {
        expression: `(() => {
            const acc = window.__LIVE_ACC;
            if (!acc) return null;
            return acc.runs.map((r, i) => ({
                round: i + 1,
                startHP: r.startHP,
                endHP: r.end ? r.end.HP : null,
                endKR: r.end ? r.end.KR : null,
                hits_count: r.hits.length,
                endAttackObserved: r.end ? r.end.endAttackObserved : false,
                rowCount: r.rows.length
            }));
        })()`,
        returnByValue: true
    }, sessionId);

    console.log("Runs Details:", JSON.stringify(runsRes.result.value, null, 2));

    // Also take a screenshot of the visible game canvas!
    const ss = await send("Page.captureScreenshot", { format: "png" }, sessionId);
    fs.writeFileSync("tools/live_game_screen.png", Buffer.from(ss.data, "base64"));
    console.log("Screenshot saved to tools/live_game_screen.png");

    ws.close();
}

main().catch(console.error);

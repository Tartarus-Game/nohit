import fs from "node:fs";

async function main() {
    const portFile = "<user>/AppData/Local/Google/Chrome/User Data/DevToolsActivePort";
    const [portStr, browserPath] = fs.readFileSync(portFile, "utf-8").trim().split("\n").map(s => s.trim());
    const browserWsUrl = `ws://127.0.0.1:${portStr}${browserPath}`;
    console.log("Connecting to:", browserWsUrl);

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
        ws.onopen = () => {
            console.log("WebSocket connection established!");
            resolve();
        };
        ws.onerror = (e) => reject(new Error("WS error: " + e));
    });

    function send(method, params = {}, sessionId) {
        const id = ++idCounter;
        const payload = { id, method, params };
        if (sessionId) payload.sessionId = sessionId;
        ws.send(JSON.stringify(payload));
        return new Promise((resolve, reject) => {
            pending.set(id, { resolve, reject });
            setTimeout(() => {
                if (pending.delete(id)) reject(new Error("Timeout: " + method));
            }, 10000);
        });
    }

    const targets = await send("Target.getTargets");
    let page = targets.targetInfos.find(t => t.type === "page");
    if (!page) {
        console.log("Creating new target...");
        page = await send("Target.createTarget", { url: "about:blank" });
    }
    console.log("Found page target:", page.targetId, page.url);

    // Bring Chrome window to foreground
    try {
        await send("Target.activateTarget", { targetId: page.targetId });
        console.log("Activated target window");
    } catch (e) {
        console.warn("activateTarget warning:", e.message);
    }

    // Attach to page
    const { sessionId } = await send("Target.attachToTarget", { targetId: page.targetId, flatten: true });
    console.log("Attached with sessionId:", sessionId);

    // Enable Runtime and Page
    await send("Page.enable", {}, sessionId);
    await send("Runtime.enable", {}, sessionId);

    const candidateUrl = "http://127.0.0.1:8103/game/index.html?mode=single&attack=sans_platforms4hard&seed=42&acceptance=1&continuous=1&candidate=fa2d81679b9884c1e053c82f9269b858a0ccad1aff684e4f91d7248b7d1dc2fa";
    console.log("Navigating to:", candidateUrl);
    const nav = await send("Page.navigate", { url: candidateUrl }, sessionId);
    console.log("Navigation result:", nav);

    // Window bounds
    try {
        const win = await send("Browser.getWindowForTarget", { targetId: page.targetId });
        console.log("Window info:", win);
        await send("Browser.setWindowBounds", {
            windowId: win.windowId,
            bounds: { windowState: "normal", width: 1280, height: 800 }
        });
        console.log("Window bounds applied!");
    } catch (e) {
        console.warn("Window control note:", e.message);
    }

    ws.close();
    console.log("Done! Visible browser window navigated to game.");
}

main().catch(console.error);

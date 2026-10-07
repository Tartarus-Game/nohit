import fs from "node:fs";

async function main() {
    const portFile = "<user>/AppData/Local/Google/Chrome/User Data/DevToolsActivePort";
    if (!fs.existsSync(portFile)) {
        throw new Error("DevToolsActivePort not found");
    }
    const [portStr, browserPath] = fs.readFileSync(portFile, "utf-8").trim().split("\n").map(s => s.trim());
    const browserWsUrl = `ws://127.0.0.1:${portStr}${browserPath}`;

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
    await new Promise((r, j) => { ws.onopen = r; ws.onerror = j; });

    function send(method, params = {}, sessionId) {
        const id = ++idCounter;
        const payload = { id, method, params };
        if (sessionId) payload.sessionId = sessionId;
        ws.send(JSON.stringify(payload));
        return new Promise((resolve, reject) => {
            pending.set(id, { resolve, reject });
            setTimeout(() => {
                if (pending.delete(id)) reject(new Error("Timeout calling " + method));
            }, 30000);
        });
    }

    const targets = await send("Target.getTargets");
    console.log("Active targets count:", targets.targetInfos.length);
    targets.targetInfos.forEach(t => console.log(`Target: [${t.type}] ${t.title} -> ${t.url}`));

    // Look for existing Gemini tab
    let geminiTarget = targets.targetInfos.find(t => t.url && t.url.includes("gemini.google.com"));
    let targetId;
    let createdNew = false;

    if (geminiTarget) {
        console.log("Found existing Gemini target:", geminiTarget.targetId, geminiTarget.url);
        targetId = geminiTarget.targetId;
    } else {
        console.log("No Gemini target found. Creating new tab for Gemini link...");
        const newTarget = await send("Target.createTarget", { url: "https://gemini.google.com/u/1/app/5fcf200ce11527e6" });
        targetId = newTarget.targetId;
        createdNew = true;
    }

    const { sessionId } = await send("Target.attachToTarget", { targetId, flatten: true });
    await send("Page.enable", {}, sessionId);
    await send("Runtime.enable", {}, sessionId);

    if (geminiTarget && !geminiTarget.url.includes("5fcf200ce11527e6")) {
        console.log("Navigating existing Gemini tab to conversation URL...");
        await send("Page.navigate", { url: "https://gemini.google.com/u/1/app/5fcf200ce11527e6" }, sessionId);
    }

    console.log("Waiting for page load and conversation DOM elements...");
    let extracted = null;
    for (let i = 0; i < 40; i++) {
        await new Promise(r => setTimeout(r, 1000));
        const res = await send("Runtime.evaluate", {
            expression: `(() => {
                // Try to find conversation text
                const textNodes = [];
                // Check if login page or conversation container
                const title = document.title;
                const bodyText = document.body ? document.body.innerText : "";
                
                // Gemini specific selectors
                const turns = Array.from(document.querySelectorAll('.conversation-container, .chat-history, message-content, user-query-container, model-response, [data-test-id="conversation-turn"]'));
                
                return {
                    url: location.href,
                    title: document.title,
                    turnsCount: turns.length,
                    bodyTextPreview: bodyText.slice(0, 500),
                    bodyLength: bodyText.length,
                    fullText: bodyText
                };
            })()`,
            returnByValue: true
        }, sessionId);

        const val = res.result ? res.result.value : null;
        if (val) {
            console.log(`Poll ${i+1}: title="${val.title}", bodyLength=${val.bodyLength}`);
            if (val.bodyLength > 1000 && !val.title.includes("Sign in") && !val.title.includes("登录")) {
                extracted = val;
                // Wait an extra 2 seconds for all messages to finish rendering
                await new Promise(r => setTimeout(r, 2000));
                const finalRes = await send("Runtime.evaluate", {
                    expression: `(() => {
                        return {
                            url: location.href,
                            title: document.title,
                            fullText: document.body ? document.body.innerText : ""
                        };
                    })()`,
                    returnByValue: true
                }, sessionId);
                extracted = finalRes.result.value;
                break;
            } else if (val.title.includes("Sign in") || val.title.includes("登录")) {
                extracted = val;
                console.log("Page redirected to Google Sign-In!");
                break;
            }
        }
    }

    if (extracted) {
        fs.writeFileSync("tools/extracted_gemini_chat.txt", extracted.fullText, "utf-8");
        console.log("Saved extracted text to tools/extracted_gemini_chat.txt (length: " + extracted.fullText.length + ")");
    } else {
        console.log("Could not extract conversation content.");
    }

    ws.close();
}

main().catch(console.error);

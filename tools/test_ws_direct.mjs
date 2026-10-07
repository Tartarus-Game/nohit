import fs from "node:fs";

const portFile = "<user>/AppData/Local/Google/Chrome/User Data/DevToolsActivePort";
const [portStr, browserPath] = fs.readFileSync(portFile, "utf-8").trim().split("\n").map(s => s.trim());
const browserWsUrl = `ws://127.0.0.1:${portStr}${browserPath}`;
console.log("Testing WS connection to:", browserWsUrl);

const ws = new WebSocket(browserWsUrl);
ws.onopen = () => {
    console.log("WS OPEN SUCCESS!");
    ws.send(JSON.stringify({ id: 1, method: "Target.getTargets" }));
};
ws.onmessage = (ev) => {
    console.log("WS MESSAGE:", ev.data.slice(0, 200));
    ws.close();
    process.exit(0);
};
ws.onerror = (err) => {
    console.error("WS ERROR:", err);
};
ws.onclose = (ev) => {
    console.log("WS CLOSED:", ev.code, ev.reason);
};

setTimeout(() => {
    console.log("WS TIMEOUT, readyState:", ws.readyState);
    process.exit(1);
}, 5000);

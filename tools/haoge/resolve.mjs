/**
 * Re-solve a list of rounds from their captured entry requests.
 *
 * Usage: node resolve.mjs --http 8160 --rounds a,b,c --width 1200 --seconds 60 [--tag t]
 * Writes <round>.<tag>.json next to the other route files.
 */
import fs from "node:fs";
import path from "node:path";

function arg(name, fallback) {
    const i = process.argv.indexOf("--" + name);
    return i >= 0 ? process.argv[i + 1] : fallback;
}
const HTTP_PORT = Number(arg("http", "8160"));
const DIR = arg("dir", "scratch/haoge-run");
const ROUNDS = arg("rounds", "").split(",").filter(Boolean);
const WIDTH = Number(arg("width", "1200"));
const SECONDS = Number(arg("seconds", "60"));
const TAG = arg("tag", "retry");
const BINDINGS = arg("bindings", "1");

const results = [];
async function one(round) {
    const reqPath = path.join(DIR, "entries", round + ".request.json");
    if (!fs.existsSync(reqPath)) { console.log(`${round}: no captured request`); return; }
    const payload = JSON.parse(fs.readFileSync(reqPath, "utf-8"));
    payload.width = WIDTH; payload.seconds = SECONDS; payload.max_ticks = 40000;
    payload.max_bindings = Number(BINDINGS);
    payload.request_id = crypto.randomUUID(); payload.progress_id = payload.request_id;
    const started = Date.now();
    try {
        const res = await fetch(`http://127.0.0.1:${HTTP_PORT}/api/solve-csv`, {
            method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
        const body = await res.json();
        const elapsed = (Date.now() - started) / 1000;
        const out = path.join(DIR, "routes", `${round}.${TAG}.json`);
        if (res.ok && body.status === "candidate_found") fs.writeFileSync(out, JSON.stringify(body), "utf-8");
        else fs.writeFileSync(out, JSON.stringify(body), "utf-8");
        const line = `${round.padEnd(24)} ${String(body.status).padEnd(16)} a=${(body.actions || []).length} ` +
            `reached=${body.reached_tick} w=${WIDTH} s=${SECONDS} ${elapsed.toFixed(0)}s reason=${body.reason || body.error}`;
        console.log(line);
        results.push({ round, status: body.status, reason: body.reason, reached_tick: body.reached_tick,
            actions: (body.actions || []).length, elapsed });
    } catch (error) {
        const cause = error && error.cause ? ` cause=${error.cause.code || error.cause.message || error.cause}` : "";
        console.log(`${round.padEnd(24)} HARNESS ERROR ${error}${cause}`);
        results.push({ round, status: "harness_error", error: String(error) + cause });
    }
}

await Promise.all(ROUNDS.map(one));
fs.writeFileSync(path.join(DIR, `resolve-${TAG}.json`), JSON.stringify(results, null, 2), "utf-8");
const solved = results.filter((r) => r.status === "candidate_found").length;
console.log(`\n${solved}/${ROUNDS.length} solved with width=${WIDTH} seconds=${SECONDS} tag=${TAG}`);

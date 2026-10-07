/**
 * Package the captured entry states and solved routes into playable route files.
 *
 * For every round that reached `candidate_found` this writes one self-contained
 * replay file (entry state + clock + the exact action/confirm sequence) plus a
 * single index. Rounds that never solved are listed with their refusal reason
 * instead of being dropped.
 *
 * Usage: node emit_routes.mjs [--dir scratch/haoge-run] [--out ROUTES.json]
 */
import fs from "node:fs";
import path from "node:path";
import crypto from "node:crypto";

function arg(name, fallback) {
    const i = process.argv.indexOf("--" + name);
    return i >= 0 ? process.argv[i + 1] : fallback;
}
const DIR = arg("dir", "scratch/haoge-run");
const OUT = arg("out", "ROUTES.json");
const ENTRIES = path.join(DIR, "entries");
const ROUTES = path.join(DIR, "routes");
const REPLAY = path.join(DIR, "replay");
// The game's own directory also gets a copy of each full plan, so the browser can
// play a verified route instead of re-solving it (`?route=<round>`). Only the
// decorative `visualization` block is dropped; every field the in-game
// validator checks is kept.
const PLANS = arg("plans", "haoge-runtime/routes");
fs.mkdirSync(REPLAY, { recursive: true });
if (PLANS) fs.mkdirSync(PLANS, { recursive: true });

const rounds = fs.readdirSync(ENTRIES).filter((f) => f.endsWith(".request.json")).sort();
// A round may have several attempts on disk (the escalating ladder, then the
// low-width / long-budget re-runs). Prefer a solved one over the deepest refusal.
function pickRoute(stem) {
    const candidates = fs.readdirSync(ROUTES)
        .filter((f) => f === stem + ".json" || f.startsWith(stem + "."))
        .map((f) => ({ file: path.join(ROUTES, f), body: JSON.parse(fs.readFileSync(path.join(ROUTES, f), "utf-8")) }));
    const solved = candidates.filter((c) => c.body.status === "candidate_found" && (c.body.actions || []).length);
    const pool = solved.length ? solved : candidates;
    if (!pool.length) return null;
    return pool.sort((a, b) => (b.body.reached_tick || 0) - (a.body.reached_tick || 0))[0];
}
const index = [];
for (const file of rounds) {
    const stem = file.replace(".request.json", "");
    const request = JSON.parse(fs.readFileSync(path.join(ENTRIES, file), "utf-8"));
    const picked = pickRoute(stem);
    const entry = { round: stem, csv_sha256: null, csv_bytes: request.custom_csv.length,
        solved: false, reason: null, actions: 0, game_seconds: null };

    const digest = crypto.createHash("sha256").update(request.custom_csv, "utf-8").digest("hex");
    entry.csv_sha256 = digest;

    if (!picked) {
        entry.reason = "not_attempted";
    } else {
        const result = picked.body;
        entry.reason = result.reason || result.error || result.status;
        const actions = result.actions || [];
        const confirms = result.confirm_sequence || [];
        if (result.status === "candidate_found" && actions.length) {
            const schedule = request.dt_schedule;
            const uniform = schedule && schedule.every((v) => v === schedule[0]);
            const replay = {
                schema: "nohit-haoge-route-v1",
                round: stem,
                note: "Entry state and clock are the ones the original game produced at this round's "
                    + "custom entry; `actions` are LRUD keymasks, one per native tick, and "
                    + "`confirm_sequence` is the Confirm bit for the same ticks.",
                game: {
                    repo: "https://github.com/1742137113/haoge-sans",
                    branch: "gh-pages",
                    commit: "a1c36cbc3204e459b0d48df4df076d6895449c18",
                    csv_sha256: digest,
                    baseline_hp: 142,
                },
                clock: {
                    fps: request.fps,
                    max_ticks: request.max_ticks,
                    dt0: schedule ? schedule[0] : null,
                    uniform,
                    dt_schedule: uniform ? null : schedule,
                    logical_step_ms: Math.min((schedule ? schedule[0] : 1 / 30), 1 / 30) * 1000,
                },
                entry_state: {
                    initial: request.initial,
                    initial_environment: request.initial_environment,
                    initial_arena: request.initial_arena,
                    initial_confirm: request.initial_confirm,
                    previous_confirm: request.previous_confirm,
                    initial_target_history: request.initial_target_history,
                },
                route: {
                    actions,
                    confirm_sequence: confirms,
                    action_count: actions.length,
                    reached_tick: result.reached_tick,
                    game_seconds: result.game_seconds,
                    wall_seconds: result.wall_seconds,
                    verified: result.verified,
                    completion: result.completion,
                },
            };
            fs.writeFileSync(path.join(REPLAY, stem + ".json"), JSON.stringify(replay), "utf-8");
            if (PLANS) {
                // The in-game validator compares `visualization.frames[0].env`
                // (22 floats) against the live boundary, so that one frame must
                // always be present. The rest of the visualization is decorative
                // geometry and is dropped: it is what made the raw responses 50 MB+.
                //
                // `visualization` is added by the dashboard's /api/solve-csv, NOT by
                // solve_csv itself, so a route produced by the standalone process
                // entry (solve_entry.py) has none. Those plans failed validation with
                // "frame0 environment differs" purely because the frame was missing.
                // Synthesise it from the plan's own recorded initial environment,
                // which is the boundary the route was solved against -- so the check
                // still compares that boundary against the live one, exactly as
                // intended, instead of failing on an absent field.
                const { visualization, ...plan } = result;
                const first = visualization && Array.isArray(visualization.frames) ? visualization.frames[0] : null;
                const frame0 = first || (Array.isArray(plan.initial_environment)
                    ? { env: plan.initial_environment.slice() } : null);
                if (!frame0) throw new Error(`${stem}: no frame-0 environment available to publish`);
                plan.visualization = { frames: [frame0] };
                fs.writeFileSync(path.join(PLANS, stem + ".plan.json"), JSON.stringify(plan), "utf-8");
            }
            entry.solved = true;
            entry.actions = actions.length;
            entry.game_seconds = result.game_seconds;
            entry.wall_seconds = result.wall_seconds;
            entry.verified = result.verified;
            entry.replay = path.posix.join(DIR, "replay", stem + ".json");
        }
    }
    index.push(entry);
}

const summary = {
    schema: "nohit-haoge-routes-index-v1",
    game: { repo: "https://github.com/1742137113/haoge-sans", branch: "gh-pages",
        commit: "a1c36cbc3204e459b0d48df4df076d6895449c18", baseline_hp: 142 },
    criterion: "HP never falls below MaxHP (142). KR is recorded, not required zero: this build "
        + "scripts DamagePlayer(-N, 1) as a heal and drains HP only above KR 10.",
    protocol: "Each route is bound to the entry state the real game produces at that round's "
        + "Custom entry with seed 42 and the native 30 Hz clamp clock.",
    rounds: index,
    solved: index.filter((r) => r.solved).length,
    total: index.length,
};
fs.writeFileSync(path.join(DIR, OUT), JSON.stringify(summary, null, 2), "utf-8");

if (PLANS) {
    // Small machine-readable list for the one-click replay page that the dashboard
    // serves from the game directory itself.
    const playable = index.filter((r) => r.solved).map((r) => ({
        round: r.round, actions: r.actions, game_seconds: r.game_seconds,
        verified: r.verified, plan: `routes/${r.round}.plan.json`,
        csv_path: path.resolve(path.dirname(PLANS), r.round + ".csv"),
    }));
    fs.writeFileSync(path.join(PLANS, "index.json"), JSON.stringify(playable, null, 2), "utf-8");
}

console.log(`${"round".padEnd(26)} ${"solved".padEnd(7)} ${"actions".padStart(7)} ${"game_s".padStart(8)}  reason`);
for (const r of index) {
    console.log(`${r.round.padEnd(26)} ${String(r.solved).padEnd(7)} ${String(r.actions).padStart(7)} ` +
        `${(r.game_seconds ? r.game_seconds.toFixed(1) : "-").padStart(8)}  ${r.reason}`);
}
console.log(`\nsolved ${summary.solved}/${summary.total} -> ${path.join(DIR, OUT)}`);

/**
 * Compact summary of one drive.mjs result. Never prints bulk vectors.
 * Usage: node summarize.mjs <result.json> [...]
 */
import fs from "node:fs";

for (const file of process.argv.slice(2)) {
    const r = JSON.parse(fs.readFileSync(file, "utf-8"));
    const s = r.last_summary || {};
    const t = s.csvtas || {}, c = s.custom || {}, p = s.campaign || {}, f = s.full || {}, b = s.bridge || {};
    const plan = t.plan || null;
    const lines = [];
    lines.push(`== ${r.label} :: ${r.terminal_status}  (${r.elapsed_seconds.toFixed(0)}s) ==`);
    lines.push(`  bridge=${b.status}${b.error ? " ERR=" + b.error : ""} clock=${s.clock && s.clock.mode}`);
    lines.push(`  csvtas=${t.status}${t.error ? " ERR=" + t.error : ""} actionsApplied=${t.actionsApplied}`);
    if (plan) lines.push(`  plan=${plan.status} reason=${plan.reason} verified=${plan.verified} actions=${plan.actions} reached_tick=${plan.reached_tick} game_s=${plan.game_seconds} wall_s=${plan.wall_seconds && plan.wall_seconds.toFixed(1)} replay=${plan.original_replay_passed}`);
    if (t.solve_timing && t.solve_timing.attempts && t.solve_timing.attempts.length)
        lines.push(`  attempts=` + t.solve_timing.attempts.map(a => `${a.state || a.status}:${((a.total_ms ?? a.total ?? 0) / 1000)}s`).join(", "));
    lines.push(`  custom=${c.status} ticks=${c.ticks} rows=${c.rows} eof=${c.eofObserved} certified=${c.terminalCertified} damage=${c.firstDamage ? JSON.stringify({tick: c.firstDamage.tick, HP: c.firstDamage.HP, KR: c.firstDamage.KR, source: c.firstDamage.source}) : "none"} errors=${JSON.stringify(c.errors)}`);
    if (c.firstDamage) {
        const d = c.firstDamage;
        lines.push(`    damage detail: attack=${d.attack} line=${d.line} T=${d.T} running=${d.running} pending=${d.source} args=${JSON.stringify(d.args)}`);
    }
    if (p.status) lines.push(`  campaign=${p.status} err=${p.error} plans=${p.planCount} ` + JSON.stringify(p.plans));
    if (f.status) lines.push(`  full=${f.status} done=${f.done} rounds=${f.rounds} ticks=${f.checkedTicks} win=${f.winObserved} tickGaps=${f.tickGaps} clockErrors=${f.clockErrors} protocol=${JSON.stringify(f.protocolErrors)} payloadBytes=${f.payloadBytes} err=${f.error}`);
    if (r.console_errors && r.console_errors.length) lines.push(`  console(${r.console_errors.length}): ` + r.console_errors.slice(0, 4).map(e => (e.text || "").slice(0, 160)).join(" | "));
    console.log(lines.join("\n"));
}

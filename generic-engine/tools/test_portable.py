"""Integration acceptance: real Godot frames plus deliberate adapter faults."""
import argparse
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("nohit_cli", HERE / "nohit.py")
cli = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cli)

def run_case(project, engine, out, mask=4, mode="run"):
    command = [sys.executable, str(HERE / "nohit.py"), mode, str(project), "--godot", str(engine),
               "--output", str(out), "--max-ticks", "70", "--mask", str(mask), "--workers", "4"]
    completed = subprocess.run(command, capture_output=True, text=True, timeout=60)
    if not (out / "summary.json").is_file():
        raise AssertionError(completed.stdout + completed.stderr)
    return cli.read(out / "summary.json")

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--godot3", type=Path)
    p.add_argument("--godot4", type=Path)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    if a.output.exists(): raise ValueError("Use a new output directory")
    a.output.mkdir(parents=True)
    records = []
    start = time.perf_counter()
    for version, engine in [(3, a.godot3), (4, a.godot4)]:
        if not engine: continue
        engine = engine.resolve()
        with tempfile.TemporaryDirectory(prefix=f"nohit-sdk-godot{version}-") as tmp:
            root = Path(tmp)
            def fixture(name):
                target = root / name
                shutil.copytree(cli.PORTABLE / f"examples/godot{version}", target,
                                ignore=shutil.ignore_patterns(".godot", ".import", "addons"))
                cli.install(target.resolve(), str(version))
                return target
            def record(name, result, expected):
                assert result["status"] == expected, (name, result)
                records.append({"engine_major": version, "case": name, "status": result["status"], "passed": True})
            base = fixture("baseline")
            adapter_bytes = (base / "nohit_adapter.gd").read_bytes()
            project_bytes = (base / "project.godot").read_bytes()
            cli.install(base.resolve(), str(version))
            assert (base / "nohit_adapter.gd").read_bytes() == adapter_bytes
            assert (base / "project.godot").read_bytes() == project_bytes
            records.append({"engine_major": version, "case": "idempotent_install_preserves_game_and_adapter", "passed": True})
            result = run_case(base, engine, a.output / f"godot{version}-verified", mode="verify")
            record("native_route_fresh_replay_damage_control", result, "native_nohit_fresh_process_observed")
            configured = fixture("configured")
            (configured / "nohit_adapter.gd").unlink()
            cli.install(configured.resolve(), str(version), config=cli.PORTABLE / "config.example.json")
            result = run_case(configured, engine, a.output / f"godot{version}-configured", mode="verify")
            record("configuration_only_adapter", result, "native_nohit_fresh_process_observed")
            missing = fixture("missing_audit")
            f = missing / "nohit_adapter.gd"
            f.write_text(f.read_text().replace("enable_damage_audit()", "pass"))
            record("missing_damage_audit_rejected", run_case(missing, engine, a.output / f"godot{version}-missing-audit"), "invalid_adapter")
            no_end = fixture("missing_end")
            f = no_end / "nohit_adapter.gd"
            f.write_text(f.read_text().replace("game.attack_finished.connect(mark_finished)" if version == 4 else
                'game.connect("attack_finished", self, "mark_finished")', "pass"))
            record("survival_without_attack_end_is_unknown", run_case(no_end, engine, a.output / f"godot{version}-missing-end"), "unknown")
            healed = fixture("healed")
            f = healed / "game.gd"
            f.write_text(f.read_text().replace("hp -= 1", "hp -= 1\n\t\thp += 1"))
            result = run_case(healed, engine, a.output / f"godot{version}-healed", mask=0)
            record("healing_cannot_hide_damage", result, "hit")
            assert result["frames"][-1]["state"]["hp"] == 20
            bad_json = fixture("bad_json")
            f = bad_json / "nohit_adapter.gd"
            f.write_text(f.read_text().replace('"x": game.soul_position.x', '"x": game.soul_position'))
            record("non_json_observation_rejected", run_case(bad_json, engine, a.output / f"godot{version}-bad-json"), "invalid_adapter")
            divergent = fixture("divergent")
            f = divergent / "nohit_adapter.gd"
            f.write_text(f.read_text().replace('"x": game.soul_position.x', '"process": OS.get_process_id(), "x": game.soul_position.x'))
            record("fresh_process_divergence_rejected", run_case(divergent, engine, a.output / f"godot{version}-divergent", mode="verify"), "replay_failed")
            safe_control = fixture("safe_control")
            f = safe_control / "game.gd"
            f.write_text(f.read_text().replace("Vector2(110 - tick * 2, 50)", "Vector2(110 - tick * 2, 500)"))
            record("non_damaging_control_withholds_certificate", run_case(safe_control, engine, a.output / f"godot{version}-safe-control", mode="verify"), "control_failed")
            delayed = fixture("delayed_hit")
            f = delayed / "game.gd"
            emission = 'damaged.emit(1)' if version == 4 else 'emit_signal("damaged", 1)'
            s = f.read_text().replace("if not running: return", 'if not running:\n\t\tif tick == 45:\n\t\t\t' + emission + '\n\t\t\ttick += 1\n\t\treturn')
            f.write_text(s)
            record("post_completion_damage_audited", run_case(delayed, engine, a.output / f"godot{version}-delayed-hit"), "hit")
            input_edges = fixture("input_edges")
            f = input_edges / "game.gd"
            s = f.read_text() + '\nvar input_presses = 0\nfunc _input(event):\n\tif event.is_action_pressed("ui_up"):\n\t\tinput_presses += 1\n'
            f.write_text(s)
            f = input_edges / "nohit_adapter.gd"
            f.write_text(f.read_text().replace('"hp": game.hp', '"presses": game.input_presses, "hp": game.hp'))
            result = run_case(input_edges, engine, a.output / f"godot{version}-input-edges")
            record("event_edges_and_polling_both_work", result, "native_route_candidate")
            assert result["frames"][-1]["state"]["presses"] == 1
            assert result["frames"][-1]["state"]["y"] == 5
            record("parallel_native_portfolio", run_case(base, engine, a.output / f"godot{version}-portfolio", mode="solve"), "native_nohit_fresh_process_observed")
    if not records: raise ValueError("Pass --godot3 and/or --godot4")
    summary = {"passed": len(records), "failed": 0, "wall_seconds": time.perf_counter() - start,
               "scope": "Portable fixtures and deliberate faults; not upstream level certificates", "cases": records}
    cli.save(a.output / "acceptance.json", summary)
    print(json.dumps(summary, indent=2))

if __name__ == "__main__":
    main()

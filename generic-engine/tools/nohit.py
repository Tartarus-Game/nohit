#!/usr/bin/env python3
"""Zero-dependency installer and fresh-process native route runner (Godot 3/4)."""
from __future__ import annotations
import argparse
import concurrent.futures
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time

PORTABLE = Path(__file__).resolve().parents[1] / "portable"
SCHEMA = "nohit.live.v1"

def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))

def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")

def major(project, requested=None):
    text = (project / "project.godot").read_text(encoding="utf-8")
    if requested:
        return int(requested)
    feature = re.search(r'config/features=.*?"([34])\.', text)
    if feature:
        return int(feature.group(1))
    config = re.search(r"^config_version\s*=\s*(\d+)", text, re.M)
    if config:
        return 4 if int(config.group(1)) >= 5 else 3
    raise ValueError("Cannot detect Godot version; pass --engine 3 or --engine 4")

def project_path(value):
    result = Path(value).expanduser().resolve()
    if not (result / "project.godot").is_file():
        raise argparse.ArgumentTypeError("Project must contain project.godot: " + str(result))
    return result

def install(project, engine=None, force=False, config=None):
    version = major(project, engine)
    source = PORTABLE / f"godot{version}"
    targets = [(source / name, project / "addons/nohit_live" / name)
               for name in ["adapter_base.gd", "session.gd", "configured_adapter.gd"]]
    if not (project / "nohit_adapter.gd").exists():
        targets.append((source / "nohit_adapter.gd", project / "nohit_adapter.gd"))
    # Preflight the complete operation. Never follow a symlink outside a project.
    for src, dst in targets:
        if dst.is_symlink() or not dst.resolve().is_relative_to(project):
            raise ValueError("Unsafe installation destination: " + str(dst))
        if dst.exists() and dst.read_bytes() != src.read_bytes() and not force:
            raise ValueError("Add-on differs; use --force-addon to replace SDK files. Your adapter is preserved: " + str(dst))
    if config:
        data = read(config)
        if data.get("schema") != "nohit.config.v1":
            raise ValueError("Config schema must be nohit.config.v1")
        dst = project / "nohit_config.json"
        if dst.is_symlink() or (dst.exists() and read(dst) != data):
            raise ValueError("Existing nohit_config.json is preserved; edit it directly")
        if (project / "nohit_adapter.gd").exists() and (project / "nohit_adapter.gd").read_text() != 'extends "res://addons/nohit_live/configured_adapter.gd"\n':
            raise ValueError("Existing custom adapter is preserved; use a new fixture or configure it manually")
    for src, dst in targets:
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dst)
    if config:
        save(project / "nohit_config.json", data)
        (project / "nohit_adapter.gd").write_text('extends "res://addons/nohit_live/configured_adapter.gd"\n')
    return {"status": "installed", "engine_major": version,
            "adapter": str(project / "nohit_adapter.gd"),
            "next": "Connect original damage/KR and attack-end hooks in nohit_adapter.gd, then run doctor and solve.",
            "project_settings_changed": False}

def doctor(project):
    version = major(project)
    text = (project / "project.godot").read_text(encoding="utf-8")
    main = re.search(r'^run/main_scene\s*=\s*"(.+)"', text, re.M)
    checks = {"project": True, "engine_major": version,
              "main_scene_configured": main is not None,
              "adapter_exists": (project / "nohit_adapter.gd").is_file(),
              "sdk_files_exist": all((project / "addons/nohit_live" / n).is_file()
                                     for n in ["adapter_base.gd", "session.gd"])}
    return {"status": "static_ready" if all(checks[k] for k in
            ["main_scene_configured", "adapter_exists", "sdk_files_exist"]) else "needs_installation",
            "checks": checks, "scope": "File/configuration checks only. A native run validates hooks, observations and InputMap.",
            "required_hooks": ["damage and KR contacts", "original attack completion", "nonempty JSON observation"],
            "input_bits": {"1": "left", "2": "right", "4": "up/jump", "8": "down"}}

def load_route(path):
    data = read(path)
    route = data.get("route") if isinstance(data, dict) else data
    if not isinstance(route, list) or not route or any(type(x) is not int or not 0 <= x <= 255 for x in route):
        raise ValueError("Route must be a nonempty array of integer masks 0..255")
    return route

def fingerprint(project):
    files = ["project.godot", "nohit_adapter.gd", "addons/nohit_live/adapter_base.gd", "addons/nohit_live/session.gd"]
    files += [name for name in ["nohit_config.json", "addons/nohit_live/configured_adapter.gd"] if (project / name).is_file()]
    return {name: hashlib.sha256((project / name).read_bytes()).hexdigest() for name in files}

def validate_result(value):
    if value.get("schema") != "nohit.live.result.v1":
        raise ValueError("Wrong result schema")
    status = value.get("status")
    if status not in ["invalid_adapter", "invalid_request", "hit", "unknown", "native_route_candidate"]:
        raise ValueError("Unknown native result status")
    if status in ["invalid_adapter", "invalid_request"]:
        return
    frames, route = value.get("frames"), value.get("route")
    if not isinstance(frames, list) or not isinstance(route, list) or len(frames) != len(route) or value.get("ticks") != len(route):
        raise ValueError("Incomplete per-frame trace")
    json.dumps(value, allow_nan=False)
    if status == "hit" and not frames and (value.get("damage_events", 0) > 0 or value.get("kr_events", 0) > 0):
        return
    last_damage = last_kr = 0
    for i, frame in enumerate(frames, 1):
        if frame.get("tick") != i or not isinstance(frame.get("state"), dict) or not frame["state"]:
            raise ValueError("Missing frame observation")
        damage, kr = frame.get("damage_events"), frame.get("kr_events")
        if type(damage) not in [int, float] or type(kr) not in [int, float] or damage < last_damage or kr < last_kr:
            raise ValueError("Audit counters are not cumulative")
        last_damage, last_kr = damage, kr
    if last_damage != value.get("damage_events") or last_kr != value.get("kr_events"):
        raise ValueError("Final audit differs from trace")
    if status == "native_route_candidate" and (not frames or not value.get("attack_completed") or
            not value.get("contract", {}).get("damage_audit") or last_damage != 0 or last_kr != 0):
        raise ValueError("Unfinished or unaudited no-hit candidate")
    if status == "hit" and last_damage <= 0 and last_kr <= 0:
        # A synchronous hit at begin is allowed, but never a valid control trace.
        if value.get("damage_events", 0) <= 0 and value.get("kr_events", 0) <= 0:
            raise ValueError("Hit result without damage")

def run_native(args, route, label):
    folder = Path(args.output).resolve() / label
    folder.mkdir(parents=True, exist_ok=False)
    request_file, result_file = folder / "request.json", folder / "result.json"
    save(request_file, {"schema": SCHEMA, "seed": args.seed, "route": route,
                       "max_ticks": args.max_ticks, "warmup_ticks": args.warmup_ticks,
                       "settle_ticks": args.settle_ticks, "repeat_last": args.repeat_last,
                       **({"scene": args.scene} if args.scene else {})})
    command = [str(Path(args.godot).resolve()) if os.path.sep in args.godot else args.godot,
               "--headless", "--path", str(args.project), "--script", "res://addons/nohit_live/session.gd",
               "--", "--nohit-request=" + str(request_file), "--nohit-output=" + str(result_file)]
    start = time.perf_counter()
    try:
        completed = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                   timeout=args.timeout, encoding="utf-8", errors="replace")
        log = completed.stdout
        (folder / "native.log").write_text(log, encoding="utf-8")
        if not result_file.is_file():
            return {"status": "runtime_error", "reason": "No result file", "log": str(folder / "native.log")}
        result = read(result_file)
        try:
            validate_result(result)
        except (ValueError, TypeError) as exc:
            result = {"status": "runtime_error", "reason": "Invalid native result: " + str(exc)}
        if "SCRIPT ERROR:" in log or "Parse Error:" in log or completed.returncode not in [0, 2]:
            result = {"status": "runtime_error", "reason": "Native script/process failure; see log"}
    except subprocess.TimeoutExpired as exc:
        output = exc.stdout or b""
        (folder / "native.log").write_text(output.decode(errors="replace") if isinstance(output, bytes) else output)
        result = {"status": "unknown", "reason": "process_timeout_including_cold_start"}
    result["wall_seconds"] = time.perf_counter() - start
    result["record"] = str(result_file)
    save(folder / "run.json", result)
    return result

def same_trace(a, b):
    # Exact exposed values, no tolerance or rounding to conceal a divergence.
    return all(a.get(k) == b.get(k) for k in ["engine", "seed", "initial", "route", "frames", "contract",
               "ticks", "attack_completed", "damage_events", "kr_events"])

def verify(args, candidate):
    before = fingerprint(args.project)
    replay = run_native(args, candidate["route"], "replay")
    control_route = load_route(args.control_route) if args.control_route else [args.control_mask] * args.max_ticks
    control = run_native(args, control_route, "control")
    replay_ok = replay.get("status") == "native_route_candidate" and same_trace(candidate, replay)
    control_ok = control.get("status") == "hit" and bool(control.get("frames")) and (
        control.get("damage_events", 0) > 0 or control.get("kr_events", 0) > 0)
    unchanged = before == fingerprint(args.project)
    return {"schema": "nohit.live.certificate.v1",
            "status": "native_nohit_fresh_process_observed" if replay_ok and control_ok and unchanged
                      else "replay_failed" if not replay_ok or not unchanged else "control_failed",
            "fresh_process_exact_observation_replay": replay_ok,
            "native_damage_control": control_ok, "integration_files_unchanged": unchanged,
            "integration_sha256": before, "route": candidate["route"], "seed": args.seed,
            "candidate_record": candidate["record"], "replay_record": replay.get("record"),
            "control_record": control.get("record"),
            "scope": "Original native frames and adapter-audited damage; observations are not full world snapshots. Applies only to this scene, seed, route and audit scope."}

def portfolio(max_ticks):
    result = [[mask] * max_ticks for mask in [0, 1, 2, 4, 8, 5, 6, 9, 10]]
    for held in [1, 2, 4]:
        result.append([held if (tick // 15) % 2 == 0 else 0 for tick in range(max_ticks)])
    return result

def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)
    installer = sub.add_parser("install", help="Copy live SDK without altering project settings or existing adapter")
    installer.add_argument("project", type=project_path)
    installer.add_argument("--engine", choices=["3", "4"])
    installer.add_argument("--force-addon", action="store_true")
    installer.add_argument("--config", type=Path, help="Declarative adapter config, for games with existing damage/end signals")
    check = sub.add_parser("doctor", help="Static integration checks")
    check.add_argument("project", type=project_path)
    for name in ["run", "verify", "solve"]:
        runner = sub.add_parser(name)
        runner.add_argument("project", type=project_path)
        runner.add_argument("--godot", default="godot")
        runner.add_argument("--output", type=Path, required=True, help="New evidence directory; never overwrite a previous run")
        runner.add_argument("--route", type=Path)
        runner.add_argument("--mask", type=int, default=0)
        runner.add_argument("--seed", type=int, default=1)
        runner.add_argument("--max-ticks", type=int, default=600)
        runner.add_argument("--warmup-ticks", type=int, default=120)
        runner.add_argument("--settle-ticks", type=int, default=2)
        runner.add_argument("--repeat-last", action="store_true")
        runner.add_argument("--scene", help="Optional res:// attack fixture, default project main scene")
        runner.add_argument("--timeout", type=float, default=30)
        runner.add_argument("--workers", type=int, default=min(4, os.cpu_count() or 1))
        runner.add_argument("--control-mask", type=int, default=0)
        runner.add_argument("--control-route", type=Path)
    args = p.parse_args(argv)
    try:
        if args.command == "install":
            result = install(args.project, args.engine, args.force_addon, args.config)
        elif args.command == "doctor":
            result = doctor(args.project)
        else:
            if not 1 <= args.max_ticks <= 1000000 or not 1 <= args.settle_ticks <= 60 or args.timeout <= 0 or not 1 <= args.workers <= 64:
                raise ValueError("Invalid ticks, settle ticks, timeout or workers")
            if not 0 <= args.mask <= 255 or not 0 <= args.control_mask <= 255:
                raise ValueError("Input mask must be 0..255")
            if args.output.exists():
                raise ValueError("Use a NEW output directory: " + str(args.output))
            initial_identity = fingerprint(args.project)
            if args.command == "solve":
                routes = [load_route(args.route)] if args.route else portfolio(args.max_ticks)
                with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
                    futures = [pool.submit(run_native, args, r, f"candidate-{i:03}") for i, r in enumerate(routes)]
                    attempts = [f.result() for f in futures]
                candidates = [r for r in attempts if r.get("status") == "native_route_candidate"]
                result = {"status": "unknown", "search": "finite input portfolio; exhaustion does not prove no solution",
                          "attempts": [{k: r.get(k) for k in ["status", "ticks", "record", "wall_seconds", "reason"]} for r in attempts]}
                if candidates:
                    result.update(verify(args, candidates[0]))
                elif any(r.get("status") in ["invalid_adapter", "runtime_error"] for r in attempts):
                    result["status"] = "invalid_adapter"
            else:
                route = load_route(args.route) if args.route else [args.mask] * args.max_ticks
                result = run_native(args, route, "candidate")
                if args.command == "verify" and result.get("status") == "native_route_candidate":
                    result = verify(args, result)
            if initial_identity != fingerprint(args.project):
                result["status"] = "replay_failed"
                result["reason"] = "Integration changed during execution"
            save(args.output / "summary.json", result)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["status"] in ["installed", "static_ready", "native_route_candidate", "native_nohit_fresh_process_observed"] else 2
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print(json.dumps({"status": "error", "reason": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2

if __name__ == "__main__":
    sys.exit(main())

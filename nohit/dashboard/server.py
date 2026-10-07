"""
nohit.dashboard.server
~~~~~~~~~~~~~~~~~~~~~~
Lightweight HTTP Server providing:
- REST API for wave listing, solving, replaying, and benchmarking.
- Static file serving for the interactive Web/HTML5 dashboard.
"""

from __future__ import annotations

import json
import mimetypes
import os
import sys
import tempfile
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, List
import numpy as np

from nohit.common.constants import DEFAULT_W, DEFAULT_H, DEFAULT_T
from nohit.common.types import BakeResult, PlatformInstance
from nohit.baker.dilator import bake_cspace
from nohit.engine.solver import solve_lattice_dp
from nohit.verifier.replayer import replay_and_verify
from nohit.dashboard.acceptance_clock import validate_compensated_clock
from nohit.benchmark import run_benchmark, create_synthetic_deadlock_wave, create_synthetic_feasible_wave

STATIC_DIR = Path(__file__).resolve().parent / "static"
C2_REPO_DIR = Path(__file__).resolve().parent.parent.parent / "c2-sans-fight"

def extract_hazard_runs(B_hazard: np.ndarray) -> List[List[List[int]]]:
    """Encodes B_hazard into list of [y, x, width] runs per frame for fast Canvas rendering."""
    T, H, W = B_hazard.shape
    frames_runs: List[List[List[int]]] = []
    for t in range(T):
        grid = B_hazard[t]
        runs: List[List[int]] = []
        for y in range(H):
            row = grid[y]
            if not np.any(row):
                continue
            d = np.diff(np.pad(row.astype(np.int8), (1, 1)))
            starts = np.where(d == 1)[0]
            ends = np.where(d == -1)[0]
            for s, e in zip(starts, ends):
                runs.append([int(y), int(s), int(e - s)])
        frames_runs.append(runs)
    return frames_runs


class DashboardHandler(BaseHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(HTTPStatus.NO_CONTENT)
        self.end_headers()

    def do_GET(self):
        url_parts = self.path.split("?")
        url_path = url_parts[0]
        query_str = url_parts[1] if len(url_parts) > 1 else ""

        if url_path.startswith('/api/csv-source/'):
            key = url_path.removeprefix('/api/csv-source/').removesuffix('.csv')
            source = getattr(self.server, 'csv_sources', {}).get(key)
            if source is None:
                self.send_json_error('CSV source expired or not registered', HTTPStatus.NOT_FOUND)
            elif url_path.endswith('.csv'):
                body = source[0]
                self.send_response(HTTPStatus.OK)
                self.send_header('Content-Type', 'text/csv; charset=utf-8')
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            else:
                self.send_json_response(source[1])
        elif url_path.startswith('/api/progress/'):
            # Read-only telemetry for one in-flight solve. An id that was never
            # registered, or has expired, answers with state 'unknown' instead of
            # a 404 so the page can poll one URL for the whole attempt.
            key = url_path.removeprefix('/api/progress/')
            if not key or len(key) > 128:
                self.send_json_error('progress id must be 1..128 characters', HTTPStatus.BAD_REQUEST)
            else:
                from nohit.dashboard.solve_progress import snapshot
                self.send_json_response(snapshot(key))
        elif url_path == "/api/waves":
            self.handle_get_waves()
        elif url_path == "/api/runtime-status":
            self.send_json_response({"startup_ms": getattr(self.server, "startup_ms", None),
                "built_code": os.environ.get("NOHIT_BUILT_RUNTIME") == '1',
                "request_time_compilation_enabled": os.environ.get("NOHIT_BUILT_RUNTIME") != '1',
                "route_cache_separate": True})
        elif url_path == "/api/coverage":
            path = Path(__file__).resolve().parents[2] / "tools" / "real-game" / "coverage-latest.json"
            self.send_json_response(json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"results": []})
        elif url_path == "/api/benchmark":
            self.handle_get_benchmark()
        elif url_path == "/api/tas":
            self.handle_get_tas(query_str)
        elif url_path == "/game" or url_path == "/game/" or url_path.startswith("/game/"):
            self.serve_game_file(url_path)
        else:
            self.serve_static_file(url_path)

    def do_POST(self):
        url_path = self.path.split("?")[0]
        if url_path == "/api/coverage":
            from datetime import datetime, timezone
            import re
            size = int(self.headers.get("Content-Length", 0))
            if size <= 0 or size > 8_000_000:
                self.send_json_error("Invalid coverage size", HTTPStatus.BAD_REQUEST)
                return
            try:
                data = json.loads(self.rfile.read(size).decode("utf-8"))
                results = data["results"]
                names = [r["wave"] for r in results]
                known = {p.name for p in C2_REPO_DIR.glob("sans_*.csv")}
                if len(names) != len(set(names)) or not set(names) <= known:
                    raise ValueError("Coverage contains duplicate or unknown waves")
                if not all(re.fullmatch(r"sans_[a-z0-9_]+\.csv", name) for name in names):
                    raise ValueError("Invalid wave")
                data["recorded_at"] = datetime.now(timezone.utc).isoformat()
                data["runtime_coverage_only"] = True
                folder = Path(__file__).resolve().parents[2] / "tools" / "real-game"
                folder.mkdir(parents=True, exist_ok=True)
                path = folder / "coverage-latest.json"
                temporary = path.with_suffix(".tmp")
                temporary.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
                temporary.replace(path)
                self.send_json_response({"path": str(path), "count": len(results)})
            except Exception as e:
                self.send_json_error(str(e), HTTPStatus.BAD_REQUEST)
            return
        if url_path == "/api/oracle-plan":
            import hashlib
            size = int(self.headers.get("Content-Length", 0))
            if size <= 0 or size > 8_000_000:
                self.send_json_error("Invalid plan size", HTTPStatus.BAD_REQUEST)
                return
            try:
                data = json.loads(self.rfile.read(size).decode("utf-8"))
                wave = str(data["wave"])
                import re
                if not re.fullmatch(r"sans_[a-z0-9_]+\.csv", wave):
                    raise ValueError("Invalid wave")
                if data["result"]["status"] != "candidate_found":
                    raise ValueError("Only a completed candidate can be loaded")
                seed = data.get("seed")
                if seed is not None and (type(seed) is not int or not 0 <= seed < 2**32):
                    raise ValueError("Seed must be an unsigned 32-bit integer")
                result = data["result"]
                actions = result["actions"]
                if not actions or not all((type(a) is int and 0 <= a <= 31) or
                    (isinstance(a, list) and len(a) == 2 and all(type(v) is int and v in (-1, 0, 1) for v in a)) for a in actions):
                    raise ValueError("Invalid original-engine inputs")
                if len(result["trajectory"]) != len(actions) + 1 or not result["end"]["ended"]:
                    raise ValueError("Candidate is not a complete original-engine route")
                if not all(row["HP"] == 92 and row["KR"] == 0 for row in result["trajectory"]):
                    raise ValueError("Candidate contains original-engine damage")
                for key, path in (("csv_sha256", C2_REPO_DIR / wave), ("runtime_sha256", C2_REPO_DIR / "c2runtime.js"), ("data_sha256", C2_REPO_DIR / "data.js")):
                    data[key] = hashlib.sha256(path.read_bytes()).hexdigest()
                folder = Path(__file__).resolve().parents[2] / "tools" / "oracle-plans"
                folder.mkdir(parents=True, exist_ok=True)
                identity = [wave, seed, data["csv_sha256"], data["runtime_sha256"], data["data_sha256"], actions]
                candidate_id = hashlib.sha256(json.dumps(identity, separators=(",", ":")).encode("utf-8")).hexdigest()
                data["candidate_id"] = candidate_id
                path = folder / (wave.removesuffix(".csv") + "-" + str(seed) + "-candidate-" + candidate_id + ".json")
                path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
                self.send_json_response({"path": str(path), "candidate_id": candidate_id, "active": False, "realtime_accepted": False})
            except Exception as e:
                self.send_json_error(str(e), HTTPStatus.BAD_REQUEST)
            return
        if url_path == "/api/acceptance-evidence":
            size = int(self.headers.get("Content-Length", 0))
            if size <= 0 or size > 8_000_000:
                self.send_json_error("Invalid evidence part size", HTTPStatus.BAD_REQUEST)
                return
            try:
                from nohit.dashboard.acceptance_evidence import store_evidence_part
                data = json.loads(self.rfile.read(size).decode("utf-8"))
                folder = Path(__file__).resolve().parents[2] / "tools" / "real-game"
                self.send_json_response(store_evidence_part(data, folder))
            except Exception as e:
                self.send_json_error(str(e), HTTPStatus.BAD_REQUEST)
            return
        if url_path == "/api/acceptance":
            # Persist observations of the real game, independently of the
            # Python solver/verifier. This server binds to loopback only.
            import base64
            from datetime import datetime
            size = int(self.headers.get("Content-Length", 0))
            if size <= 0 or size > 8_000_000:
                self.send_json_error("Invalid trace size", HTTPStatus.BAD_REQUEST)
                return
            try:
                data = json.loads(self.rfile.read(size).decode("utf-8"))
                folder = Path(__file__).resolve().parents[2] / "tools" / "real-game"
                folder.mkdir(parents=True, exist_ok=True)
                stem = "bonesgap1-" + datetime.now().strftime("%Y%m%d-%H%M%S-%f")
                trace = folder / (stem + ".json")
                screenshot = data.pop("screenshot", None)
                candidate_id = data.get("candidate_id")
                if candidate_id and data.get("result", {}).get("passed"):
                    import re
                    import hashlib
                    wave = str(data["wave"])
                    seed = data.get("seed")
                    runs = data["trace"]["runs"]
                    if (not re.fullmatch(r"sans_[a-z0-9_]+\.csv", wave) or
                            not re.fullmatch(r"[0-9a-f]{64}", candidate_id) or
                            seed is not None and (type(seed) is not int or not 0 <= seed < 2**32) or
                            data.get("clock") not in {"original-runtime-realtime","original-runtime-realtime-catchup-240hz"} or len(runs) != 3):
                        raise ValueError("Invalid real-time candidate acceptance")
                    if not all(r["startHP"] == 92 and r["end"]["HP"] == 92 and r["end"]["endAttackObserved"] and not r["hits"] and r["rows"] and
                               all(row["HP"] == 92 and row["KR"] == 0 for row in r["rows"]) for r in runs):
                        raise ValueError("Candidate did not complete three no-damage rounds")
                    validate_compensated_clock(data)
                    plan_folder = folder.parent / "oracle-plans"
                    base = wave.removesuffix(".csv") + "-" + str(seed)
                    candidate_path = plan_folder / (base + "-candidate-" + candidate_id + ".json")
                    candidate = json.loads(candidate_path.read_text(encoding="utf-8"))
                    if data["plan"]["actions"] != candidate["result"]["actions"]:
                        raise ValueError("Observed plan differs from the candidate")
                    for key, game_path in (("csv_sha256", C2_REPO_DIR / wave), ("runtime_sha256", C2_REPO_DIR / "c2runtime.js"), ("data_sha256", C2_REPO_DIR / "data.js")):
                        if candidate[key] != hashlib.sha256(game_path.read_bytes()).hexdigest():
                            raise ValueError("Original game source changed during acceptance")
                    candidate["realtime_acceptance_trace"] = trace.name
                    candidate["realtime_clock"] = data["clock"]
                    candidate["compensation"] = data.get("compensation")
                    candidate["realtime_accepted"] = True
                    active_path = plan_folder / (base + ".json")
                    active_path.write_text(json.dumps(candidate, ensure_ascii=False), encoding="utf-8")
                    data["promoted_candidate"] = str(active_path)
                    matrix_path = folder / "coverage-latest.json"
                    if matrix_path.exists():
                        matrix = json.loads(matrix_path.read_text(encoding="utf-8"))
                        matrix.setdefault("acceptance", {})[wave] = {"status": "passed_three", "seed": seed,
                            "candidate_id": candidate_id, "trace": trace.name,
                            "clock": data["clock"], "compensation": data.get("compensation"), "rounds": [
                                {"start_hp": r["startHP"], "min_hp": min(x["HP"] for x in r["rows"]),
                                 "end_hp": r["end"]["HP"], "max_kr": max(x["KR"] for x in r["rows"]),
                                 "hits": len(r["hits"]), "end_attack_observed": True} for r in runs]}
                        matrix_path.write_text(json.dumps(matrix, ensure_ascii=False), encoding="utf-8")
                if data.get('suite') == 'continuous-normal-game':
                    import hashlib
                    from nohit.dashboard.acceptance_evidence import read_evidence_manifest
                    from nohit.dashboard.csv_api import implementation_hashes
                    observed = read_evidence_manifest(data, folder)
                    data['solver_source_sha256'] = implementation_hashes()
                    source_names = ['c2runtime.js', 'data.js', 'attack_seed.js', 'tas_runner.js',
                                    'full_game_runner.js', 'full_game_acceptance.js', 'lag_compensation.js',
                                    'menu_controller.js', 'solver_state.js', 'csv_round_controller.js']
                    data['source_sha256'] = {name:hashlib.sha256((C2_REPO_DIR / name).read_bytes()).hexdigest()
                                             for name in source_names}
                    data['script_sha256'] = {path.name:hashlib.sha256(path.read_bytes()).hexdigest()
                                             for path in C2_REPO_DIR.glob('sans_*.csv')}
                    data['script_text_sha256'] = {path.name:hashlib.sha256(
                        path.read_bytes().decode('utf-8-sig').replace('\r\n', '\n').encode('utf-8')).hexdigest()
                        for path in C2_REPO_DIR.glob('sans_*.csv')}
                    if observed.get('result', {}).get('passed') and (
                        not observed.get('winObserved') or observed.get('firstDamage') or observed.get('tickGaps') or
                        observed.get('clockErrors') or observed.get('protocolErrors') or not observed.get('checkedTicks') or
                        any(row['HP'] != 92 or row['KR'] != 0 for row in observed.get('rows', []))):
                        raise ValueError('Continuous game record does not satisfy no-hit victory')
                trace.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
                if screenshot:
                    (folder / (stem + ".png")).write_bytes(base64.b64decode(screenshot, validate=True))
                self.send_json_response({"trace": str(trace), "screenshot": str(folder / (stem + ".png")) if screenshot else None})
            except Exception as e:
                self.send_json_error(str(e), HTTPStatus.BAD_REQUEST)
            return
        if url_path in ("/api/solve", "/api/solve-csv", "/api/csv-source"):
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)
            try:
                data = json.loads(body.decode("utf-8"))
            except Exception as e:
                self.send_json_error(f"Invalid JSON: {e}", HTTPStatus.BAD_REQUEST)
                return
            if url_path == '/api/csv-source':
                try:
                    from nohit.dashboard.csv_source import register_csv_source
                    if not hasattr(self.server, 'csv_sources'):
                        self.server.csv_sources = {}
                    self.send_json_response(register_csv_source(data, self.server.csv_sources))
                except (ValueError, TypeError, OSError) as error:
                    self.send_json_error(str(error), HTTPStatus.BAD_REQUEST)
            elif url_path == "/api/solve-csv":
                try:
                    from nohit.dashboard.csv_api import solve_csv_request
                    self.send_json_response(solve_csv_request(data))
                except (ValueError, TypeError, OSError) as error:
                    self.send_json_error(str(error), HTTPStatus.BAD_REQUEST)
                except Exception as error:
                    self.send_json_error(str(error), HTTPStatus.INTERNAL_SERVER_ERROR)
            else:
                self.handle_post_solve(data)
        else:
            self.send_json_error("Not Found", HTTPStatus.NOT_FOUND)

    def handle_get_waves(self):
        waves = []
        if C2_REPO_DIR.exists():
            for p in sorted(C2_REPO_DIR.glob("sans_*.csv")):
                waves.append({
                    "id": p.name,
                    "name": p.stem.replace("sans_", "").replace("_", " ").title(),
                    "category": "C2 Attack Script",
                    "file": p.name,
                })

        # Add synthetic presets
        waves.extend([
            {
                "id": "preset_platform_ferry",
                "name": "Moving Platform Ferry (Solvable)",
                "category": "Synthetic Feasible",
                "file": None,
            },
            {
                "id": "preset_deadlock_spikes",
                "name": "Full Spikes at t=15 (Deadlock)",
                "category": "Synthetic Deadlock",
                "file": None,
            },
            {
                "id": "preset_deadlock_sweeper",
                "name": "Wall Sweeper at t=20 (Deadlock)",
                "category": "Synthetic Deadlock",
                "file": None,
            },
            {
                "id": "preset_deadlock_eruption",
                "name": "Floor & Ceiling Eruption (Deadlock)",
                "category": "Synthetic Deadlock",
                "file": None,
            },
        ])

        self.send_json_response({"waves": waves})

    def handle_get_benchmark(self):
        try:
            results = run_benchmark(c2_repo_dir=C2_REPO_DIR, verbose=False)
            rows = [
                {
                    "name": r.name,
                    "category": r.category,
                    "outcome": f"No candidate @ t={r.deadlock_frame}" if r.is_deadlock else "Model candidate (game unverified)",
                    "bake_ms": round(r.bake_time_ms, 2),
                    "dp_ms": round(r.dp_time_ms, 2),
                    "total_ms": round(r.total_time_ms, 2),
                    "peak_states": r.peak_states,
                    "peak_memory_mb": round(r.peak_memory_mb, 2),
                    "verified": r.verified,
                }
                for r in results
            ]
            self.send_json_response({"benchmark": rows})
        except Exception as e:
            self.send_json_error(str(e), HTTPStatus.INTERNAL_SERVER_ERROR)

    def handle_post_solve(self, data: Dict[str, Any]):
        wave_id = data.get("wave")
        custom_csv = data.get("custom_csv")
        T = int(data.get("T", DEFAULT_T))

        try:
            if custom_csv:
                with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, encoding="utf-8") as tmp:
                    tmp.write(custom_csv)
                    tmp_path = tmp.name
                try:
                    bake = bake_cspace(tmp_path, T=T)
                finally:
                    if os.path.exists(tmp_path):
                        os.unlink(tmp_path)
            elif wave_id == "preset_platform_ferry":
                bake = create_synthetic_feasible_wave(T=T)
            elif wave_id == "preset_deadlock_spikes":
                bake = create_synthetic_deadlock_wave(1, T=min(T, 40))
            elif wave_id == "preset_deadlock_sweeper":
                bake = create_synthetic_deadlock_wave(2, T=min(T, 40))
            elif wave_id == "preset_deadlock_eruption":
                bake = create_synthetic_deadlock_wave(3, T=min(T, 40))
            else:
                csv_path = C2_REPO_DIR / wave_id
                if not csv_path.exists():
                    self.send_json_error(f"Wave {wave_id} not found", HTTPStatus.NOT_FOUND)
                    return
                bake = bake_cspace(csv_path, T=T)

            # Solve lattice DP
            sol = solve_lattice_dp(bake)

            # Local model agreement is not actual game acceptance.
            verified = False
            collision_frames = []

            # Extract platform instances per frame
            platforms_by_frame = []
            for t in range(bake.T):
                plats = [
                    {
                        "id": p.plat_id,
                        "x_left": p.x_left,
                        "x_right": p.x_right,
                        "y_surf": p.y_surf,
                        "vx": p.vx,
                    }
                    for p in bake.platform_table[t]
                ]
                platforms_by_frame.append(plats)

            # Extract hazard runs for canvas rendering
            hazard_runs = extract_hazard_runs(bake.B_hazard)

            response_data = {
                "is_deadlock": None,
                "deadlock_proven": False,
                "deadlock_frame": None,
                "search_exhausted_frame": sol.deadlock_frame,
                "candidate_found": not sol.is_deadlock,
                "search_status": "model_candidate" if not sol.is_deadlock else "no_candidate",
                "search_limited": True,
                "realtime_accepted": False,
                "stats": {
                    "bake_ms": round(sol.stats.bake_time_ms, 2),
                    "dp_ms": round(sol.stats.dp_solve_time_ms, 2),
                    "total_ms": round(sol.stats.total_time_ms, 2),
                    "peak_states": sol.stats.peak_alive_states,
                    "alive_history": sol.stats.alive_states_history,
                    "peak_memory_mb": round(sol.stats.peak_memory_mb, 2),
                },
                "action_sequence": sol.action_sequence,
                "trajectory": sol.trajectory,
                "verified": verified,
                "collision_frames": collision_frames,
                "initial_state": list(bake.initial_state),
                "T": bake.T,
                "W": bake.W,
                "H": bake.H,
                "platforms": platforms_by_frame,
                "hazard_runs": hazard_runs,
                "slam_frames": list(bake.metadata.get("slam_frames", [])),
            }
            self.send_json_response(response_data)
        except Exception as e:
            import traceback
            traceback.print_exc()
            self.send_json_error(str(e), HTTPStatus.INTERNAL_SERVER_ERROR)

    def handle_get_tas(self, query_str: str):
        import urllib.parse
        params = urllib.parse.parse_qs(query_str)
        wave_name = params.get("wave", ["sans_bonegap1.csv"])[0]
        import re
        if not re.fullmatch(r"sans_[a-z0-9_]+\.csv", wave_name):
            self.send_json_error("Invalid wave", HTTPStatus.BAD_REQUEST)
            return
        T_param = params.get("T", [None])[0]
        # T == 0 (or omitted) means "cover the whole attack". The script's own
        # EndAttack timestamp defines the horizon; the legacy default of 150
        # frames silently truncated every round to ~38% of its length.
        T = int(T_param) if T_param not in (None, "", "0") else 0
        soul_w = int(params.get("soul_w", [4])[0])
        soul_h = int(params.get("soul_h", [4])[0])
        try:
            attack_seed = int(params["seed"][0]) if "seed" in params else None
            if attack_seed is not None and not 0 <= attack_seed <= 0xffffffff:
                raise ValueError()
        except ValueError:
            self.send_json_error("seed must be an integer from 0 to 4294967295", HTTPStatus.BAD_REQUEST)
            return
        # In-game matching physics: Construct 2 heart kernel by default.
        physics_mode = params.get("physics_mode", ["c2"])[0]
        operator = params.get("operator", ["baseline"])[0]
        if operator not in ("baseline", "a", "b"):
            self.send_json_error("operator must be baseline, a or b", HTTPStatus.BAD_REQUEST)
            return
        if physics_mode not in ("docs", "c2"):
            self.send_json_error(
                f"physics_mode must be 'docs' or 'c2', got {physics_mode!r}", HTTPStatus.BAD_REQUEST
            )
            return

        csv_path = C2_REPO_DIR / wave_name
        if not csv_path.exists():
            self.send_json_error(f"Wave {wave_name} not found", HTTPStatus.NOT_FOUND)
            return

        # All fresh TAS requests use one mathematical search core. A named
        # candidate may be loaded only for independent original-game replay.
        if not params.get('candidate'):
            if physics_mode != 'c2' or T != 0 or soul_w != 4 or soul_h != 4:
                self.send_json_response({'wave':wave_name,'candidate_found':False,
                    'planner':'canonical-dag-dp','search_status':'unsupported_configuration',
                    'deadlock_proven':False,'detail':'TAS requires the full original attack and original 4x4 hitbox'})
                return
            from nohit.engine.canonical_solver import solve_attack
            try:
                initial = json.loads(params['initial'][0]) if 'initial' in params else None
                initial_environment = json.loads(params['initial_environment'][0]) if 'initial_environment' in params else None
                if initial_environment is not None:
                    import math
                    if (not isinstance(initial_environment, list) or len(initial_environment) not in (18, 22) or
                            any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in initial_environment)):
                        raise ValueError('initial_environment must contain 18 or 22 finite numeric values')
                clock_start_ms = float(params['clock_start_ms'][0]) if 'clock_start_ms' in params else None
                if clock_start_ms is not None:
                    import math
                    if not math.isfinite(clock_start_ms) or clock_start_ms < 0:
                        raise ValueError('clock_start_ms must be a finite nonnegative number')
                max_nodes = int(params.get('max_nodes', ['500000'])[0])
                if not 1 <= max_nodes <= 2000000:
                    raise ValueError('max_nodes must be between 1 and 2000000')
                margin = float(params.get('margin', ['4'])[0])
                if not 0 <= margin <= 8:
                    raise ValueError('margin must be finite and between 0 and 8')
                lookahead = int(params.get('lookahead', ['60'])[0])
                decision_ticks = int(params.get('decision_ticks', ['4'])[0])
                if decision_ticks not in (1,4):
                    raise ValueError('decision_ticks must be 1 or 4')
                max_ticks = int(params.get('max_ticks',['40000'])[0])
                if not 1 <= max_ticks <= 2000000:
                    raise ValueError('max_ticks must be between 1 and 2000000')
                termination_policy = params.get('termination_policy',['endattack'])[0]
                if termination_policy not in ('endattack','eof_hazards_drained'):
                    raise ValueError('invalid termination_policy')
                weights = json.loads(params['weights'][0]) if 'weights' in params else None
                raw_cancel = params.get('allow_cancel', ['1'])[0]
                if raw_cancel not in ('0','1'):
                    raise ValueError('allow_cancel must be 0 or 1')
                extra = {'clock_start_ms':clock_start_ms} if clock_start_ms is not None else {}
                if raw_cancel == '0': extra['allow_cancel'] = False
                if 'lookahead_policy' in params:
                    extra['lookahead_policy'] = params['lookahead_policy'][0]
                # One solver and one safety predicate. A poor optional score
                # must not spend the entire automatic-run budget ordering the
                # same graph. Explicit user weights retain their chosen order.
                import time
                search_started = time.perf_counter()
                adaptive_order = weights is None and 'lookahead_policy' not in params and max_nodes > 50000
                first_budget = 50000 if adaptive_order else max_nodes
                common = dict(seed=42 if attack_seed is None else attack_seed,
                              margin=margin, lookahead=lookahead,
                              decision_ticks=decision_ticks,
                              max_ticks=max_ticks,termination_policy=termination_policy,
                              initial_environment=initial_environment, **extra)
                result = solve_attack(csv_path, initial, max_nodes=first_budget, weights=weights, **common)
                def attempt_record(attempt, budget, allow_cancel=raw_cancel == '1'):
                    return dict(status=attempt['status'], max_nodes=budget,
                                weights=attempt.get('ranking_weights'),
                                lookahead_policy=attempt.get('lookahead_policy','navigation'),
                                lookahead=attempt.get('lookahead',lookahead),
                                allow_cancel=allow_cancel,
                                reached_frame=attempt.get('frame',0),
                                expansions=attempt.get('expansions', 0),
                                timing_ms=attempt.get('timing_ms'))
                attempts = [attempt_record(result, first_budget)]
                if adaptive_order and result['status'] == 'resource_limit':
                    remaining = max_nodes - first_budget
                    profiles = [
                        (dict.fromkeys(('clearance','lookahead','center','switches'), 0.), 'navigation', lookahead, raw_cancel == '1', 50000)]
                    profiles.extend((dict(clearance=0.,lookahead=1.,center=1.,switches=0.), 'coast', horizon, raw_cancel == '1', 50000)
                                    for horizon in dict.fromkeys((lookahead,120,240)))
                    if raw_cancel == '1':
                        # Prioritize the no-slow-key subgraph of the same
                        # operator before spending the remaining full-graph
                        # budget. Its failure never proves the full graph dead.
                        profiles.append((dict.fromkeys(('clearance','lookahead','center','switches'), 0.),
                                         'navigation', lookahead, False, 200000))
                    subset_finished = False
                    for ordered_weights, policy, horizon, allow_cancel, trial_budget in profiles:
                        if remaining <= 0 or result['status'] != 'resource_limit': break
                        budget = min(trial_budget, remaining)
                        result = solve_attack(csv_path, initial, max_nodes=budget, weights=ordered_weights,
                                              **dict(common,lookahead_policy=policy,lookahead=horizon,allow_cancel=allow_cancel))
                        attempts.append(attempt_record(result,budget,allow_cancel))
                        remaining -= budget
                        subset_finished = raw_cancel == '1' and not allow_cancel and result['status'] == 'exhausted_in_declared_model'
                    if remaining > 0 and (result['status'] == 'resource_limit' or subset_finished):
                        # Progress is a scheduling hint, never a proof that the
                        # retained prefix can finish or that other paths fail.
                        best = max((a for a in attempts if a['allow_cancel'] == (raw_cancel == '1')),
                                   key=lambda a:a['reached_frame'])
                        result = solve_attack(csv_path, initial,max_nodes=remaining,weights=best['weights'],
                                              **dict(common,lookahead_policy=best['lookahead_policy'],lookahead=best['lookahead']))
                        attempts.append(attempt_record(result,remaining))
                    elif subset_finished:
                        result = dict(result,status='resource_limit',search_limited=True,
                                      deadlock_proven=False,complete_in_original_game=False)
                result['evaluation_attempts'] = attempts
                result['requested_max_nodes'] = max_nodes
                result['total_expansions'] = sum(a['expansions'] for a in attempts)
                result['automatic_order_changed'] = len(attempts) > 1
                if result.get('timing_ms'):
                    result['timing_ms'] = dict(result['timing_ms'],
                        first_route_wall=(time.perf_counter()-search_started)*1000)
            except (ValueError, TypeError) as error:
                self.send_json_error(str(error), HTTPStatus.BAD_REQUEST)
                return
            found = result['status'] == 'candidate_found'
            from nohit.engine.execution_schedule import execution_schedule
            execution = execution_schedule(result) if found else dict(actions=result['actions'],
                control_ticks=result.get('control_ticks',4),control_hz=result.get('control_hz',60),
                trajectory=result.get('trajectory',[]),has_terminal_tail=False)
            self.send_json_response(dict(result, candidate_found=found, search_status=result['status'],
                physics_mode='c2', fps=execution['control_hz'], is_deadlock=None, cache_hit=False,
                solver_control_ticks=result.get('control_ticks',4),control_ticks=execution['control_ticks'],
                control_hz=execution['control_hz'],execution_includes_terminal_tail=execution['has_terminal_tail'],
                solver_actions=result['actions'],actions=execution['actions'],action_sequence=execution['actions'],
                trajectory=[[s[0],480-s[1],s[3]*40/60,0,0] for s in execution['trajectory']],
                arena={'c2_left':0,'c2_floor':480,'W':640,'H':480,'soul_w':4,'soul_h':4,'v_walk':150,'v_jump':180}))
            return
        # Their fixed-step replay is still distinct from real-time acceptance.
        candidate_id = params.get("candidate", [None])[0]
        if candidate_id is not None and not re.fullmatch(r"[0-9a-f]{64}", candidate_id):
            self.send_json_error("Invalid candidate ID", HTTPStatus.BAD_REQUEST)
            return
        oracle_path = Path(__file__).resolve().parents[2] / "tools" / "oracle-plans" / (
            wave_name.removesuffix(".csv") + "-" + str(attack_seed) +
            ("-candidate-" + candidate_id if candidate_id else "") + ".json")
        if candidate_id and not oracle_path.exists():
            self.send_json_error("Candidate not found for this wave and seed", HTTPStatus.NOT_FOUND)
            return
        if oracle_path.exists() and physics_mode == "c2" and T == 0:
            import hashlib
            data = json.loads(oracle_path.read_text(encoding="utf-8"))
            if (data.get("csv_sha256") == hashlib.sha256(csv_path.read_bytes()).hexdigest() and
                data.get("runtime_sha256") == hashlib.sha256((C2_REPO_DIR / "c2runtime.js").read_bytes()).hexdigest() and
                data.get("data_sha256") == hashlib.sha256((C2_REPO_DIR / "data.js").read_bytes()).hexdigest()):
                result = data["result"]
                obs = result["trajectory"]
                self.send_json_response({"wave": wave_name, "seed": attack_seed, "T":len(obs), "fps":60,
                    "planner":data.get("planner", "original-engine-branch-candidate"), "candidate_found":True,
                    "search_status":"candidate_found", "is_deadlock":None, "deadlock_proven":False,
                    "search_limited":result.get("search_limited", True),"realtime_accepted":bool(data.get("realtime_accepted")),"physics_mode":"c2","cache_hit":True,
                    "candidate_id":data.get("candidate_id"),"realtime_acceptance_trace":data.get("realtime_acceptance_trace"),
                    "action_sequence":result["actions"],
                    "trajectory":[[r["x"],480-r["y"],r.get("dy",0)*40/60,0,0] for r in obs],
                    "arena":{"c2_left":0,"c2_floor":480,"W":640,"H":480,"soul_w":4,"soul_h":4,"v_walk":150,"v_jump":180},
                    "stats":{"bake_ms":0,"dp_ms":result.get("ms",0),"total_ms":result.get("ms",0),"peak_states":result.get("beam")},
                    "planning":{"margin_px":result.get("marginPx"),"native_runtime":True}})
                return

        self.send_json_error("Candidate source hashes do not match the current original game", HTTPStatus.CONFLICT)

    def serve_game_file(self, url_path: str):
        if url_path in ("/game", "/game/"):
            rel_path = "index.html"
        else:
            rel_path = url_path[len("/game/"):].lstrip("/")

        file_path = (C2_REPO_DIR / rel_path).resolve()
        if not str(file_path).startswith(str(C2_REPO_DIR.resolve())):
            self.send_json_error("Forbidden", HTTPStatus.FORBIDDEN)
            return

        if not file_path.exists() or file_path.is_dir():
            self.send_json_error("Not Found", HTTPStatus.NOT_FOUND)
            return

        mime_type, _ = mimetypes.guess_type(str(file_path))
        if mime_type is None:
            if file_path.suffix == ".csv":
                mime_type = "text/plain"
            elif file_path.suffix == ".json":
                mime_type = "application/json"
            else:
                mime_type = "application/octet-stream"

        # The game is developed in place here: tas_runner.js and the C2 data files
        # are edited between runs, and a cached copy silently measures the OLD
        # code (that happened with the tick-phase fix). Never let the browser
        # serve a stale build.
        try:
            with open(file_path, "rb") as f:
                content = f.read()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", mime_type)
            self.send_header("Content-Length", str(len(content)))
            self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
            self.send_header("Pragma", "no-cache")
            self.end_headers()
            self.wfile.write(content)
        except Exception as e:
            self.send_json_error(str(e), HTTPStatus.INTERNAL_SERVER_ERROR)

    def serve_static_file(self, rel_path: str):
        if rel_path in ("/", ""):
            rel_path = "index.html"
        clean_path = rel_path.lstrip("/")
        file_path = (STATIC_DIR / clean_path).resolve()

        if not str(file_path).startswith(str(STATIC_DIR)):
            self.send_json_error("Forbidden", HTTPStatus.FORBIDDEN)
            return

        if not file_path.exists() or file_path.is_dir():
            self.send_json_error("Not Found", HTTPStatus.NOT_FOUND)
            return

        mime_type, _ = mimetypes.guess_type(str(file_path))
        if mime_type is None:
            mime_type = "application/octet-stream"

        try:
            with open(file_path, "rb") as f:
                content = f.read()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", mime_type)
            self.send_header("Content-Length", str(len(content)))
            self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
            self.end_headers()
            self.wfile.write(content)
        except Exception as e:
            self.send_json_error(str(e), HTTPStatus.INTERNAL_SERVER_ERROR)

    def send_json_response(self, data: Any):
        payload = json.dumps(data).encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def send_json_error(self, message: str, status: HTTPStatus):
        payload = json.dumps({"error": message}).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


def start_server(port: int = 8080, host: str = "127.0.0.1") -> ThreadingHTTPServer:
    # Compile/load machine code once before accepting solve requests. Route
    # searches still run afresh; startup compilation is not a route cache hit.
    from numba import types
    from nohit.engine.source_compiled import _search, _clearance, _clearance_anchors
    _clearance.compile((types.Array(types.boolean, 3, 'C'),))
    _clearance_anchors.compile((types.Array(types.boolean, 3, 'C'),))
    for dtype in (types.uint8, types.uint16):
        _search.compile((types.Array(types.boolean, 3, 'C'), types.Array(types.boolean, 3, 'C'),
                     types.Array(dtype, 3, 'C'), types.Array(dtype, 3, 'C'),
                     types.boolean, types.float64, types.int64, types.int64, types.boolean,
                     types.Array(types.float64, 3, 'C'), types.float64, types.float64, types.int64))
    if os.environ.get('NOHIT_BUILT_RUNTIME') == '1':
        for dispatcher in (_search, _clearance, _clearance_anchors):
            if sum(dispatcher._cache_misses.values()):
                raise RuntimeError('Built code was not loaded; rebuild with tools/build_kernels.py')
            dispatcher.disable_compile()
    server = ThreadingHTTPServer((host, port), DashboardHandler)
    return server


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8080
    server = start_server(port=port)
    print(f">> Sans Bullet Hell Lattice Verification Dashboard running at http://127.0.0.1:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n>> Shutting down server.")
        server.server_close()

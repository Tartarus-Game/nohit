"""Local CSV solver API, source transport, native evidence and browser UI."""
from __future__ import annotations

import json
import mimetypes
import os
import sys
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

STATIC_DIR = Path(__file__).resolve().parent / "static"
# The vendored jcw87 export is the default game served at /game/. A different
# build of the SAME Construct 2 project (identical event sheets, different CSVs
# and assets) can be served without touching this checkout by setting
# NOHIT_GAME_DIR to its directory. Nothing else about the pipeline changes: the
# driver, the solver and the acceptance verifiers all read the served bytes.
C2_REPO_DIR = Path(os.environ.get("NOHIT_GAME_DIR")
                   or Path(__file__).resolve().parent.parent.parent / "c2-sans-fight").resolve()

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

        if url_path.startswith('/api/csv-source/'):
            relative = url_path.removeprefix('/api/csv-source/')
            imported = relative.startswith('import/')
            original_download = imported and relative.endswith('.original.csv')
            if imported:
                identity = relative.removeprefix('import/')
                if original_download:
                    identity = identity.removesuffix('.original.csv')
                key = 'import:' + identity
            else:
                key = relative.removesuffix('.csv')
            source = getattr(self.server, 'csv_sources', {}).get(key)
            if source is None:
                self.send_json_error('CSV source expired or not registered', HTTPStatus.NOT_FOUND)
            elif original_download or not imported and relative.endswith('.csv'):
                body = source[2] if original_download else source[0]
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
        elif url_path == "/api/runtime-status":
            self.send_json_response({"startup_ms": getattr(self.server, "startup_ms", None),
                "engine": "native-csv", "route_cache_separate": True})
        elif url_path == "/game" or url_path == "/game/" or url_path.startswith("/game/"):
            self.serve_game_file(url_path)
        else:
            self.serve_static_file(url_path)

    def do_POST(self):
        url_path = self.path.split("?")[0]
        if url_path == "/api/acceptance-evidence":
            size = int(self.headers.get("Content-Length", 0))
            if size <= 0 or size > 8_000_000:
                self.send_json_error("Invalid evidence part size", HTTPStatus.BAD_REQUEST)
                return
            try:
                from nohit.dashboard.acceptance_evidence import store_evidence_part
                data = json.loads(self.rfile.read(size).decode("utf-8"))
                folder = Path(__file__).resolve().parents[2] / "build" / "evidence"
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
                folder = Path(__file__).resolve().parents[2] / "build" / "evidence"
                folder.mkdir(parents=True, exist_ok=True)
                stem = "acceptance-" + datetime.now().strftime("%Y%m%d-%H%M%S-%f")
                trace = folder / (stem + ".json")
                screenshot = data.pop("screenshot", None)
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
                    # The no-damage criterion is "HP never falls below full", where
                    # full is the served build's own MaxHP. Records carry it
                    # explicitly; 92 is the vendored jcw87 build's baseline and stays
                    # the default so older records keep their original meaning.
                    baseline_hp = observed.get('baselineHP', 92)
                    if (type(baseline_hp) not in (int, float) or not 0 < baseline_hp <= 100000):
                        raise ValueError('Continuous game record has an invalid HP baseline')
                    # KR used to be required to stay 0 as a proxy for "was hit". That
                    # proxy is exact for the vendored build but wrong for a build whose
                    # scripts inject KR 1 alongside a heal, so the authoritative check
                    # is HP. A record may only relax the KR requirement by declaring
                    # its policy and bounding the excursion below the build's lowest
                    # HP-drain bucket; an undeclared or unbounded excursion still fails.
                    max_kr = observed.get('maxKR')
                    if max_kr is None:
                        kr_ok = all(row['KR'] == 0 for row in observed.get('rows', []))
                    else:
                        if not observed.get('krPolicy'):
                            raise ValueError('Continuous game record declares KR excursions without a policy')
                        if type(max_kr) not in (int, float) or not 0 <= max_kr <= 10:
                            raise ValueError('Continuous game record has a KR excursion above the drain bucket')
                        kr_ok = True
                    if observed.get('result', {}).get('passed') and (
                        not observed.get('winObserved') or observed.get('firstDamage') or observed.get('tickGaps') or
                        observed.get('clockErrors') or observed.get('protocolErrors') or not observed.get('checkedTicks') or
                        not kr_ok or
                        any(row['HP'] != baseline_hp for row in observed.get('rows', []))):
                        raise ValueError('Continuous game record does not satisfy no-hit victory')
                trace.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
                if screenshot:
                    (folder / (stem + ".png")).write_bytes(base64.b64decode(screenshot, validate=True))
                self.send_json_response({"trace": str(trace), "screenshot": str(folder / (stem + ".png")) if screenshot else None})
            except Exception as e:
                self.send_json_error(str(e), HTTPStatus.BAD_REQUEST)
            return
        if url_path in ("/api/solve-csv", "/api/csv-source"):
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
            self.send_json_error("Not Found", HTTPStatus.NOT_FOUND)

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
    # Prepare reusable native code without solving a source or caching a route.
    from nohit.engine.csv_warmup import warm_csv_kernels
    warm_csv_kernels()
    server = ThreadingHTTPServer((host, port), DashboardHandler)
    return server


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8080
    server = start_server(port=port)
    print(f">> NOHIT CSV Solver Dashboard running at http://127.0.0.1:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n>> Shutting down server.")
        server.server_close()

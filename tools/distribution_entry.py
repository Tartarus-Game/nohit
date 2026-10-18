"""Standalone executable entry; requires neither Python nor a C++ compiler."""
import argparse
import json
import os
from pathlib import Path
import sys
import tempfile

# Must precede every engine import, including imports performed by the server.
os.environ['NOHIT_NATIVE_TUNE'] = 'portable'
os.environ.setdefault('OMP_WAIT_POLICY', 'PASSIVE')


def self_test():
    # Exercise real native search and independent scalar verification without
    # permitting a compiler, JIT, subprocess or cached machine-specific image.
    import shutil
    import subprocess
    def forbidden(*args, **kwargs):
        raise RuntimeError('A standalone release attempted to launch a subprocess')
    shutil.which = lambda *args, **kwargs: None
    subprocess.Popen = forbidden
    from nohit.engine.native_backend import load_backend
    _, metadata = load_backend()
    assert metadata['bundled'] and not metadata['compiled']
    assert metadata['cpu_target'] == 'portable'
    from nohit.engine.csv_solver import solve_csv
    from nohit.dashboard.server import start_server
    initial = [320.,304.,0.,0.,0.,0.,0.,1.,750.,0.,0.]
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / 'smoke.csv'
        # Real moving hazard + blue movement-sensitive hazard and EndAttack.
        path.write_text('0,HeartMode,0\n0,BoneH,100,100,20,20,0,0\n'
                        '0,BoneH,300,300,40,0,0,1\n0.2,EndAttack\n')
        result = solve_csv(path, initial, dt_schedule=[1/60]*120,
                           max_ticks=120, width=64, seconds=5,
                           objective='human_friendly', analyze_difficulty=True)
        assert result['verified'], result.get('reason')
        assert result['actions']
    server = start_server(port=0)
    server.server_close()
    root = Path(__import__('nohit').__file__).resolve().parents[1]
    assert (root/'nohit/dashboard/static/index.html').is_file()
    assert (root/'c2-sans-fight/c2runtime.js').is_file()
    assert 'numba' not in sys.modules
    print(json.dumps(dict(self_test='passed', bundled=True, compiler_required=False,
                          python_required=False, ticks=len(result['actions']))))


def main():
    parser = argparse.ArgumentParser(description='NOHIT portable dashboard')
    parser.add_argument('port', type=int, nargs='?', default=8080)
    parser.add_argument('--self-test', action='store_true')
    args = parser.parse_args()
    from nohit import _configure_solver_process
    _configure_solver_process()
    if args.self_test:
        self_test()
        return
    from nohit.engine.csv_warmup import warm_csv_kernels
    from nohit.dashboard.server import start_server
    warm_csv_kernels()
    server = start_server(port=args.port)
    print(f'NOHIT: open http://127.0.0.1:{server.server_port}', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()

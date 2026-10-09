"""Empty-cache dashboard startup + first HTTP CSV solve + scene replay."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

ROOT=Path(__file__).resolve().parents[1]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--child',action='store_true');args=parser.parse_args()
    if not args.child:
        with tempfile.TemporaryDirectory(prefix='nohit-cold-http-') as cache:
            env=dict(os.environ,NOHIT_NATIVE_CACHE=str(Path(cache)/'native'),NUMBA_CACHE_DIR=str(Path(cache)/'numba'))
            started=time.perf_counter()
            run=subprocess.run([sys.executable,'-m','tools.benchmark_dashboard_cold','--child'],
                cwd=ROOT,env=env,capture_output=True,text=True,timeout=20)
            if run.returncode:raise RuntimeError(run.stdout+run.stderr)
            report=json.loads(run.stdout);report['external_wall_seconds']=time.perf_counter()-started
            assert report['external_wall_seconds']<10
            (ROOT/'tools/optimization-results/cold-dashboard-http.json').write_text(json.dumps(report,indent=2))
            print(json.dumps(report))
        return
    started=time.perf_counter()
    import http.client
    import resource
    import threading
    from nohit.dashboard.server import start_server
    from nohit.engine.native_backend import load_backend
    server=start_server(port=0)
    ready=time.perf_counter()
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    entry=json.loads((ROOT/'tools/optimization-results/sans_bonegap1-entry.json').read_text())
    data=dict(csv_path=str(ROOT/'c2-sans-fight/sans_bonegap1.csv'),initial=entry['initial'],
        initial_environment=entry['initial_environment'],initial_arena=entry['initial_arena'],
        initial_confirm=entry['initial_confirm'],previous_confirm=entry['previous_confirm'],
        dt_schedule=[1/30]*40000,width=3000,seconds=8,search_strategy='native',workers=8)
    connection=http.client.HTTPConnection('127.0.0.1',server.server_address[1],timeout=10)
    connection.request('POST','/api/solve-csv',json.dumps(data),{'Content-Type':'application/json'})
    response=connection.getresponse();result=json.loads(response.read());connection.close()
    elapsed=time.perf_counter()-started
    assert response.status==200,result
    assert result['verified'] and result['visualization']['frame_count']==len(result['actions'])+1
    assert 'numba' not in sys.modules and 'llvmlite' not in sys.modules
    metadata=load_backend()[1];assert metadata['compiled']
    print(json.dumps(dict(inside_startup_seconds=ready-started,inside_through_response_seconds=elapsed,
        status=result['status'],verified=result['verified'],visualization_seconds=result['visualization_seconds'],
        request_seconds=result['request_seconds'],empty_code_cache=True,native_code=metadata,
        numba_imported=False,llvmlite_imported=False,solver_peak_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024,
        compiler_peak_rss_bytes=resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss*1024)))
    server.shutdown();server.server_close();thread.join()


if __name__=='__main__':main()

"""Ordered macro policies must select the same route at different worker counts."""
from types import SimpleNamespace
import numpy as np

from nohit.engine.native_backend import search


def test_macro_portfolio_respects_ordered_selection_with_parallel_workers():
    nt=240
    bounds=[100.,100.,540.,420.]
    env=np.tile(bounds+[0.,1.,0.,1/60,750.,0.,0.,0.,0.,0.]+bounds+bounds,(nt,1))
    wave=SimpleNamespace(env_schedule=env,platform_table=np.empty((nt,0,9)),
        geometry_white=np.empty((nt,0,4)),geometry_blue=np.empty((nt,0,4)),
        geometry_polygons=np.empty((nt,0,8)))
    initial=np.array([320.,304.,0.,0.,0.,0.,0.,1.,750.,0.,0.])
    controls=np.tile(np.arange(16),(nt-1,1));counts=np.full(nt-1,16)
    records=[search(initial,wave,controls,counts,[128],[42],workers,5,
        skip_policies=True,race=False,macro_width=128) for workers in (1,4)]
    for winner,actions,trace,attempts,metadata in records:
        assert winner==0 and metadata['controller']=='held-control-frontier'
        assert metadata['macro_hold_ticks']==4
        assert metadata['portfolio_selection']=='ordered'
    assert records[0][1].tobytes()==records[1][1].tobytes()
    assert records[0][2].tobytes()==records[1][2].tobytes()

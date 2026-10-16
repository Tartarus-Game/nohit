"""Progress follows the actual native CSV paths used by the game controller."""
import numpy as np

from nohit.engine.csv_solver import solve_csv


INITIAL=[320.,304.,0.,0.,0.,0.,0.,1.,750.,0.,0.]


def test_segmented_target_search_publishes_multiple_live_ticks_and_frontier_counts(tmp_path):
    path=tmp_path/'observed.csv'
    path.write_text('0,HeartMode,0\n0.1,GetHeartPos,x,y\n0.1,GetHeartPos,x,y\n0.1,EndAttack\n')
    snapshots=[]
    result=solve_csv(path,INITIAL,dt_schedule=(1/60,)*120,max_ticks=120,width=8,seconds=5,
        observation_chunk_ticks=6,observation_preview_ticks=6,progress=lambda **fields:snapshots.append(fields))
    assert result['status']=='candidate_found'
    search=[row for row in snapshots if row.get('phase')=='search' and row.get('expanded_states',0)>0]
    assert len({row.get('tick') for row in search})>=3
    assert all(isinstance(row.get('alive_states'),int) for row in search)
    assert max(row['expanded_states'] for row in search)>0
    verification=[row for row in snapshots if row.get('phase')=='verify']
    assert verification and verification[-1]['tick']==len(result['actions'])


def test_static_dialogue_search_reports_search_and_scalar_verification(tmp_path):
    path=tmp_path/'dialogue.csv'
    path.write_text('0,HeartMode,0\n0.3,SansText,abc,\n0.1,EndAttack\n')
    snapshots=[]
    result=solve_csv(path,INITIAL,dt_schedule=(1/60,)*120,max_ticks=120,width=8,seconds=5,
        progress=lambda **fields:snapshots.append(fields))
    assert result['status']=='candidate_found'
    assert any(row.get('phase')=='search' and row.get('expanded_states',0)>0 for row in snapshots)
    assert any(row.get('phase')=='verify' and row.get('tick')==len(result['actions']) for row in snapshots)


def test_native_callback_is_live_and_preserves_exact_witness_even_if_reporter_raises(tmp_path):
    from nohit.engine.native_backend import search
    from nohit.engine.parametric_environment import ParametricEnvironment
    path=tmp_path/'frontier.csv'
    path.write_text('0,HeartMode,0\n0.6,EndAttack\n')
    wave=ParametricEnvironment(path,dt_schedule=(1/30,)*100,max_ticks=100).bind().wave
    table=np.tile(np.arange(16,dtype=np.int64),(len(wave.env_schedule)-1,1))
    counts=np.full(len(table),16,np.int64)
    snapshots=[];inside_search=[True]
    def live(**fields):
        assert inside_search[0]
        snapshots.append(fields)
    def broken(**fields):
        raise RuntimeError('A broken telemetry consumer must not reject a witness')
    outputs=[]
    for progress in (None,live,broken):
        outputs.append(search(np.array(INITIAL),wave,table,counts,[512],[42],1,5,
            terminal_target=[320.,300.],progress=progress))
    inside_search[0]=False
    assert snapshots and all(row['phase']=='search' for row in snapshots)
    assert len({row['tick'] for row in snapshots})>=2
    assert any(row['expanded_states']>0 for row in snapshots)
    assert all(type(row['alive_states']) is int for row in snapshots)
    baseline=outputs[0]
    assert all(row[0]==baseline[0]==0 for row in outputs)
    assert all(row[1].tobytes()==baseline[1].tobytes() and
        row[2].tobytes()==baseline[2].tobytes() for row in outputs)
    assert snapshots[-1]['expanded_states']==sum(row['expanded'] for row in outputs[1][3])


def test_window_ticks_are_source_positions_and_search_counts_are_cumulative(tmp_path):
    path=tmp_path/'windows.csv'
    path.write_text('0,HeartMode,0\n0.1,GetHeartPos,x,y\n0.1,GetHeartPos,x,y\n0.1,EndAttack\n')
    snapshots=[]
    result=solve_csv(path,INITIAL,dt_schedule=(1/60,)*120,max_ticks=120,width=8,seconds=5,
        observation_chunk_ticks=6,observation_preview_ticks=6,progress=lambda **fields:snapshots.append(fields))
    assert result['verified']
    search=[row for row in snapshots if row.get('phase')=='search' and 'expanded_states' in row]
    assert search and all(row['ticks'] is None for row in search)
    expanded=[row['expanded_states'] for row in search]
    assert expanded==sorted(expanded)
    assert max(row['tick'] for row in search)==len(result['actions'])
    assert any('committed through source tick 6' in row.get('message','') for row in search)
    committed=[row['committed_tick'] for row in search]
    assert committed==sorted(committed) and max(committed)==len(result['actions'])
    assert all(row['committed_tick']<=row['tick'] for row in search)
    assert any(row['tick']>row['committed_tick'] for row in search)


def test_short_preflight_marks_a_coarse_cpu_clock_as_an_upper_bound(tmp_path,monkeypatch):
    from types import SimpleNamespace
    from nohit.engine import source_policy
    from nohit.engine.parametric_environment import ParametricEnvironment
    path=tmp_path/'short.csv';path.write_text('0,HeartMode,0\n0.5,EndAttack\n')
    wave=ParametricEnvironment(path,dt_schedule=(1/30,)*100,max_ticks=100).bind().wave
    walls=iter([0.]+[.001]*100)
    cpus=iter([0.,.015625])
    monkeypatch.setattr(source_policy,'time',SimpleNamespace(
        perf_counter=lambda:next(walls),thread_time=lambda:next(cpus)))
    result=source_policy.preflight(np.array(INITIAL),wave,3)
    code=result[4]
    assert code['search_cpu_seconds']==.001
    assert code['effective_search_cores']==1.
    assert code['thread_cpu_clock_raw_seconds']==.015625
    assert code['cpu_measurement_resolution_limited'] is True
    assert code['search_cpu_seconds_kind']=='single_thread_wall_upper_bound'

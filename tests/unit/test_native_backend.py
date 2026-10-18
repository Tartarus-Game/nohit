"""Native byte parity, deterministic parallel search, cold imports and bounds."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import numpy as np
import pytest

from nohit.engine.native_backend import step_batch, collision_batch, expand_batch
from nohit.engine.native_candidate import find_native_candidate, verify_candidate
from nohit.engine.source_oracle import scalar_module

ROOT=Path(__file__).resolve().parents[2]


@pytest.mark.parametrize('mode',[0.,1.])
@pytest.mark.parametrize('direction',[0.,1.,2.,3.])
@pytest.mark.parametrize('pulse',['none','slam','teleport','resize'])
def test_native_step_and_collision_are_source_byte_exact(mode,direction,pulse):
    # The independent scalar bodies retain source arithmetic and contact order.
    rng=np.random.default_rng(712)
    env=np.array([0.,0.,100.,100.,mode,direction,0.,1/30,750.,0.,50.,50.,1.,0.,0.,0.,100.,100.,0.,0.,100.,100.])
    if pulse=='slam':env[6]=1.
    if pulse=='teleport':env[9]=1.
    if pulse=='resize':env[:4]=env[18:22]=(10.,15.,90.,85.)
    platforms=np.array([[10.,45.,50.,5.,-0.,0.,1.,1.,-20.],
        [45.,70.,40.,5.,27.,-13.,1.,1.,-13.], [20.,30.,40.,5.,-21.,2.,1.,0.,2.]])
    states=np.zeros((120,11));states[:,:2]=rng.uniform(-15,115,(120,2));states[:,2:4]=rng.uniform(-750,750,(120,2))
    states[:,4]=rng.integers(0,32,120);states[:,5]=rng.integers(0,2,120);states[:,6:10]=(mode,direction,750.,1.)
    states[:16,:2]=(13.,37.);states[:16,2:4]=(-0.,0.);states[:16,4]=np.arange(16)
    controls=np.array(list(range(31,-1,-1))+[0,31,4],np.int64)
    players=np.repeat(states,len(controls),axis=0);masks=np.tile(controls,len(states))
    expected=np.empty_like(players);source=scalar_module('discrete_operator')
    for before,mask,after in zip(players,masks,expected):source.step_mask_into(before,int(mask),env,platforms,after)
    before=players.tobytes();actual=step_batch(players,masks,env,platforms)
    assert actual.tobytes()==expected.tobytes() and players.tobytes()==before
    white=np.array([[50.,45.,60.,50.],[np.nan]*4]);blue=np.array([[25.,25.,40.,40.]])
    polys=np.array([[60.,60.,90.,70.,80.,90.,50.,80.],[np.nan]*8])
    collision=scalar_module('cspace');payload=(np.empty((1,2,0,0),np.uint8),polys[None],0.,0.,1.)
    safe=np.array([not collision.collision_query(white[None],blue[None],0,s,0.,payload) for s in expected])
    assert np.array_equal(collision_batch(actual,white,blue,polys)==0,safe)
    envs=np.stack((env,env));ps=np.stack((platforms,platforms));ws=np.stack((white,white));bs=np.stack((blue,blue));qs=np.stack((polys,polys))
    outputs=[expand_batch(states,controls,0,envs,ps,ws,bs,qs,workers=w) for w in (1,4)]
    expected_parents=np.repeat(np.arange(len(states)),len(controls))[safe]
    for got,parents,keys in outputs:
        assert got.tobytes()==expected[safe].tobytes()
        assert parents.tobytes()==expected_parents.astype(np.int64).tobytes()
        assert keys.tobytes()==masks[safe].tobytes()


def test_native_matches_original_numba_dispatcher():
    # Separately compare the compiled original, not just its Python bodies.
    from nohit.engine.discrete_operator import step_mask_into
    rng=np.random.default_rng(29);env=np.array([0.,0.,100.,100.,1.,1.,0.,1/30,750.,0.,0.,0.,0.,0.,0.,0.,100.,100.,0.,0.,100.,100.])
    p=np.empty((0,9));states=np.zeros((600,11));states[:,:2]=rng.uniform(13,87,(600,2));states[:,2:4]=rng.uniform(-750,750,(600,2));states[:,4]=rng.integers(0,16,600);states[:,6:9]=(1.,1.,750.)
    masks=rng.integers(0,32,600,dtype=np.int64);expected=np.empty_like(states)
    for before,mask,after in zip(states,masks,expected):step_mask_into(before,int(mask),env,p,after)
    assert step_batch(states,masks,env,p).tobytes()==expected.tobytes()


def test_csv_import_does_not_load_numba_or_llvmlite():
    completed=subprocess.run([sys.executable,'-c',"import sys; import nohit.engine.csv_solver; assert 'numba' not in sys.modules; assert 'llvmlite' not in sys.modules"],cwd=ROOT,capture_output=True,text=True)
    assert completed.returncode==0,completed.stderr


def fixture(tmp_path):
    path=tmp_path/'simple.csv';path.write_text('0,HeartMode,0\n0.5,EndAttack\n')
    return path,[320.,304.,0.,0.,0.,0.,0.,1.,750.,0.,0.],dict(dt_schedule=[1/30]*100,max_ticks=100)


def test_worker_count_does_not_change_verified_witness(tmp_path):
    path,initial,settings=fixture(tmp_path)
    results=[find_native_candidate(path,initial,workers=w,**settings) for w in (1,2,4,8)]
    first=results[0]
    assert first.verified and first.stats['route_cache'] is False
    assert all(r.actions==first.actions and r.trajectory.tobytes()==first.trajectory.tobytes() for r in results)
    assert all(r.stats['workspace_bytes']<=r.stats['workspace_budget_bytes'] for r in results)
    for workers,result in zip((1,2,4,8),results):
        code=result.stats['native_code']
        assert code['cpu_measurement']==('python-thread-cpu-clock' if code.get('scalar_preflight') else 'native-thread-cpu-clock')
        assert 0<=code['effective_search_cores']<=workers+0.05
    assert first.stats['workspace_bytes']<len(first.trajectory)*3000*88


def test_scalar_oracle_rejects_mutated_witness(tmp_path):
    path,initial,settings=fixture(tmp_path);result=find_native_candidate(path,initial,**settings)
    trace=result.trajectory.copy();trace[2,0]+=1e-9
    valid,why=verify_candidate(path,initial,settings,result.actions,trace,result.bindings[0])
    assert not valid and why=='replay_state_mismatch'


@pytest.mark.parametrize('text',['0,SansText,a,\n0.5,EndAttack\n','0.1,GetHeartPos,x,y\n0.5,EndAttack\n'])
def test_unresolved_worlds_do_not_enter_static_native_probe(tmp_path,text):
    path=tmp_path/'unresolved.csv';path.write_text(text)
    assert find_native_candidate(path,[320.,304.,0.,0.,0.,0.,0.,1.,750.,0.,0.],dt_schedule=[1/30]*100,max_ticks=100,termination_policy='eof_hazards_drained') is None


def test_native_empty_batch_and_resource_validation():
    env=np.zeros((2,22));env[:,7]=1/30;p=np.empty((2,0,9));b=np.empty((2,0,4));q=np.empty((2,0,8))
    result=expand_batch(np.empty((0,11)),np.arange(32,dtype=np.int64),0,env,p,b,b,q,workers=4)
    assert [v.shape for v in result]==[(0,11),(0,),(0,)]
    with pytest.raises(ValueError,match='workers'):expand_batch(np.zeros((1,11)),np.arange(16),0,env,p,b,b,q,workers=0)


@pytest.mark.parametrize('text',[
    '0,HeartMode,0\n0.1,GetHeartPos,x,y\n0.3,EndAttack\n',
    '0,SansText,hello,\n0.3,EndAttack\n',
])
def test_input_dependent_world_is_replayed_without_numba(tmp_path,text):
    path=tmp_path/'observed.csv';path.write_text(text)
    script="""
import json,sys
from nohit.engine.csv_solver import solve_csv
from nohit.dashboard.csv_visualization import build_csv_visualization
r=solve_csv(sys.argv[1],[320.,304.,0.,0.,0.,0.,0.,1.,750.,0.,0.],
    dt_schedule=[1/30]*500,max_ticks=500,search_strategy='native',seconds=3)
assert r['verified'], r['reason']
v=build_csv_visualization(sys.argv[1],r,dt_schedule=[1/30]*500)
assert len(v['frames'])==len(r['actions'])+1
assert 'numba' not in sys.modules and 'llvmlite' not in sys.modules
r['trajectory'][2][0]+=1e-8
try: build_csv_visualization(sys.argv[1],r,dt_schedule=[1/30]*500)
except ValueError: pass
else: raise AssertionError('mutated trajectory accepted')
"""
    process=subprocess.run([sys.executable,'-c',script,str(path)],cwd=ROOT,capture_output=True,text=True,timeout=10)
    assert process.returncode==0,process.stdout+process.stderr


def test_wide_frontier_shared_edge_team_keeps_exact_witness(tmp_path):
    from nohit.engine.native_backend import search
    from nohit.engine.parametric_environment import ParametricEnvironment
    path=tmp_path/'incoming.csv'
    path.write_text('0,HeartMode,0\n0,BoneV,350,285,45,2,100\n1,EndAttack\n')
    wave=ParametricEnvironment(path,dt_schedule=[1/30]*100,max_ticks=100).bind().wave
    state=np.array([320.,304.,0.,0.,0.,0.,0.,1.,750.,0.,0.])
    table=np.tile(np.arange(16,dtype=np.int64),(len(wave.env_schedule)-1,1))
    counts=np.full(len(table),16,np.int64)
    results=[search(state,wave,table,counts,[512],[42],workers,3) for workers in (1,4)]
    assert all(result[0]==0 for result in results)
    assert results[0][1].tobytes()==results[1][1].tobytes()
    assert results[0][2].tobytes()==results[1][2].tobytes()
    assert results[1][4].get('edge_workers')==4
    assert results[1][3][0]['expanded']>128
    # Mandatory original-scalar replay independently checks every parallel edge.
    player=scalar_module('discrete_operator');state=results[1][2][0].copy()
    for tick,mask in enumerate(results[1][1],1):
        player.step_mask_into(state,int(mask),wave.env_schedule[tick],wave.platform_table[tick],state)
        assert state.tobytes()==results[1][2][tick].tobytes()


def test_explicit_native_small_width_never_enters_legacy_jit(tmp_path,monkeypatch):
    from nohit.engine import csv_solver
    path,initial,settings=fixture(tmp_path)
    result=csv_solver.solve_csv(path,initial,width=1,search_strategy='native',**settings)
    assert result['verified'] and result['search_stats']['backend']=='native-portfolio'


def test_auto_narrow_safe_wave_needs_neither_compiler_nor_numba(tmp_path):
    path,initial,settings=fixture(tmp_path)
    script="""
import json,os,sys
from pathlib import Path
from nohit.engine.csv_solver import solve_csv
r=solve_csv(sys.argv[1],json.loads(sys.argv[2]),width=1,dt_schedule=[1/30]*100,max_ticks=100)
assert r['verified'] and r['search_stats']['native_code']['scalar_preflight']
assert not r['search_stats']['native_code']['compiled']
assert 'numba' not in sys.modules and 'llvmlite' not in sys.modules
assert not list(Path(os.environ['NOHIT_NATIVE_CACHE']).glob('*'))
"""
    cache=tmp_path/'cache';cache.mkdir()
    environment=dict(os.environ,NOHIT_NATIVE_CACHE=str(cache),CXX='compiler-that-does-not-exist')
    result=subprocess.run([sys.executable,'-c',script,str(path),json.dumps(initial)],env=environment,cwd=ROOT,capture_output=True,text=True,timeout=5)
    assert result.returncode==0,result.stdout+result.stderr


def test_preflight_rejects_a_trajectory_with_an_incoming_hazard(tmp_path):
    from nohit.engine.parametric_environment import ParametricEnvironment
    from nohit.engine.source_policy import preflight
    path=tmp_path/'unsafe-neutral.csv'
    path.write_text('0,HeartMode,0\n0,BoneV,350,285,45,2,100\n1,EndAttack\n')
    wave=ParametricEnvironment(path,dt_schedule=[1/30]*100,max_ticks=100).bind().wave
    assert preflight(np.array([320.,304.,0.,0.,0.,0.,0.,1.,750.,0.,0.]),wave,3) is None


@pytest.mark.parametrize("width,workers",[(512,4),(4096,1),(4096,3),(4096,7)])
def test_rolling_backup_restores_a_pruned_source_path_byte_exactly(width,workers):
    from nohit.engine.native_backend import search
    nt=21
    env=np.tile(np.array([0.,0.,1000.,1000.,0.,1.,0.,1/30,750.,0.,320.,304.,0.,0.,0.,0.,1000.,1000.,0.,0.,1000.,1000.]),(nt,1))
    white=np.full((nt,4,4),np.nan);x,y=355.,364.
    white[-1]=[[-1000.,-1000.,x-2.1,2000.],[x+2.1,-1000.,2000.,2000.],
        [x-2.1,-1000.,x+2.1,y-2.1],[x-2.1,y+2.1,x+2.1,2000.]]
    wave=SimpleNamespace(env_schedule=env,platform_table=np.empty((nt,0,9)),geometry_white=white,
        geometry_blue=np.empty((nt,0,4)),geometry_polygons=np.empty((nt,0,8)))
    table=np.tile(np.arange(16,dtype=np.int64),(nt-1,1));counts=np.full(nt-1,16,np.int64)
    # A nonbinary source latch verifies that snapshots preserve its float64,
    # rather than coercing it to a boolean or quantizing it.
    state=np.array([320.,304.,0.,0.,0.,.25,0.,1.,750.,0.,0.])
    winner,actions,trace,attempts,_=search(state,wave,table,counts,[width],[42],workers,3)
    assert winner==0
    if width==512:assert attempts[0]['recoveries']>0
    assert trace[-1,:2].tolist()==[x,y]
    source=scalar_module('discrete_operator');collision=scalar_module('cspace')
    payload=(np.empty((nt,2,0,0),np.uint8),wave.geometry_polygons,0.,0.,1.)
    for tick in range(nt):
        if tick:source.step_mask_into(state,int(actions[tick-1]),env[tick],wave.platform_table[tick],state)
        assert state.tobytes()==trace[tick].tobytes()
        assert not collision.collision_query(white,wave.geometry_blue,tick,state,0.,payload)


def test_default_cpu_workers_respect_affinity_quota_and_api_limit(monkeypatch):
    from nohit.engine import native_backend as backend
    monkeypatch.setattr(backend.os,'cpu_count',lambda:64)
    monkeypatch.setattr(backend.os,'sched_getaffinity',lambda _:set(range(48)),raising=False)
    original=backend.Path.read_text
    def quota(self,*args,**kwargs):
        return '800000 100000' if self.as_posix()=='/sys/fs/cgroup/cpu.max' else original(self,*args,**kwargs)
    monkeypatch.setattr(backend.Path,'read_text',quota)
    assert backend.available_cpu_workers()==8
    monkeypatch.setattr(backend.Path,'read_text',lambda _: 'max 100000')
    assert backend.available_cpu_workers()==32
    monkeypatch.setattr(backend.os,'sched_getaffinity',lambda _:set(range(3)))
    assert backend.available_cpu_workers()==3


def test_integer_frontier_is_mixed_without_rebuilds_or_merging_source_states(tmp_path):
    from nohit.engine.native_backend import search
    from nohit.engine.parametric_environment import ParametricEnvironment
    path=tmp_path/'integer.csv';path.write_text('0,HeartMode,0\n0.6,EndAttack\n')
    wave=ParametricEnvironment(path,dt_schedule=[1/30]*100,max_ticks=100).bind().wave
    initial=np.array([320.,304.,0.,0.,0.,0.,0.,1.,750.,0.,0.])
    table=np.tile(np.arange(16,dtype=np.int64),(len(wave.env_schedule)-1,1));counts=np.full(len(table),16,np.int64)
    results=[search(initial,wave,table,counts,[512],[42],workers,5,terminal_target=[320.,300.]) for workers in (1,4)]
    assert all(r[0]==0 and r[4]['state_hash_rebuilds']==0 for r in results)
    assert all(r[4]['state_hash_mode']=='avalanche-full-bit-equality' for r in results)
    assert results[0][1].tobytes()==results[1][1].tobytes()
    assert results[0][2].tobytes()==results[1][2].tobytes()
    player=scalar_module('discrete_operator');state=initial.copy()
    for tick,mask in enumerate(results[0][1],1):
        player.step_mask_into(state,int(mask),wave.env_schedule[tick],wave.platform_table[tick],state)
        assert state.tobytes()==results[0][2][tick].tobytes()


@pytest.mark.parametrize("direction",[-0.,.25,1.,2.,3.,7.375])
def test_shared_frame_axes_preserve_scalar_player_bits(direction):
    from nohit.engine.native_backend import step_batch
    rng=np.random.default_rng(891)
    states=np.tile(np.array([320.,304.,0.,0.,0.,.25,1.,direction,750.,1.,1.]),(64,1))
    states[:,:2]+=rng.uniform(-45.,45.,(64,2));states[:,2:4]=rng.uniform(-350.,350.,(64,2))
    states[:,4]=rng.integers(0,32,64)
    env=np.array([33.,251.,608.,391.,1.,direction,0.,1/60,750.,0.,320.,304.,1.,0.,33.,251.,608.,391.,33.,251.,608.,391.])
    platforms=np.array([[280.,340.,100.,10.,30.,-10.,1.,0.,0.]])
    masks=rng.integers(0,32,64,dtype=np.int64)
    actual=step_batch(states,masks,env,platforms)
    source=scalar_module('discrete_operator')
    for index,state in enumerate(states):
        expected=state.copy();source.step_mask_into(expected,int(masks[index]),env,platforms,expected)
        assert expected.tobytes()==actual[index].tobytes()

@pytest.mark.parametrize('dt',[1/60,1/30,0.,-1/60])
def test_clear_movement_sweep_matches_old_walls_and_platform_samples(dt):
    from nohit.engine.native_backend import step_batch
    rng=np.random.default_rng(922)
    states=np.tile(np.array([320.,304.,0.,0.,0.,1.,1.,1.,750.,1.,0.]),(256,1))
    states[:,:2]=rng.uniform([25.,245.],[616.,400.],(256,2))
    states[:,2:4]=rng.uniform(-2000.,2000.,(256,2))
    states[:,4]=rng.integers(0,32,256);states[:,7]=rng.choice([0.,1.,2.,3.,.75],256)
    states[:12,0]=[46.,46.,46.,595.,595.,595.,280.,280.,280.,388.,388.,388.]
    states[:12,1]=[264.,np.nextafter(264.,0.),np.nextafter(264.,400.),378.,np.nextafter(378.,0.),np.nextafter(378.,400.),332.,np.nextafter(332.,0.),np.nextafter(332.,400.),332.,340.,350.]
    env=np.array([33.,251.,608.,391.,1.,1.,0.,dt,750.,0.,320.,304.,1.,0.,33.,251.,608.,391.,33.,251.,608.,391.])
    platforms=np.array([[280.,340.,100.,10.,30.,-10.,1.,1.,-10.],[350.,290.,80.,8.,-15.,20.,1.,1.,20.],[50.,360.,60.,5.,0.,0.,0.,0.,0.]])
    masks=rng.integers(0,32,256,dtype=np.int64);actual=step_batch(states,masks,env,platforms)
    source=scalar_module('discrete_operator')
    for index,state in enumerate(states):
        expected=state.copy();source.step_mask_into(expected,int(masks[index]),env,platforms,expected)
        assert actual[index].tobytes()==expected.tobytes(),(index,dt)

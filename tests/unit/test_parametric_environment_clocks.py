"""Explicit clock protocols remain immutable and scope every bound history."""
import struct
import numpy as np
import pytest

from nohit.engine.compact_wave import compile_wave
from nohit.engine.parametric_environment import ParametricEnvironment
from nohit.engine.history_quotient import FutureHistoryKey


def source(tmp_path,text='0,HeartMode,0\n0.2,EndAttack\n'):
    path=tmp_path/'clock.csv';path.write_text(text)
    return path


def same_wave(a,b):
    for name in ('env_schedule','platform_table','num_platforms','geometry_white',
                 'geometry_blue','geometry_polygons','initial','schedule','dt'):
        aa=np.asarray(getattr(a,name));bb=np.asarray(getattr(b,name))
        assert aa.shape==bb.shape and aa.dtype==bb.dtype and aa.tobytes()==bb.tobytes(),name
    for name in ('source_events','target_history','pending_target','complete','termination_reason',
                 'eof_tick','environment_state_keys','origin','dimensions'):
        assert getattr(a,name)==getattr(b,name),name


@pytest.mark.parametrize('schedule',[
    [1/30]*100,[1/60]*100,[1/240]*100,
    [1/30,1/60,1/120,1/240]*25,
])
def test_explicit_clock_reference_resumable_and_compiler_agree(tmp_path,schedule):
    path=source(tmp_path,'0,HeartMode,0\n0,Platform,220,340,50,0,80,1\n'
        '0.025,BoneV,280,260,20,0,50\n0.075,SansSlam,2\n0.1,EndAttack\n')
    environments=[ParametricEnvironment(path,max_ticks=100,capture_state_keys=True,
                    backend=backend,dt_schedule=schedule) for backend in ('reference','resumable')]
    bindings=[env.bind() for env in environments]
    same_wave(bindings[0].wave,bindings[1].wave)
    same_wave(bindings[0].wave,compile_wave(path,max_ticks=100,capture_state_keys=True,dt_schedule=schedule))
    assert bindings[0].identity==bindings[1].identity
    assert bindings[0].complete


@pytest.mark.parametrize('backend',['reference','resumable'])
def test_caller_mutation_does_not_change_clock_or_identity(tmp_path,backend):
    path=source(tmp_path)
    caller=np.array([1/30,1/60,1/120]*40)
    original=caller.copy()
    env=ParametricEnvironment(path,max_ticks=120,backend=backend,dt_schedule=caller)
    assert isinstance(env.dt_schedule,tuple)
    caller[:]=1/240
    binding=env.bind()
    expected=ParametricEnvironment(path,max_ticks=120,backend=backend,dt_schedule=original).bind()
    assert binding.identity==expected.identity
    same_wave(binding.wave,expected.wave)
    assert np.asarray(env.dt_schedule).tobytes()==original.tobytes()
    with pytest.raises(TypeError):env.dt_schedule[0]=1/240
    with pytest.raises(AttributeError):env.dt_schedule=(1/240,)*120
    assert env.bind() is binding


def test_complete_clock_not_only_executed_prefix_scopes_bindings(tmp_path):
    path=source(tmp_path)
    a=np.full(100,1/30);b=a.copy();b[-1]=np.nextafter(b[-1],1.)
    clocks=[None,a,b,np.append(a,a[-1])]
    bindings=[ParametricEnvironment(path,max_ticks=10,dt_schedule=clock).bind() for clock in clocks]
    assert len({binding.identity for binding in bindings})==len(clocks)
    # The changed tail is not consumed. Its future protocol still scopes facts.
    same_wave(bindings[1].wave,bindings[2].wave)
    assert ParametricEnvironment(path,max_ticks=10,dt_schedule=a.tolist()).bind().identity==bindings[1].identity


@pytest.mark.parametrize('backend',['reference','resumable'])
def test_pending_extension_retains_clock_and_exact_history_suffix(tmp_path,backend):
    path=source(tmp_path,'0.025,GetHeartPos,x,y\n0,BoneV,$x,$y,10,0,20\n'
        '0.075,GetHeartPos,x,y\n0,GetHeartPos,x,y\n0.1,EndAttack\n')
    schedule=np.array([1/30,1/60,1/120,1/240]*40)
    env=ParametricEnvironment(path,max_ticks=160,backend=backend,dt_schedule=schedule,capture_state_keys=True)
    reference=ParametricEnvironment(path,max_ticks=160,backend='reference',dt_schedule=schedule,capture_state_keys=True)
    root=env.bind();bound=root;ref=reference.bind()
    for _ in range(3):
        assert bound.pending_target is not None
        parent=bound
        bound=env.extend(bound,100.+len(bound.history),200.)
        ref=reference.extend(ref,100.+len(ref.history),200.)
        assert bound.identity[:-32]==parent.identity
        assert bound.identity[-32:]==struct.pack('<qqdd',*bound.history[-1])
        assert bound.identity[:-32*len(bound.history)]==root.identity
        same_wave(bound.wave,ref.wave)
        if backend=='resumable':assert bound.resume_state.program.dt_schedule==env.dt_schedule
    assert bound.complete and bound.pending_target is None
    fresh=ParametricEnvironment(path,max_ticks=160,backend=backend,dt_schedule=schedule,capture_state_keys=True)
    direct=fresh.bind(bound.history)
    same_wave(direct.wave,bound.wave)
    assert direct.identity==bound.identity


@pytest.mark.parametrize('backend',['reference','resumable'])
def test_short_clock_exhaustion_is_an_incomplete_budget_boundary(tmp_path,backend):
    path=source(tmp_path,'0,HeartMode,0\n0.05,GetHeartPos,x,y\n1,EndAttack\n')
    schedule=(1/30,1/60,1/120,1/240)
    env=ParametricEnvironment(path,max_ticks=100,backend=backend,dt_schedule=schedule)
    binding=env.bind()
    while binding.pending_target is not None:binding=env.extend(binding,320.,304.)
    assert not binding.complete and binding.wave.termination_reason=='tick_budget'
    assert len(binding.wave.env_schedule)==len(schedule)
    assert binding.wave.dt.tobytes()==np.asarray(schedule).tobytes()
    if backend=='resumable':assert binding.resume_state.data['tick']==len(schedule)
    expected=ParametricEnvironment(path,max_ticks=100,backend='reference',dt_schedule=schedule).bind(binding.history)
    same_wave(binding.wave,expected.wave)


def test_clock_scopes_own_history_quotients_and_rejects_foreign_extensions(tmp_path):
    path=source(tmp_path,'0,GetHeartPos,x,y\n0.025,BlackScreen,1\n0.2,EndAttack\n')
    environments=[ParametricEnvironment(path,max_ticks=100,dt_schedule=[dt]*100) for dt in (1/30,1/60)]
    bound=[env.extend(env.bind(),100.,200.) for env in environments]
    keys=[FutureHistoryKey(env)(binding,10) for env,binding in zip(environments,bound)]
    assert keys[0]!=keys[1]
    with pytest.raises(ValueError,match='another environment template'):
        environments[0].extend(environments[1].bind(),100.,200.)


@pytest.mark.parametrize('schedule',[[],[0.],[-0.],[-1.],[float('nan')],[float('inf')],
    [float('-inf')],[[1/30]],[1/30,[]],1/30,'0.033',None])
def test_invalid_or_ambiguous_clock_is_rejected(tmp_path,schedule):
    path=source(tmp_path)
    if schedule is None:
        with pytest.raises(ValueError,match='clock'):
            ParametricEnvironment(path,clock_start_ms=100.,dt_schedule=[1/30]*100)
    else:
        with pytest.raises(ValueError,match='dt_schedule'):
            ParametricEnvironment(path,dt_schedule=schedule)


def test_existing_positional_arguments_and_default_identity_remain_compatible(tmp_path):
    path=source(tmp_path)
    old=ParametricEnvironment(path,42,None,None,'endattack',100,False,'reference')
    keyword=ParametricEnvironment(path,max_ticks=100,backend='reference')
    assert old.dt_schedule is None and old.bind().identity==keyword.bind().identity
    explicit=ParametricEnvironment(path,42,None,None,'endattack',100,False,'reference',[1/30]*100)
    assert explicit.dt_schedule==(1/30,)*100

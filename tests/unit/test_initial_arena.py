"""Native arena target/size/callback state exists before the first CSV row."""
import copy

import numpy as np
import pytest

from nohit.engine.compact_wave import TimelineVM,compile_wave
from nohit.engine.parametric_environment import ParametricEnvironment
from nohit.engine.resumable_wave import initialize,advance_one_tick,advance_with_dialogue_input


INITIAL=[32.,240.,608.,384.,0.,1.,0.,1/30,750.,0.,0.,0.,0.]
ARENA={'target':[33.,251.,608.,391.],'size':[576.,144.],'speed':480.,'callback':''}


def source(tmp_path,text='0,HeartMode,0\n0.2,EndAttack\n'):
    path=tmp_path/'initial-arena.csv';path.write_text(text,encoding='utf-8')
    return path


def options(arena=ARENA):
    return dict(initial_environment=INITIAL,initial_arena=arena,dt_schedule=(1/30,)*20,max_ticks=20)


@pytest.mark.parametrize('backend',['reference','resumable'])
def test_native_pending_arena_applies_on_frame_zero_then_stays_settled(tmp_path,backend):
    path=source(tmp_path)
    wave=ParametricEnvironment(path,backend=backend,capture_state_keys=True,**options()).bind().wave
    expected=np.tile(ARENA['target'],(len(wave.env_schedule),1))
    np.testing.assert_array_equal(wave.env_schedule[:,:4],expected)
    direct=compile_wave(path,capture_state_keys=True,**options())
    np.testing.assert_array_equal(wave.env_schedule,direct.env_schedule)
    assert wave.environment_state_keys==direct.environment_state_keys
    assert wave.terminal_details['initial_callback_contract']=='explicit_initial_arena'


def test_resumable_and_vm_receive_native_size_target_speed_and_callback(tmp_path):
    path=source(tmp_path)
    arena=dict(ARENA,callback='TLResume')
    state=initialize(path,**options(arena))
    assert state.data['cz']==INITIAL[:4]
    assert state.data['cz_size']==ARENA['size']
    assert state.data['tgt_cz']==ARENA['target']
    assert state.data['cz_speed']==480.
    assert state.data['end_resize']['function']=='TLResume'
    frame=advance_one_tick(state).frame
    np.testing.assert_array_equal(frame.env[:4],ARENA['target'])
    vm=TimelineVM(**options(arena))
    np.testing.assert_array_equal(vm.run([['0.2','EndAttack']],dt_nominal=1/30)['env_schedule'][0,:4],ARENA['target'])


@pytest.mark.parametrize('command,expected',[
    ('CombatZoneResizeInstant,100,260,500,380',[100.,260.,500.,380.]),
    ('CombatZoneResize,100,260,500,380,',[48.,256.,592.,380.]),
])
@pytest.mark.parametrize('backend',['reference','resumable'])
def test_csv_row_zero_overrides_initial_pending_target(tmp_path,backend,command,expected):
    path=source(tmp_path,'0,'+command+'\n0.2,EndAttack\n')
    wave=ParametricEnvironment(path,backend=backend,**options()).bind().wave
    np.testing.assert_array_equal(wave.env_schedule[0,:4],expected)


def test_opening_dialogue_still_advances_native_arena(tmp_path):
    path=source(tmp_path,'0,SansText,hello,\n0,EndAttack\n')
    state=initialize(path,**options())
    result=advance_with_dialogue_input(state,confirm=False,cancel=False,
        previous_confirm=False,previous_cancel=False)
    np.testing.assert_array_equal(result.frame.env[:4],ARENA['target'])
    assert result.state.dialogue.alive


@pytest.mark.parametrize('arena,expected',[
    (dict(ARENA,size=[600.,144.]),[33.,251.,616.,391.]),
    (dict(ARENA,speed=120.),[33.,244.,608.,388.]),
])
@pytest.mark.parametrize('backend',['reference','resumable'])
def test_native_size_and_speed_are_not_reconstructed_from_bounds(tmp_path,backend,arena,expected):
    path=source(tmp_path)
    wave=ParametricEnvironment(path,backend=backend,**options(arena)).bind().wave
    np.testing.assert_array_equal(wave.env_schedule[0,:4],expected)


@pytest.mark.parametrize('backend',['reference','resumable'])
def test_initial_tlresume_callback_fires_once_after_settling(tmp_path,backend):
    path=source(tmp_path,'0,TLPause\n0.1,EndAttack\n')
    wave=ParametricEnvironment(path,backend=backend,**options(dict(ARENA,callback='TLResume'))).bind().wave
    assert wave.complete
    calls=wave.terminal_details['executed_callbacks']
    assert len(calls)==1 and calls[0]['function']=='TLResume'
    assert calls[0]['executed_tick']==0
    assert wave.terminal_details['pending_callbacks']==[]


@pytest.mark.parametrize('backend',['reference','resumable'])
def test_arena_snapshot_scopes_identity_and_is_copied(tmp_path,backend):
    path=source(tmp_path,'0,GetHeartPos,x,y\n0.1,EndAttack\n')
    arena=copy.deepcopy(ARENA)
    template=ParametricEnvironment(path,backend=backend,**options(arena))
    arena['target'][0]=200.;arena['size'][0]=100.;arena['speed']=1.;arena['callback']='TLResume'
    binding=template.bind()
    original=ParametricEnvironment(path,backend=backend,**options()).bind()
    assert binding.identity==original.identity
    variants=[None,ARENA,dict(ARENA,target=[34.,251.,608.,391.]),
              dict(ARENA,size=[575.,144.]),dict(ARENA,speed=240.),dict(ARENA,callback='TLResume')]
    identities=[ParametricEnvironment(path,backend=backend,**options(a)).bind().identity for a in variants]
    assert len(set(identities))==len(variants)
    assert template.extend(binding,320.,320.).identity[:-32]==binding.identity
    programs=[initialize(path,**options(a)).program.identity for a in variants]
    assert len(set(programs))==len(variants)


@pytest.mark.parametrize('entry',['compile','initialize','parametric','vm'])
def test_unsupported_initial_callback_is_explicitly_rejected(tmp_path,entry):
    path=source(tmp_path)
    kwargs=options(dict(ARENA,callback='SpawnLateAttack'))
    with pytest.raises(ValueError,match='unsupported_initial_arena_callback:SpawnLateAttack'):
        if entry=='compile':compile_wave(path,**kwargs)
        elif entry=='initialize':initialize(path,**kwargs)
        elif entry=='parametric':ParametricEnvironment(path,**kwargs)
        else:TimelineVM(**kwargs)


@pytest.mark.parametrize('backend',['reference','resumable'])
def test_none_preserves_existing_initial_arena_contract(tmp_path,backend):
    path=source(tmp_path)
    kwargs=options(None)
    explicit=ParametricEnvironment(path,backend=backend,**kwargs).bind()
    del kwargs['initial_arena']
    omitted=ParametricEnvironment(path,backend=backend,**kwargs).bind()
    assert explicit.identity==omitted.identity
    np.testing.assert_array_equal(explicit.wave.env_schedule,omitted.wave.env_schedule)
    np.testing.assert_array_equal(explicit.wave.env_schedule[0,:4],INITIAL[:4])
    assert explicit.wave.terminal_details['initial_callback_contract']=='assumed_none_not_encoded_in_initial_environment'

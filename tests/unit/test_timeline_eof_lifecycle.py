"""EOF stops commands, never native attack entities or physics."""
import numpy as np
import pytest
from nohit.engine.compact_wave import compile_wave
from nohit.engine.parametric_environment import ParametricEnvironment


def source(tmp_path,text):
    path=tmp_path/'eof.csv'
    path.write_text(text)
    return path


def test_default_still_requires_original_endattack(tmp_path):
    path=source(tmp_path,'0,HeartMode,0\n')
    with pytest.raises(ValueError,match='EOF without EndAttack'):
        compile_wave(path)


def test_eof_waiting_blaster_survives_and_fires(tmp_path):
    path=source(tmp_path,'0,GasterBlaster,1,320,240,320,240,0,0.2,0.1\n')
    wave=compile_wave(path,termination_policy='eof_hazards_drained',max_ticks=1000)
    assert wave.complete and wave.termination_reason=='eof_hazards_drained'
    assert wave.eof_tick==0
    assert not np.isfinite(wave.geometry_polygons[0]).any()
    assert np.isfinite(wave.geometry_polygons[1:]).any()
    assert wave.terminal_details['active_blasters']==0
    assert wave.terminal_details['player_invariant_proven'] is False
    assert not any(event[1]=='endattack' for event in wave.source_events)


def test_passive_platform_is_retained_at_eof(tmp_path):
    path=source(tmp_path,'0,Platform,200,300,60,0,0\n')
    wave=compile_wave(path,termination_policy='eof_hazards_drained',max_ticks=20)
    assert wave.complete and len(wave.env_schedule)==1
    assert wave.terminal_details['active_platforms']==1
    assert wave.platform_table[0,0,6]==1.


def test_budget_does_not_drop_prefire_hazard_or_claim_completion(tmp_path):
    path=source(tmp_path,'0,GasterBlaster,1,320,240,320,240,0,1,0.1\n')
    wave=compile_wave(path,termination_policy='eof_hazards_drained',max_ticks=8)
    assert not wave.complete and wave.termination_reason=='tick_budget'
    assert wave.terminal_details['active_blasters']==1
    assert len(wave.env_schedule)==8


def test_budget_is_explicit_for_endattack_program(tmp_path):
    path=source(tmp_path,'1,EndAttack\n')
    prefix=compile_wave(path,max_ticks=8)
    full=compile_wave(path,max_ticks=300)
    assert not prefix.complete and prefix.termination_reason=='tick_budget'
    assert full.complete and full.termination_reason=='endattack'


def test_caller_can_compile_beyond_old_40000_tick_cap(tmp_path):
    path=source(tmp_path,'167,EndAttack\n')
    wave=compile_wave(path,max_ticks=40100)
    assert wave.complete and len(wave.env_schedule)>40000


def test_eof_warning_stab_and_stationary_bone_are_not_discarded(tmp_path):
    path=source(tmp_path,'0,BoneStab,1,30,1,0.2\n0,BoneV,320,300,40,0,0\n')
    wave=compile_wave(path,termination_policy='eof_hazards_drained',max_ticks=10)
    assert not wave.complete
    assert wave.terminal_details['active_stabs']==1
    assert wave.terminal_details['active_bones']==1


def test_parametric_policy_and_budget_are_in_binding_identity(tmp_path):
    path=source(tmp_path,'0,GetHeartPos,x,y\n0,GasterBlaster,1,$x,$y,$x,$y,0,0.2,0.1\n')
    env=ParametricEnvironment(path,termination_policy='eof_hazards_drained',max_ticks=1000)
    root=env.bind()
    assert root.pending_target is not None and not root.complete
    full=env.extend(root,320.,240.)
    assert full.complete and full.wave.termination_reason=='eof_hazards_drained'
    short=ParametricEnvironment(path,termination_policy='eof_hazards_drained',max_ticks=8).bind()
    assert short.identity!=root.identity


def test_dialogue_is_an_unresolved_boundary_not_cosmetic(tmp_path):
    path=source(tmp_path,'0,SansText,hello\n0,GasterBlaster,1,320,240,320,240,0,0,0\n')
    wave=compile_wave(path,termination_policy='eof_hazards_drained',max_ticks=100)
    assert not wave.complete and wave.termination_reason=='dialogue_boundary'
    assert wave.terminal_details['pending_dialogue']['line']==1
    assert not any(event[1]=='gasterblaster' for event in wave.source_events)
    assert wave.terminal_details['timeline_exhausted'] is False


@pytest.mark.parametrize('callback',['',','])
def test_eof_without_callback_records_model_initial_assumption(tmp_path,callback):
    path=source(tmp_path,'0,CombatZoneResize,133,251,508,391'+callback+'\n')
    wave=compile_wave(path,termination_policy='eof_hazards_drained')
    assert wave.terminal_details['timeline_exhausted'] is True
    assert wave.terminal_details['pending_callbacks']==[]
    assert wave.terminal_details['initial_callback_contract']=='assumed_none_not_encoded_in_initial_environment'


@pytest.mark.parametrize('callback',['SpawnLateAttack','1'])
def test_settled_arena_does_not_certify_callback_execution(tmp_path,callback):
    path=source(tmp_path,'0,CombatZoneResize,133,251,508,391,'+callback+'\n')
    wave=compile_wave(path,termination_policy='eof_hazards_drained')
    assert wave.terminal_details['arena_settled']
    assert wave.terminal_details['timeline_exhausted']
    assert wave.terminal_details['pending_callbacks']==[{'source_line':1,'tick':0,
        'function':callback,'status':'execution_unproven'}]


def test_budget_before_last_instruction_is_not_timeline_exhaustion(tmp_path):
    path=source(tmp_path,'1,EndAttack\n')
    wave=compile_wave(path,max_ticks=2)
    assert wave.terminal_details['timeline_exhausted'] is False


@pytest.mark.parametrize('name',['TLResume','tLrEsUmE'])
def test_resize_tlresume_fires_once_only_after_arena_settles(tmp_path,name):
    path=source(tmp_path,'0,CombatZoneResize,241,226,406,391,'+name+'\n0.5,EndAttack\n')
    initial=[133.,251.,508.,391.,0.,1.,0.,1/240,750.,0.,0.,0.,0.]
    short=compile_wave(path,initial_environment=initial,max_ticks=1)
    assert not short.complete and not short.terminal_details['arena_settled']
    assert short.terminal_details['executed_callbacks']==[]
    assert short.terminal_details['pending_callbacks'][0]['status']=='awaiting_arena_settle'
    full=compile_wave(path,initial_environment=initial,max_ticks=200)
    calls=full.terminal_details['executed_callbacks']
    assert len(calls)==1 and calls[0]['executed_tick']>0
    assert calls[0]['phase']=='post_timeline_combatzonetick'
    assert full.terminal_details['pending_callbacks']==[]
    assert full.terminal_details['end_resize'] is None
    at=calls[0]['executed_tick']
    np.testing.assert_array_equal(full.env_schedule[at,:4],[241,226,406,391])
    assert not np.array_equal(full.env_schedule[at-1,:4],[241,226,406,391])


def test_already_running_tlresume_has_no_timeline_clock_effect(tmp_path):
    initial=[133.,251.,508.,391.,0.,1.,0.,1/240,750.,0.,0.,0.,0.]
    waves=[]
    for suffix in ('',',TLResume'):
        path=source(tmp_path,'0,CombatZoneResize,241,226,406,391'+suffix+'\n0.5,EndAttack\n')
        waves.append(compile_wave(path,initial_environment=initial))
    np.testing.assert_array_equal(waves[0].env_schedule,waves[1].env_schedule)
    assert waves[0].source_events[-1][0]==waves[1].source_events[-1][0]


def test_overwriting_unknown_callback_cannot_erase_unproven_effects(tmp_path):
    path=source(tmp_path,'0,CombatZoneResize,133,251,508,391,SpawnLateAttack\n'
                '0.1,CombatZoneResize,133,251,508,391,TLResume\n0.1,EndAttack\n')
    wave=compile_wave(path)
    assert wave.terminal_details['end_resize'] is None
    assert len(wave.terminal_details['executed_callbacks'])==1
    assert wave.terminal_details['pending_callbacks'][0]['function']=='SpawnLateAttack'

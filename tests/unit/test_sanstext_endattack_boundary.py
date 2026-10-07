"""A later EndAttack never authorizes skipping an earlier live dialogue."""
import numpy as np
import pytest

from nohit.engine.compact_wave import compile_wave
from nohit.engine.parametric_environment import ParametricEnvironment
from nohit.engine.parametric_dag import solve_parametric


def source(tmp_path):
    path=tmp_path/'dialogue-before-end.csv'
    path.write_text('0,HeartMode,0\n0,BoneV,100,100,20,0,30\n'
                    '0,SansText,ab,\n0,SansText,c,\n0,EndAttack\n')
    return path


@pytest.mark.parametrize('backend',['compiler','reference','resumable'])
def test_default_endattack_policy_stops_before_dialogue_and_preserves_live_hazards(tmp_path,backend):
    path=source(tmp_path)
    options=dict(max_ticks=100,dt_schedule=[1/30]*100)
    if backend=='compiler':
        wave=compile_wave(path,allow_partial=True,**options)
    else:
        wave=ParametricEnvironment(path,backend=backend,**options).bind().wave
    assert not wave.complete
    assert wave.termination_reason=='dialogue_boundary'
    assert wave.terminal_details['pending_dialogue']['text']=='ab'
    assert wave.terminal_details['active_bones']==1
    assert not wave.terminal_details['timeline_exhausted']
    assert not any(command=='endattack' for _,command,_ in wave.source_events)
    assert len(wave.geometry_white[-1])==1
    assert np.isfinite(wave.geometry_white[-1]).all()


@pytest.mark.parametrize('policy',['endattack','eof_hazards_drained'])
def test_explicit_confirm_edges_resume_both_lines_before_endattack_clears_hazards(tmp_path,policy):
    template=ParametricEnvironment(source(tmp_path),termination_policy=policy,
                                   max_ticks=100,dt_schedule=[1/30]*100)
    boundary=template.bind()
    assert not boundary.complete and boundary.wave.termination_reason=='dialogue_boundary'
    parent=template.begin_controlled(boundary,previous_input_code=0)
    expected_chars=[1,2,1,1,1]
    expected_running=[False,True,False,False,True]
    # A held Confirm cannot dismiss the next line. Every wait tick keeps moving
    # the live bone; only the source EndAttack after both callbacks clears it.
    for tick,control in enumerate([0,32,32,0,32]):
        child=template.step_controlled(parent,control)
        assert child.status=='ready' and child.frame.tick==tick
        assert child.state.dialogue.current_char==expected_chars[tick]
        assert child.state.data['running']==expected_running[tick]
        assert child.frame.white.shape==(1,4)
        assert child.frame.white[0,0]==101.+tick
        assert not any(command=='endattack' for _,command,_ in child.frame.events)
        parent=child
    terminal=template.step_controlled(parent,0)
    assert terminal.status=='terminal' and terminal.reason=='endattack'
    assert terminal.frame.tick==5 and len(terminal.frame.white)==0
    assert [event[1] for event in terminal.frame.events]==['endattack']


def test_default_route_solver_cannot_claim_a_candidate_by_ignoring_dialogue(tmp_path):
    result=solve_parametric(source(tmp_path),[320.,304.,0.,0.,0.,0.,0.,1.,750.,0.,0.],
        dt_schedule=[1/30]*100,max_ticks=100,decision_ticks=1,allow_cancel=False,
        weights=[0,0,0,0])
    assert result['status']=='model_incomplete'
    assert result['model_termination_reason']=='dialogue_boundary'
    assert result['actions']==[] and result['complete_in_original_game'] is False

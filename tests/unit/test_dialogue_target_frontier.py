"""Dialogue continuation must bind each reachable player's actual observations."""
import numpy as np
import pytest

from nohit.engine.parametric_environment import ParametricEnvironment
from nohit.engine.joint_transition import begin_joint, step_joint


STATE=np.array([320.,304.,0.,0.,0.,0.,0.,1.,750.,0.,0.])


def fixture(tmp_path, tail, *, at_zero=False):
    path=tmp_path/'target-after-dialogue.csv'
    path.write_text('0,HeartMode,0\n'+('0' if at_zero else '0.033333')+',SansText,a,\n'+tail)
    template=ParametricEnvironment(path,dt_schedule=(1/30,)*100,max_ticks=100,
                                   termination_policy='eof_hazards_drained')
    return template,template.bind()


def replay(template,binding,initial,result):
    fresh=ParametricEnvironment(template.path,dt_schedule=template.dt_schedule,max_ticks=100,
                               termination_policy='eof_hazards_drained')
    origin=np.asarray(initial).reshape(-1,11)[result.origin_index]
    node=begin_joint(fresh,fresh.bind(binding.history),origin,previous_input_code=int(origin[4]))
    targets=list(binding.history)
    for index,control in enumerate(result.controls,1):
        edge=step_joint(fresh,node,control)
        assert edge.state is not None
        node=edge.state;targets.extend(node.environment.frame.target_history)
        assert np.asarray(node.player).tobytes()==result.trajectory[index].tobytes()
    assert node.environment.status=='terminal'
    assert tuple(targets)==result.target_history
    assert node.environment.identity==result.controlled_binding_identity


def test_public_csv_reports_full_history_and_base_provenance(tmp_path):
    from nohit.engine.csv_solver import solve_csv
    template,_=fixture(tmp_path,'0,GetHeartPos,x,y\n0,EndAttack\n')
    result=solve_csv(template.path,STATE,dt_schedule=template.dt_schedule,max_ticks=100,width=10)
    assert result['status']=='candidate_found' and result['verified']
    assert len(result['target_history'])==1
    provenance=result['environment_provenance']
    assert provenance['kind']=='controlled' and provenance['base_target_history']==[]
    assert provenance['base_binding_identity']==result['environment_binding_identity']
    assert provenance['final_binding_identity']==result['controlled_environment_binding_identity']
    assert provenance['base_binding_identity']!=provenance['final_binding_identity']


def test_tick_zero_known_target_prefix_is_verified_and_counted_once(tmp_path):
    from nohit.engine.csv_solver import solve_csv
    path=tmp_path/'tick-zero-history.csv'
    path.write_text('0,HeartMode,0\n0,GetHeartPos,x,y\n0,SansText,a,\n'
                    '0,GetHeartPos,u,v\n0,EndAttack\n')
    result=solve_csv(path,STATE,dt_schedule=(1/30,)*100,max_ticks=100,width=1,
                     initial_target_history=[[0,2,320.,304.]])
    assert result['verified'] and result['primed_initial_frame']
    assert [(row[0],row[1]) for row in result['target_history']]==[(0,2),(3,4)]
    assert result['target_history'][0]==[0,2,320.,304.]
    assert result['target_history'][1][2:]==result['trajectory'][3][:2]
    assert result['environment_provenance']['base_target_history']==[[0,2,320.,304.]]

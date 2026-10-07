import itertools
import pytest
import numpy as np
from nohit.engine.canonical_lattice import step,collision
from nohit.engine.adaptive_dag import search
from nohit.engine.canonical_solver import model_issues,solve_attack,ranking_weights
from nohit.engine.compact_wave import ROOT


def fixture(ticks=9):
    env=np.tile(np.array([133.,251.,508.,391.,1.,1.,0.,1/240]),(ticks,1))
    platforms=np.zeros((ticks,0,7))
    white=np.full((ticks,1,4),np.nan)
    blue=white.copy()
    initial=np.array([320.,377.81875,0.,0.,0.])
    return white,blue,env,platforms,initial


def test_frontier_search_matches_exhaustive_tiny_graph():
    w,b,e,p,s=fixture()
    w[-1,0]=[133,251,321,391]
    alphabet=list(itertools.product(range(-1,2),range(2)))
    witnesses=[]
    for route in itertools.product(alphabet,repeat=2):
        q=s.copy()
        safe=True
        for f,(ux,up) in enumerate(route):
            for m in range(1,5):
                t=f*4+m
                q=step(q,ux,up,e[t],p[t])
                if collision(w,b,t,q,0): safe=False
        if safe:witnesses.append(route)
    status,frame,_,_,route=search(w,b,e,p,s,max_nodes=1000)
    assert bool(witnesses)==(status==0)
    assert frame==2
    assert tuple(map(tuple,route)) in witnesses


def test_capacity_exhaustion_is_not_no_solution():
    assert search(*fixture(),max_nodes=1)[0]==2


def test_initial_collision_cannot_be_escaped_after_the_fact():
    w,b,e,p,s=fixture()
    w[0,0]=[310,370,330,385]
    assert search(w,b,e,p,s,max_nodes=100)[0]==1


def test_terminal_partial_frame_is_checked():
    w,b,e,p,s=fixture(6)
    w[-1,0]=[0,0,640,480]
    assert search(w,b,e,p,s,max_nodes=1000)[0]==1


def test_blue_bones_use_velocity_not_requested_keys():
    w,b,e,p,s=fixture()
    b[:,0]=[310,370,330,385]
    assert not collision(w,b,0,s,0)
    s[2]=.001
    assert collision(w,b,0,s,0)


def test_player_targeted_attack_requires_actual_initial_state_before_binding():
    path=ROOT/'c2-sans-fight/sans_randomblaster1.csv'
    assert any(x['reason']=='environment_depends_on_player_history' for x in model_issues(path))
    assert solve_attack(path)['status']=='initial_state_required'


def test_player_targeted_attack_receives_the_requested_forecast_policy(monkeypatch):
    import nohit.engine.canonical_solver as canonical
    captured={}
    def fake_solver(path,initial,**kwargs):
        captured.update(kwargs)
        return {'status':'resource_limit','planner':'parametric-demand-dag-dp'}
    monkeypatch.setattr(canonical,'solve_parametric',fake_solver)
    result=solve_attack(ROOT/'c2-sans-fight/sans_randomblaster1.csv',
        [320.,377.96875,0.,0.,0.],lookahead_policy='coast',lookahead=240)
    assert captured['lookahead_policy']=='coast' and captured['lookahead']==240
    assert result['lookahead_policy']=='coast' and result['lookahead']==240
    assert result['planner']=='canonical-dag-dp'
    assert result['environment_solver']=='parametric-demand-dag-dp'


def test_actual_initial_state_is_required():
    result=solve_attack(ROOT/'c2-sans-fight/sans_bonegap1.csv')
    assert result['status']=='initial_state_required'
    assert result['deadlock_proven'] is False


def test_static_random_program_is_eligible_but_player_targeting_is_not():
    assert model_issues(ROOT/'c2-sans-fight/sans_bonegap2.csv') == []


@pytest.mark.parametrize('row', ['0,HeartMode,2', '0,HeartMode,nan',
                                'nan,BoneV,100,200,10,0,30',
                                '0,BoneV,100,200,nan,0,30'])
def test_invalid_model_arguments_are_rejected(tmp_path, row):
    path=tmp_path/'invalid.csv'
    path.write_text(row+'\n1,EndAttack\n')
    assert model_issues(path)


@pytest.mark.parametrize('row', [
    '0,PlatForm,101,339,30,,,,,',
    '0,BoneV,288,229,65,,,,,',
    '0,BoneV,376,204,185,,,,,',
    '0,HeartMode,', '0,HeartMode', '0,HeartMode,1.9',
])
def test_native_numeric_empty_arguments_are_zero(tmp_path, row):
    path=tmp_path/'numeric-empty.csv'
    path.write_text(row+'\n1,EndAttack\n')
    assert model_issues(path)==[]


@pytest.mark.parametrize('row', [
    '0,Set,,1', '0,Add,,1,2', '0,Rnd,,2',
])
def test_empty_arithmetic_destinations_remain_invalid(tmp_path, row):
    path=tmp_path/'missing-name.csv'
    path.write_text(row+'\n1,EndAttack\n')
    assert any(issue['reason']=='missing_arguments'
               for issue in model_issues(path,allow_player_history=True))


def test_original_realhell_numeric_blanks_are_not_missing_arguments():
    path=next(ROOT.glob('Real HELL*.csv'))
    assert not any(issue['reason']=='missing_arguments'
                   for issue in model_issues(path,allow_player_history=True))


def test_original_realhell_is_eligible_only_with_explicit_eof_lifecycle():
    path=next(ROOT.glob('Real HELL*.csv'))
    assert any(issue['reason']=='missing_endattack'
               for issue in model_issues(path,allow_player_history=True))
    assert model_issues(path,allow_player_history=True,
                        termination_policy='eof_hazards_drained')==[]


@pytest.mark.parametrize('target',['','0,GetHeartPos,x,y\n'])
def test_public_eof_lifecycle_does_not_treat_persistent_hazards_as_finished(tmp_path,target):
    path=tmp_path/'persistent.csv'
    path.write_text(target+'0,BoneV,320,200,10,0,0\n')
    initial=[320,304,0,0,0,0,0,1,750,0,0]
    assert solve_attack(path,initial,max_ticks=8)['status']=='unsupported_mechanism'
    result=solve_attack(path,initial,max_ticks=8,termination_policy='eof_hazards_drained')
    assert result['status']=='resource_limit'
    assert result['model_termination_reason']=='tick_budget'
    assert not result['actions'] and not result['deadlock_proven']


def test_legacy_platform_kernel_rejects_another_wave():
    from nohit.engine.compact_solver import solve_platforms4hard
    with pytest.raises(ValueError,match='unsupported_mechanism'):
        solve_platforms4hard(ROOT/'c2-sans-fight/sans_bonegap1.csv',max_states=1)


def test_vm_does_not_return_a_completed_wave_when_endattack_is_unreachable():
    from nohit.engine.compact_wave import TimelineVM
    wave=TimelineVM(max_ticks=8).run([['200','EndAttack']])
    assert wave['complete'] is False
    assert wave['termination_reason']=='tick_budget'
    assert wave['ticks']==8


def test_red_diagonal_matches_original_replay_velocity():
    # Native counterexample: bonesgap1-20261006-010909-608853.json,
    # sans_boneslidev frame 78. Original sets each axis to 150, without normalization.
    w,b,e,p,s=fixture()
    e[:,4]=0
    s[:]=[320.,304.,0.,0.,0.]
    moved=step(s,1,-1,e[0],p[0])
    assert tuple(moved[2:4])==(150.,150.)


@pytest.mark.parametrize('weights', [[], {'unknown':1}, {'center':float('nan')},
    {'center':float('inf')}, {'switches':-1}, {'center':True}, {'center':'1'}])
def test_invalid_style_weights_are_rejected(weights):
    with pytest.raises(ValueError,match='weights'):
        ranking_weights(weights)


def test_partial_preferences_keep_defaults_and_zero_disables_all_rewards():
    assert ranking_weights({'switches':2.})==dict(clearance=1.,lookahead=1.,center=1.,switches=2.)
    zero=dict.fromkeys(('clearance','lookahead','center','switches'),0.)
    assert ranking_weights(zero)==zero



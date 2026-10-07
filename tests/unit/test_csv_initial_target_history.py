"""Native row-zero samples precede the observed post-row-zero player clamp."""
import copy

import numpy as np
import pytest

from nohit.dashboard.csv_visualization import build_csv_visualization
from nohit.engine.csv_solver import solve_csv
from nohit.engine.discrete_operator import sample_position, step_mask_into
from nohit.engine.parametric_environment import ParametricEnvironment


@pytest.fixture
def boundary_case(tmp_path):
    def make(tail='0.1,EndAttack\n'):
        path = tmp_path/'entry-target.csv'
        path.write_text('0,HeartMode,0\n0,CombatZoneSpeed,30\n'
                        '0,CombatZoneResize,100,100,500,400,\n'
                        '0,GetHeartPos,x,y\n0,BoneV,$x,100,10,0,0\n'+tail)
        bounds = [32, 240, 608, 384]
        env = bounds+[0,1,0,1/30,750,0,0,0,0,0]+bounds+bounds
        settings = dict(initial_environment=env, dt_schedule=(1/30,)*100, max_ticks=100)
        pre = np.array([45,300,0,0,0,0,0,1,750,0,0], dtype=float)
        template = ParametricEnvironment(path, **settings)
        truth = template.extend(template.bind(), 45., 300.)
        observed = pre.copy()
        step_mask_into(pre,0,truth.wave.env_schedule[0],truth.wave.platform_table[0],observed)
        assert observed[0] == 46 and truth.history == ((0,4,45.,300.),)
        return path, observed, settings, truth
    return make


@pytest.mark.parametrize('tail', ['0.1,EndAttack\n', '0,SansText,a,\n0,EndAttack\n',
                                 '0.1,SansText,a,\n0,EndAttack\n'])
def test_native_initial_sample_survives_frontier_scalar_prefix_and_visual_replay(boundary_case, tail):
    path, observed, settings, truth = boundary_case(tail)
    result = solve_csv(path, observed, **settings, initial_target_history=truth.history, width=1)
    assert result['verified'] and result['status'] == 'candidate_found', result
    assert result['initial_target_history'] == [[0,4,45.,300.]]
    assert result['target_history'][0] == [0,4,45.,300.]
    assert result['trajectory'][0] == observed.tolist()
    visual = build_csv_visualization(path,result,initial_environment=settings['initial_environment'],
                                     dt_schedule=settings['dt_schedule'])
    assert visual['frames'][0]['white'][0][0] == 45
    assert visual['frames'][0]['player'][0] == 46
    assert [f['player'] for f in visual['frames']] == result['trajectory']


@pytest.mark.parametrize('history', [[], [[1,4,45,300]], [[0,5,45,300]], [[0,4,45,300],[0,4,45,300]],
                                     [[False,4,45,300]], [[0,4.5,45,300]], [[0,4,float('nan'),300]],
                                     [[0,4,True,300]], [[0,4,45]], 'bad'])
def test_initial_observation_contract_rejects_missing_fabricated_or_future_reads(boundary_case, history):
    path, observed, settings, _ = boundary_case()
    with pytest.raises(ValueError):
        solve_csv(path,observed,**settings,initial_target_history=history,width=1)


def test_visualization_cannot_substitute_post_clamp_position_for_observed_sample(boundary_case):
    path, observed, settings, truth = boundary_case()
    result = solve_csv(path,observed,**settings,initial_target_history=truth.history,width=1)
    changed = copy.deepcopy(result)
    changed['initial_target_history'][0][2] = 46
    with pytest.raises(ValueError, match='history|sample|identity'):
        build_csv_visualization(path,changed,initial_environment=settings['initial_environment'],
                                 dt_schedule=settings['dt_schedule'])


def test_future_target_is_still_sampled_from_its_own_movement_phase(boundary_case):
    path, observed, settings, truth = boundary_case('0.1,GetHeartPos,nextx,nexty\n'
                                                  '0,BoneV,$nextx,100,10,0,0\n0.1,EndAttack\n')
    result = solve_csv(path,observed,**settings,initial_target_history=truth.history,width=3)
    assert result['verified']
    assert len(result['target_history']) == 2
    tick, line, x, y = result['target_history'][1]
    assert tick > 0 and x != 45
    wave = ParametricEnvironment(path,**settings).bind(truth.history).wave
    actual = sample_position(np.asarray(result['trajectory'][tick-1]),
                             wave.env_schedule[tick],wave.platform_table[tick])
    assert (x,y) == actual
    assert result['initial_target_history'] == [[0,4,45.,300.]]
    visual = build_csv_visualization(path,result,initial_environment=settings['initial_environment'],
                                     dt_schedule=settings['dt_schedule'])
    assert visual['frames'][tick]['white'][1][0] == x


def test_multiple_initial_reads_retain_intervening_teleport_and_reject_partial_history(tmp_path):
    path = tmp_path/'multiple-initial.csv'
    path.write_text('0,GetHeartPos,x,y\n0,BoneV,$x,100,10,0,0\n'
                    '0,HeartTeleport,200,300\n0,GetHeartPos,x,y\n'
                    '0,BoneV,$x,100,10,0,0\n0.1,EndAttack\n')
    settings = dict(dt_schedule=(1/30,)*100,max_ticks=100,width=1)
    observed = [200.,300.,0.,0.,0.,0.,0.,1.,750.,0.,0.]
    history = [[0,1,45.,300.],[0,4,200.,300.]]
    result = solve_csv(path,observed,**settings,initial_target_history=history)
    assert result['verified'] and result['target_history'] == history
    visual = build_csv_visualization(path,result,dt_schedule=settings['dt_schedule'])
    assert [row[0] for row in visual['frames'][0]['white']] == [45.,200.]
    with pytest.raises(ValueError,match='omits'):
        solve_csv(path,observed,**settings,initial_target_history=history[:1])
    changed = copy.deepcopy(history);changed[1][2] = 199.
    with pytest.raises(ValueError,match='teleport|source'):
        solve_csv(path,observed,**settings,initial_target_history=changed)


def test_explicit_empty_history_is_valid_only_when_source_has_no_initial_reads(tmp_path):
    path = tmp_path/'no-initial-read.csv';path.write_text('0.1,EndAttack\n')
    initial = [320.,304.,0.,0.,0.,0.,0.,1.,750.,0.,0.]
    settings = dict(dt_schedule=(1/30,)*100,max_ticks=100,width=1)
    result = solve_csv(path,initial,**settings,initial_target_history=[])
    assert result['verified'] and result['initial_target_history'] == []
    with pytest.raises(ValueError,match='source program'):
        solve_csv(path,initial,**settings,initial_target_history=[[0,1,320.,304.]])


@pytest.mark.parametrize('tail',['0.1,EndAttack\n','0.1,SansText,a,\n0,EndAttack\n'])
def test_initial_arena_recipe_survives_candidate_scalar_prefix_and_visualization(tmp_path,tail):
    path = tmp_path/'inherited-arena.csv';path.write_text('0,HeartMode,0\n'+tail)
    bounds = [32,240,608,384]
    env = bounds+[0,1,0,1/30,750,0,0,0,0,0]+bounds+bounds
    arena = dict(target=[100,100,500,400],size=[576,144],speed=30,callback='')
    initial = [320.,304.,0.,0.,0.,0.,0.,1.,750.,0.,0.]
    settings = dict(initial_environment=env,initial_arena=arena,dt_schedule=(1/30,)*100,max_ticks=100)
    result = solve_csv(path,initial,**settings,initial_target_history=[],width=1)
    assert result['verified'], result
    assert result['initial_arena']['target'] == (100.,100.,500.,400.)
    # The result carries enough source-world state for the renderer's default.
    visual = build_csv_visualization(path,result,initial_environment=env,dt_schedule=settings['dt_schedule'])
    wave = ParametricEnvironment(path,**settings).bind().wave
    assert visual['frames'][0]['env'] == wave.env_schedule[0].tolist()
    assert visual['frames'][0]['bounds'] != bounds
    wrong = dict(arena,speed=31)
    with pytest.raises(ValueError,match='identity'):
        build_csv_visualization(path,result,initial_environment=env,initial_arena=wrong,
                                 dt_schedule=settings['dt_schedule'])

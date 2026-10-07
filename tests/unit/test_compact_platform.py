import json
from pathlib import Path
import numpy as np

from nohit.engine.compact_platform import Player, Platform, microstep, platform_at
from nohit.engine.compact_lattice import native_micro, same_state, state_hash
from nohit.engine.compact_wave import ROOT, compile_wave, prepare_collision, prepare_collision_native
from nohit.engine.compact_lattice import blocked, search, search_depth_first, product_micro_into, search_frs_dp_bellman


def test_original_microstep_differential():
    fixture = json.loads((Path(__file__).parents[1] / 'fixtures/platforms4hard-microsteps.json').read_text())
    for case in fixture['cases']:
        first = case['initial']
        state = Player(*(first[k] for k in ('x', 'y', 'dx', 'dy')))
        for tick, row in enumerate(case['rows'], 1):
            if row['ended']:
                break  # EndAttack/menu reset is outside the player transition.
            platform = platform_at(tick)
            assert abs(platform.x - row['platforms'][0]['x']) < 1e-8
            state = microstep(state, row['action'], platform, row['dt'])
            for key in ('x', 'y', 'dx', 'dy'):
                assert abs(getattr(state, key) - row[key]) < 1e-8, (case['name'], tick, key, state, row)


def test_fractional_states_are_not_merged():
    a = Player(175, 327.95, 90, 0, 0)
    b = Player(175, 327.950000001, 90, 0, 0)
    assert a != b
    assert len({a, b}) == 2


def test_native_model_original_differential():
    fixture=json.loads((Path(__file__).parents[1]/'fixtures/platforms4hard-microsteps.json').read_text())
    for case in fixture['cases']:
        first=case['initial']
        s=np.array([first[k] for k in ('x','y','dx','dy')]+[0.0])
        for tick,row in enumerate(case['rows'],1):
            if row['ended']:
                break
            p=platform_at(tick)
            schedule=np.array([p.x,p.y,p.width,p.height,p.dx,p.dy,row['dt']])
            s=native_micro(s,*row['action'],schedule)
            for actual,key in zip(s,('x','y','dx','dy')):
                assert abs(actual-row[key])<1e-8,(case['name'],tick,key,actual,row[key])


def test_exact_equality_preserves_jump_edge_and_subpixel_position():
    s=np.array([175.,327.95,90.,0.,0.])
    assert same_state(s,s.copy())
    for field in range(5):
        changed=s.copy()
        changed[field]=np.nextafter(changed[field],np.inf)
        assert not same_state(s,changed)
    assert len({int(state_hash(s)),int(state_hash(s+1))})==2


def test_compiled_environment_matches_original_in_relevant_domain():
    schedule,geometry,initial=compile_wave(ROOT/'c2-sans-fight/sans_platforms4hard.csv')
    original=json.loads((ROOT/'tools/real-game/platforms4hard-environment-capture.json').read_text())['frames']
    for tick,actual in enumerate(geometry[:-1]):
        expected=np.asarray(original[tick])[:,:4]
        for box in actual:
            if box[0]<550 and box[2]>110 and box[1]<395 and box[3]>225:
                assert np.min(np.max(np.abs(expected-box),axis=1))<1e-8,(tick,box)
        for box in expected:
            if box[0]<550 and box[2]>110 and box[1]<395 and box[3]>225:
                assert np.min(np.max(np.abs(actual-box),axis=1))<1e-8,(tick,box)
    assert len(schedule)==1753
    assert np.isfinite(initial).all()


def test_collision_fractional_anchor_indices_do_not_accumulate_offsets():
    mask=np.zeros((1,160,7),np.uint64)
    s=np.array([175.25,327.95,0.,0.,0.])
    assert not blocked(mask,0,s)
    x,y=176-113,328-231
    mask[0,y,x//64]=np.uint64(1)<<np.uint64(x%64)
    assert blocked(mask,0,s)


def test_search_resource_failure_is_explicit_and_short_witness_is_complete():
    schedule,geometry,initial=compile_wave(ROOT/'c2-sans-fight/sans_platforms4hard.csv')
    mask=prepare_collision(geometry[:9])
    status,depth,_,_,_,end=search(mask,schedule[:9],initial,1,10)
    assert status==2 and end==-1
    status,depth,_,_,route=search_depth_first(mask,schedule[:9],initial,100,100)
    assert status==0 and depth==2 and len(route)==2
    status,_,_,_,route=search_depth_first(mask,schedule[:9],initial,0,100)
    assert status==2 and len(route)==0


def test_unknown_csv_is_rejected(tmp_path):
    path=tmp_path/'custom.csv'
    path.write_text('0,GetHeartPos,X,Y\n')
    import pytest
    with pytest.raises(ValueError,match='unsupported_mechanism'):
        compile_wave(path)


def test_native_collision_operator_is_bit_identical_to_reference():
    _,geometry,_=compile_wave(ROOT/'c2-sans-fight/sans_platforms4hard.csv')
    for margin in (0.,1.25):
        assert np.array_equal(prepare_collision(geometry,margin),prepare_collision_native(geometry,margin))


def test_product_state_keeps_every_initial_condition():
    state=np.tile(np.array([175.,327.,0.,58.5,0.]),3)
    for field in (8,13,14):
        changed=state.copy()
        changed[field]=np.nextafter(changed[field],np.inf)
        assert not same_state(state,changed)


def test_product_collision_rejects_a_hit_in_a_nonfirst_member():
    schedule,geometry,initial=compile_wave(ROOT/'c2-sans-fight/sans_platforms4hard.csv')
    mask=prepare_collision(geometry[:9])
    product=np.tile(initial,2)
    product[5:10]=[290.,350.,0.,0.,0.]
    status,_,_,_,route=search_depth_first(mask,schedule[:9],product,100,100)
    assert status==1 and len(route)==0


def test_product_9member_clock_profiles_diverge():
    schedule,_,initial=compile_wave(ROOT/'c2-sans-fight/sans_platforms4hard.csv')
    state=np.tile(initial,9)
    for tick in range(1,9):
        product_micro_into(state,0,1,schedule[tick],state,tick)
    m0_y,m3_y,m6_y=state[1],state[16],state[31]
    assert abs(m3_y-m0_y)>1e-4
    assert abs(m6_y-m0_y)>1e-4
    assert abs(m6_y-m3_y)>1e-4


def test_product_9member_collision_rejects_each_nonnominal_member_in_frs_dp():
    schedule,geometry,initial=compile_wave(ROOT/'c2-sans-fight/sans_platforms4hard.csv')
    mask=prepare_collision_native(geometry[:9])
    base=np.tile(initial,9)
    for m in range(1,9):
        product=base.copy()
        product[m*5:m*5+5]=[290.,350.,0.,0.,0.]
        status,_,_,_,route=search_frs_dp_bellman(mask,schedule[:9],product,max_states=100,max_beam=10)
        assert status==1 and len(route)==0


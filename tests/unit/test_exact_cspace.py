"""Sound cell classifications and continuous queries, including rotated beams."""
from types import SimpleNamespace
import numpy as np
import pytest
from nohit.engine.cspace import bake_cspace,collision_query,quad_intersects_box
from nohit.engine.compact_wave import TimelineVM,compile_wave,ROOT,native_fixed_dt


def wave(rectangles=(),polygons=(),blue=()):
    return SimpleNamespace(env_schedule=np.zeros((1,8)),
        geometry_white=np.array(rectangles,dtype=float).reshape(1,-1,4),
        geometry_blue=np.array(blue,dtype=float).reshape(1,-1,4),
        geometry_polygons=np.array(polygons,dtype=float).reshape(1,-1,8),
        dimensions=(32,32),origin=(0,0))


def query(w,b,x,y,moving=False,margin=0.):
    return collision_query(w.geometry_white,w.geometry_blue,0,
        np.array([x,y,float(moving),0.,0.]),margin,b.payload)


def test_subpixel_boundary_never_rounded_to_whole_cell():
    w=wave([[10.125,5.,12.,25.]])
    for cell in (1.,4.,7.):
        b=bake_cspace(w,cell)
        assert not query(w,b,8.124999,10.)
        assert query(w,b,8.125,10.)
        assert query(w,b,8.125001,10.)


def test_rotated_beam_does_not_fill_aabb_corners():
    w=wave(polygons=[[4.,6.,6.,4.,26.,24.,24.,26.]])
    b=bake_cspace(w)
    assert not query(w,b,5.,24.)
    assert query(w,b,15.,15.)
    assert not query(w,b,15.,22.)
    assert query(w,b,15.,22.,margin=3.)


def test_random_continuous_points_match_exact_reference_for_all_cell_sizes():
    rng=np.random.default_rng(743)
    w=wave([[7.13,4.37,8.91,27.34]],[[4.,6.,6.,4.,26.,24.,24.,26.]],
           [[20.45,1.9,22.34,7.12]])
    points=rng.uniform(-2.,34.,(3000,2))
    for size in (1.,4.,11.):
        b=bake_cspace(w,size)
        for x,y in points:
            for moving in (False,True):
                expected=False
                for box in list(w.geometry_white[0])+list(w.geometry_blue[0] if moving else []):
                    expected|=x+2>=box[0] and x-2<=box[2] and y+2>=box[1] and y-2<=box[3]
                expected|=quad_intersects_box(w.geometry_polygons[0,0],x,y,2.,2.)
                assert query(w,b,x,y,moving)==expected


def test_blue_plane_and_slam_damage_are_independent_of_preferences():
    w=wave(blue=[[10.,10.,20.,20.]])
    b=bake_cspace(w)
    assert not query(w,b,15.,15.)
    assert query(w,b,15.,15.,True)
    state=np.zeros(11);state[:2]=[1.,1.];state[10]=1.
    assert collision_query(w.geometry_white,w.geometry_blue,0,state,0.,b.payload)


def test_sine_bones_direction_matches_source_and_signed_heights():
    for spacing,expected_x,expected_dx in ((-24,133.+1.5,1.5),(24,508.-1.5,-1.5)):
        sim=TimelineVM().run([['0','SineBones','20',str(spacing),'360','25'],['.02','EndAttack']])
        assert sim['geom_white'][0,0,0]==expected_x
        assert sim['geom_white'][1,0,0]-sim['geom_white'][0,0,0]==expected_dx
        # i=14 has a negative top height; it remains a signed source bone.
        assert sim['geom_white'][0,28,1]<257.


def test_player_targeting_requires_observed_history():
    rows=[['0','GetHeartPos','x','y'],['.02','EndAttack']]
    with pytest.raises(ValueError,match='player_history_required'):
        TimelineVM().run(rows)
    sim=TimelineVM(heart_samples={0:(123.,234.)}).run(rows)
    assert sim['player_dependent']
    assert sim['source_events'][0][1]=='getheartpos'


def test_intro_has_exact_polygon_beams_and_complete_reset_events():
    w=compile_wave(ROOT/'c2-sans-fight/sans_intro.csv')
    assert w.geometry_polygons.shape[2]==8
    assert np.isfinite(w.geometry_polygons).any()
    assert np.count_nonzero(w.env_schedule[:,6])==1
    assert w.env_schedule.shape[1]==22
    assert any(e[1]=='heartteleport' for e in w.source_events)


def test_actual_timestamp_arithmetic_preserves_native_timer_boundary():
    # This dt was directly observed in original jcw diagnostics near 4 seconds.
    clock=native_fixed_dt(4096.,80)
    assert clock[1]==0.00416666666666697
    rows=[['0','GasterBlaster','1','100','100','100','100','0','0','.1'],['.3','EndAttack']]
    actual=TimelineVM(dt_schedule=clock).run(rows)
    ideal=TimelineVM().run(rows)
    def first_beam(sim):return int(np.flatnonzero(np.isfinite(sim['geometry_polygons'][:,:,0]).any(axis=1))[0])
    assert first_beam(actual)==24
    assert first_beam(ideal)==25

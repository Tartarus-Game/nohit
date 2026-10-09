import math
import time

import numpy as np
import pytest

from nohit.engine.native_dynamic import _world
from nohit.engine.parametric_environment import ParametricEnvironment
from nohit.engine.source_oracle import scalar_module
from nohit.engine.source_verification import certify_observed,scalar_collision_checker


@pytest.mark.parametrize('text',[
    '0,HeartMode,0\n0.01,GetHeartPos,x,y\n0,HeartTeleport,330,300\n0,GetHeartPos,a,b\n0.1,EndAttack\n',
    '0,HeartMode,1\n0,Platform,285,350,60,0,42\n0.05,GetHeartPos,x,y\n'
    '0,BlackScreen,1\n0,Platform,300,360,60,2,20\n0,GetHeartPos,a,b\n'
    '0,CombatZoneResizeInstant,140,200,500,400\n0.05,GetHeartPos,c,d\n0.1,EndAttack\n',
    '0,HeartMode,0\n'+('0.004166666666666667,GetHeartPos,x,y\n'*120)+'0,EndAttack\n',
])
def test_linear_certifier_preserves_source_observation_phase_and_rejects_mutations(tmp_path,text):
    path=tmp_path/'observed.csv';path.write_text(text)
    initial=[320.,304.,0.,0.,0.,0.,1.,1.,750.,0.,0.]
    settings=dict(dt_schedule=[1/240]*1000,max_ticks=1000,seed=42)
    proposal=[(i//8)%4 for i in range(1000)]
    built=_world(path,initial,settings,proposal,False,False,None,time.perf_counter()+5)
    _,binding,trace,confirms,safe,word=built;assert safe
    verified=certify_observed(path,initial,settings,word,trace,None)
    assert verified is not None and verified[1]==binding.history
    bad=trace.copy();bad[2,0]+=1e-8
    assert certify_observed(path,initial,settings,word,bad,None) is None


def test_padding_trim_retains_internal_holes_infinite_rectangles_and_closed_quad_contact():
    from types import SimpleNamespace
    white=np.array([[[math.nan]*4,[-math.inf,-100.,-5.,100.],[math.nan]*4]])
    blue=np.array([[[20.,20.,30.,30.],[math.nan]*4]])
    polygons=np.array([[[math.nan]*8,[0.,0.,10.,0.,10.,10.,0.,10.],[math.nan]*8]])
    wave=SimpleNamespace(geometry_white=white,geometry_blue=blue,geometry_polygons=polygons)
    check=scalar_collision_checker(wave);source=scalar_module('cspace')
    data=(np.empty((1,2,0,0),np.uint8),polygons,0.,0.,1.)
    for x in (-7.,-3.,12.,12.+1e-9,25.):
        for moving in (0.,1.):
            state=np.array([x,5.,moving,0.,0.,0.,0.,1.,750.,0.,0.])
            assert check(0,state)==source.collision_query(white,blue,0,state,0.,data)


def test_clock_is_frozen_once_without_changing_full_suffix_identity(tmp_path):
    path=tmp_path/'clock.csv';path.write_text('0,EndAttack\n')
    values=[1/240,1/120,1/30]
    first=ParametricEnvironment(path,dt_schedule=values)
    second=ParametricEnvironment(path,dt_schedule=first.dt_schedule)
    assert second.dt_schedule is first.dt_schedule
    values[-1]=1/60
    assert first.dt_schedule[-1]==1/30
    assert first._clock_identity==second._clock_identity
    assert first._clock_identity!=ParametricEnvironment(path,dt_schedule=values)._clock_identity
    with pytest.raises(AttributeError):first.dt_schedule.identity=b'changed'

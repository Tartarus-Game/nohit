"""Owned collection removes per-tick copies without weakening branch isolation."""
import pickle

import numpy as np

from nohit.engine.parametric_environment import ParametricEnvironment
from nohit.engine.resumable_wave import (
    EnvState, initialize, advance_one_tick, _advance_owned_tick, TickCommitted,
)


def test_owned_ticks_match_pure_operator_and_do_not_mutate_retained_frames(tmp_path):
    path=tmp_path/'entities.csv'
    path.write_text('0,Platform,220,340,50,0,80,1\n'
                    '0,BoneV,480,100,120,2,100,1\n'
                    '0,BoneStab,1,30,0.05,0.2\n'
                    '0,GasterBlaster,0,0,240,250,250,35,0.05,0.2\n'
                    '0.1,CombatZoneResize,140,120,480,390\n0.2,EndAttack\n')
    pure=initialize(path);owned=initialize(path)
    retained=[]
    for _ in range(100):
        before=pickle.dumps(pure)
        expected=advance_one_tick(pure)
        assert pickle.dumps(pure)==before
        actual=_advance_owned_tick(owned)
        assert actual.state is owned
        assert type(actual) is type(expected)
        assert pickle.dumps(actual.state)==pickle.dumps(expected.state)
        assert pickle.dumps(actual.frame)==pickle.dumps(expected.frame)
        retained.append((actual.frame,pickle.dumps(actual.frame)))
        pure=expected.state
        if not isinstance(actual,TickCommitted):break
    else:raise AssertionError('fixture did not terminate')
    for frame,snapshot in retained:
        assert pickle.dumps(frame)==snapshot


def test_collector_clones_at_branch_boundaries_not_each_tick(tmp_path,monkeypatch):
    path=tmp_path/'branches.csv'
    path.write_text('0,Platform,220,340,50,0,80,1\n'
                    '0,BoneV,480,100,120,2,100,1\n'
                    '0,BoneStab,1,30,0.05,0.2\n'
                    '0,GasterBlaster,0,0,240,250,250,35,0.05,0.2\n'
                    '0.1,GetHeartPos,x,y\n0,BoneV,$x,$y,10,0,20\n'
                    '0.1,GetHeartPos,x,y\n0.1,EndAttack\n')
    copies=[];original=EnvState.clone
    def counted(state):
        copies.append(state.data['tick'])
        return original(state)
    monkeypatch.setattr(EnvState,'clone',counted)
    template=ParametricEnvironment(path,max_ticks=100)
    parent=template.bind()
    # The only clone is the unresolved-observation preview.
    assert len(copies)==1
    snapshot=pickle.dumps(parent)
    for position in ((100.,200.),(300.,320.)):
        count=len(copies)
        child=template.extend(parent,*position)
        assert len(copies)-count==2  # branch ownership plus boundary preview
        assert pickle.dumps(parent)==snapshot
        reference=ParametricEnvironment(path,max_ticks=100,backend='reference').bind(child.history)
        for name in ('env_schedule','platform_table','geometry_white','geometry_blue','geometry_polygons'):
            a,b=np.asarray(getattr(child.wave,name)),np.asarray(getattr(reference.wave,name))
            assert a.shape==b.shape
            assert a.tobytes()==b.tobytes(),name
        assert child.wave.source_events==reference.wave.source_events
        assert child.wave.target_history==reference.wave.target_history

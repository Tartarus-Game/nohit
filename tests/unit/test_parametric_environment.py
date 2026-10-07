"""Player observations bind new environment branches; prefixes are not wins."""
import numpy as np
import pytest
from nohit.engine.parametric_environment import ParametricEnvironment


def test_distinct_target_histories_keep_distinct_beam_geometry(tmp_path):
    path=tmp_path/'targets.csv'
    path.write_text('0,GetHeartPos,x,y\n'
                    '0,GasterBlaster,1,$x,$y,$x,$y,0,0,0.1\n'
                    '0.4,GetHeartPos,x2,y2\n'
                    '0.4,EndAttack\n')
    template=ParametricEnvironment(path)
    root=template.bind()
    assert not root.complete and root.resolved_through_tick==-1
    assert root.pending_target['tick']==0
    a=template.extend(root,100.125,200.)
    b=template.extend(root,101.126,200.)
    near=template.extend(root,100.126,200.)
    assert a.identity!=b.identity
    assert a.identity!=near.identity  # Source int() geometry does not erase history.
    assert not a.complete and not b.complete
    assert template.extend(root,100.125,200.) is a
    active=np.isfinite(a.wave.geometry_polygons[:,:,0])
    assert active.any()
    assert np.max(np.abs(a.wave.geometry_polygons[active]-b.wave.geometry_polygons[active]))>0.
    final=template.extend(a,300.,300.)
    assert final.complete and final.pending_target is None
    assert len(final.wave.target_history)==2
    assert root.history==()  # Extending does not mutate sibling/ancestor states.


def test_prior_same_tick_teleport_is_applied_before_sampling(tmp_path):
    path=tmp_path/'teleport.csv'
    path.write_text('0,HeartTeleport,321,299\n0,GetHeartPos,x,y\n0.1,EndAttack\n')
    template=ParametricEnvironment(path)
    root=template.bind()
    assert root.pending_target['preceding_teleport']==(321.,299.)
    bound=template.extend(root,2.,3.)
    assert bound.history[0][2:]==(321.,299.)


def test_binding_rejects_observations_not_consumed_by_program(tmp_path):
    path=tmp_path/'bad.csv';path.write_text('0.1,GetHeartPos,x,y\n0.1,EndAttack\n')
    with pytest.raises(ValueError,match='does not match'):
        ParametricEnvironment(path).bind(((999,2,1.,2.),))

"""Native Fire hotspot controls the exact outside-layout stopping tick."""
import json
import math
from pathlib import Path

import numpy as np
import pytest

from nohit.engine.compact_wave import _ActiveGasterBlaster,_blaster_fire_bbox


def test_all_original_fire_frames_have_the_declared_geometry():
    root=Path(__file__).resolve().parents[2]
    types=json.loads((root/'c2-sans-fight/data.js').read_text(encoding='utf-8-sig'))['project'][3]
    sprite=next(row for row in types if row[11]==7974524067202295)
    fire=next(animation for animation in sprite[7] if animation[0]=='Fire')
    assert len(fire[7])==5
    assert all(frame[4:6]==[57,44] and frame[7:9]==[0.5087719559669495,0.5] for frame in fire[7])


def test_first_original_native_divergence_stops_at_tick_876():
    # Original linear trace tick 293931 (model 875), blaster UID 161.
    # Native bbox bottom is already -0.6483875755051116. The old centred
    # approximation said +0.05872 and incorrectly took another 8.625px step.
    b=_ActiveGasterBlaster(1,451,136,451,136,135,0,.155)
    b.x=658.3590635868175;b.y=-71.35906358681744
    b.angle=135.;b.state=3;b.leave_speed=2040.;b.beam_timer=.28333333333861097
    b.base_size=70.;b.damage=True
    before=(b.x,b.y)
    bbox=_blaster_fire_bbox(b.x,b.y,math.cos(math.radians(135)),math.sin(math.radians(135)),2.,2.)
    np.testing.assert_allclose(bbox,[587.6483875755051,-143.4839573751877,730.4839573751877,-.6483875755051116],atol=2e-13,rtol=0)
    assert b.step(.004166666666744277)
    assert (b.x,b.y)==before
    assert b.leave_speed==0.


@pytest.mark.parametrize('angle',[-.000001,0,45,89.999999,90,135,180,225,270,315,359.999999])
@pytest.mark.parametrize('size',[0,1,2])
def test_bbox_matches_independent_rotated_corners_at_extreme_angles(angle,size):
    b=_ActiveGasterBlaster(size,0,0,0,0,0,0,1)
    a=math.radians(angle);ux,uy=math.cos(a),math.sin(a)
    width=57*b.scale_x;height=44*b.scale_y
    points=[]
    for vx,vy in ((0,0),(1,0),(1,1),(0,1)):
        lx=(vx-.5087719559669495)*width;ly=(vy-.5)*height
        points.append([123+ux*lx-uy*ly,234+uy*lx+ux*ly])
    points=np.asarray(points)
    expected=[points[:,0].min(),points[:,1].min(),points[:,0].max(),points[:,1].max()]
    np.testing.assert_allclose(_blaster_fire_bbox(123,234,ux,uy,b.scale_x,b.scale_y),expected,atol=1e-13,rtol=0)


@pytest.mark.parametrize('angle',[0,45,90,135,180,225,270,315])
@pytest.mark.parametrize('side',['left','right','top','bottom'])
def test_outside_stop_on_each_rotated_boundary(angle,side):
    a=math.radians(angle);ux,uy=math.cos(a),math.sin(a)
    bounds=_blaster_fire_bbox(0,0,ux,uy,2,2)
    # Put exactly the selected extent at the boundary, then move 1e-7 on
    # each side. Other coordinates stay inside the viewport.
    for outside in (False,True):
        epsilon=1e-7 if outside else -1e-7
        x,y=320.,240.
        if side=='left':x=-bounds[2]-epsilon
        elif side=='right':x=640-bounds[0]+epsilon
        elif side=='top':y=-bounds[3]-epsilon
        else:y=480-bounds[1]+epsilon
        b=_ActiveGasterBlaster(1,0,0,0,0,angle,0,1)
        b.x=x;b.y=y;b.state=3;b.leave_speed=1000.;b.damage=True
        b.step(1/240)
        assert b.leave_speed==(0. if outside else 1030.)
        if outside:assert (b.x,b.y)==(x,y)

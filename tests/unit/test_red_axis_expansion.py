import numpy as np
import pytest
from nohit.engine.compact_wave import compile_wave
from nohit.engine.cspace import bake_cspace
from nohit.engine.local_relation import _expand
from nohit.engine.red_axis_expansion import expand_red_axes,compact_red_axis_step


@pytest.mark.parametrize('hold',[1,4])
def test_all_edges_equal_full_operator_including_boundary_fallback(tmp_path,hold):
    p=tmp_path/'red.csv';p.write_text('0,HeartMode,0\n0,BoneV,330,280,20,0,0\n0.2,EndAttack\n')
    w=compile_wave(p);space=bake_cspace(w);b=w.env_schedule[1,:4]
    states=[]
    for x in [b[0]+13,np.nextafter(b[0]+13,np.inf),320.,b[2]-13]:
        for y in [b[1]+13,np.nextafter(b[1]+13,np.inf),304.,b[3]-13]:
            for dx,dy in [(150.,-150.),(-150.,150.),(0.,0.),(600.,0.)]:
                states.append([x,y,dx,dy,5.,0.,0.,1.,750.,0.,0.])
    states=np.array(states);controls=np.arange(32,dtype=np.int64)
    actual=expand_red_axes(w,states,controls,0,hold,space)
    expected=_expand(states,controls,0,hold,w.env_schedule,w.platform_table,w.geometry_white,w.geometry_blue,space.payload)
    assert actual is not None
    for got,want in zip(actual[:3],expected):assert got.tobytes()==want.tobytes()
    assert actual[3]['full_operator_edges'] and actual[3]['fast_joint_edges']
    packed=compact_red_axis_step(w,states,controls,0,hold,space)
    assert {s.tobytes() for s in packed[0]}=={s.tobytes() for s in expected[0]}
    edges={(int(p),int(m)):s.tobytes() for s,p,m in zip(*expected)}
    for s,p,m in zip(*packed[:3]):assert s.tobytes()==edges[(int(p),int(m))]


def test_unsupported_mode_returns_unknown_not_empty(tmp_path):
    p=tmp_path/'blue.csv';p.write_text('0,HeartMode,1\n0.2,EndAttack\n')
    w=compile_wave(p);space=bake_cspace(w)
    s=np.array([[320.,304.,0.,0.,0.,0.,1.,1.,750.,0.,0.]])
    assert expand_red_axes(w,s,np.arange(16,dtype=np.int64),0,4,space) is None


def test_packed_ids_are_exact_and_keep_actual_mask_and_predecessor(tmp_path):
    p=tmp_path/'red.csv';p.write_text('0,HeartMode,0\n0.2,EndAttack\n')
    w=compile_wave(p);space=bake_cspace(w);controls=np.arange(32,dtype=np.int64)
    s=np.array([[320.,304.,0.,0.,0.,0.,0.,1.,750.,0.,0.],
                [np.nextafter(320.,np.inf),304.,150.,-150.,15.,0.,0.,1.,750.,0.,0.]])
    reference=_expand(s,controls,0,4,w.env_schedule,w.platform_table,w.geometry_white,w.geometry_blue,space.payload)
    actual=compact_red_axis_step(w,s,controls,0,4,space)
    assert actual[3]['packed']
    assert {row.tobytes() for row in actual[0]}=={row.tobytes() for row in reference[0]}
    edges={(int(p),int(m)):row.tobytes() for row,p,m in zip(*reference)}
    for row,p,m in zip(*actual[:3]):assert row.tobytes()==edges[(int(p),int(m))]

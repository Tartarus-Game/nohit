"""Exact committed-state equality is independent of historical evidence."""
import copy
import struct

import numpy as np
import pytest

from nohit.engine.environment_state_key import encode_typed,encode_environment_state,REQUIRED_STATE_FIELDS
from nohit.engine.parametric_environment import ParametricEnvironment


def snapshot():
    state=dict.fromkeys(REQUIRED_STATE_FIELDS,None)
    state.update(phase='post_world_tick',vars={'x':1.},active_blasters=[],next_tick=4)
    return state


def test_typed_encoding_is_injective_for_ambiguous_python_values():
    values=[None,False,True,0,1,0.,-0.,1.,'1','1.0',b'1',(),[],{},
            ('ab','c'),('a','bc'),[1,2],(1,2),np.float64(1),np.int64(1)]
    assert len({encode_typed(value) for value in values})==len(values)
    assert encode_typed({'b':2,'a':1})==encode_typed({'a':1,'b':2})
    a=struct.unpack('<d',struct.pack('<Q',0x7ff8000000000001))[0]
    b=struct.unpack('<d',struct.pack('<Q',0x7ff8000000000002))[0]
    assert encode_typed(a)!=encode_typed(b)


def test_all_declared_snapshot_fields_participate_in_the_key():
    original=snapshot();key=encode_environment_state(original)
    for name in REQUIRED_STATE_FIELDS-{'phase'}:
        modified=copy.deepcopy(original);modified[name]=('changed',modified[name])
        assert encode_environment_state(modified)!=key,name
    with pytest.raises(ValueError,match='missing fields'):
        encode_environment_state({'phase':'post_world_tick'})
    original['phase']='await_target'
    with pytest.raises(ValueError,match='committed'):
        encode_environment_state(original)


def pair(tmp_path,tail='0.025,EndAttack\n'):
    path=tmp_path/'state_key.csv'
    path.write_text('0,GetHeartPos,hx,hy\n0,BoneV,$hx,100,20,0,0\n'
                    '0.0125,BlackScreen,1\n0,HeartTeleport,320,304\n'
                    '0,Set,hx,320\n0,Set,hy,304\n'+tail)
    template=ParametricEnvironment(path,max_ticks=100,capture_state_keys=True)
    root=template.bind()
    return path,template,template.extend(root,20,40),template.extend(root,80,90)


def test_still_live_variable_values_are_not_projected_by_full_state_key(tmp_path):
    path=tmp_path/'live_vars.csv'
    path.write_text('0,GetHeartPos,hx,hy\n0.0125,BlackScreen,1\n'
                    '0,HeartTeleport,320,304\n0.025,BoneV,$hx,100,20,0,0\n0.025,EndAttack\n')
    template=ParametricEnvironment(path,max_ticks=100,capture_state_keys=True)
    root=template.bind();a=template.extend(root,20,40);b=template.extend(root,80,90)
    assert a.wave.environment_state_keys[4]!=b.wave.environment_state_keys[4]


def test_capture_is_disabled_by_default(tmp_path):
    path=tmp_path/'default.csv';path.write_text('0.008333,GetHeartPos,x,y\n0.01,EndAttack\n')
    assert ParametricEnvironment(path,max_ticks=100).bind().wave.environment_state_keys==()

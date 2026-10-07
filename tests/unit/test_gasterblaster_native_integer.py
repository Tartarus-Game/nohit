"""Native int distinguishes literal/SET strings from arithmetic numbers."""
import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

from nohit.engine import compact_wave,resumable_wave
from nohit.engine.cspace import bake_cspace,collision_query,quad_intersects_box
from nohit.engine.discrete_operator import initial_state,sample_position,step_mask_into
from nohit.engine.initial_target_history import bind_initial_target_history
from nohit.engine.parametric_environment import ParametricEnvironment


def test_blaster_sprite_xy_setters_preserve_existing_zero_sign():
    entity=compact_wave._ActiveGasterBlaster(0,'-0.4','-0.4','-0.4','-0.4',0,0.5,0.25)
    # Native sprites are created at +0,+0. SetX/SetY do not assign when the
    # old/new values compare equal; instance-variable EndX/EndY do assign.
    assert not np.signbit(entity.x) and not np.signbit(entity.y)
    assert np.signbit(entity.end_x) and np.signbit(entity.end_y)
    entity.step(1/240)
    assert not np.signbit(entity.x) and not np.signbit(entity.y)


@pytest.mark.parametrize('backend',['reference','resumable'])
@pytest.mark.parametrize('source,value,expected',[
    ('literal','-10.4',-10.),('set','-10.4',-10.),('mul','-10.4',-11.),
    ('literal','-1e3',-1.),('set','-1e3',-1.),('mul','-1e3',-1000.),
    ('literal','-12.9tail',-12.),('set','nonnumeric',0.),
])
def test_all_six_integer_fields_preserve_loaded_type(tmp_path,monkeypatch,backend,source,value,expected):
    prefix='' if source=='literal' else f'0,{"SET" if source=="set" else "MUL"},v,{value}'+(',1' if source=='mul' else '')+'\n'
    argument=value if source=='literal' else '$v'
    path=tmp_path/'typed-blaster.csv'
    path.write_text(prefix+f'0,GasterBlaster,{",".join([argument]*6)},0.125,0.375\n2,EndAttack\n')
    original=compact_wave._ActiveGasterBlaster;captured=[]
    def create(*args):
        entity=original(*args);captured.append(vars(entity).copy());return entity
    monkeypatch.setattr(compact_wave,'_ActiveGasterBlaster',create)
    monkeypatch.setattr(resumable_wave,'_ActiveGasterBlaster',create)
    ParametricEnvironment(path,backend=backend,dt_schedule=[1/240],max_ticks=1).bind()
    assert len(captured)==1
    entity=captured[0]
    assert [entity[k] for k in ('size','x','y','end_x','end_y','end_ang')]==[expected]*6
    assert entity['timer']==0.125 and entity['blast_time']==0.375


@pytest.mark.parametrize('backend',['reference','resumable'])
def test_native_final_original_actions_first_collide_at_5950(tmp_path,backend):
    base=Path(__file__).resolve().parents[1]/'fixtures'/'native_final_negative_angle_failure'
    fixture=json.loads(base.with_suffix('.json').read_text(encoding='utf-8'))
    assert hashlib.sha256(base.with_suffix('.npz').read_bytes()).hexdigest()==fixture['npz_sha256']
    with np.load(base.with_suffix('.npz')) as saved:
        states=saved['native_states'];actions=saved['actions'];dt=saved['dt'];hp_kr=saved['hp_kr']
    path=tmp_path/'actual-final.csv';path.write_bytes(fixture['csv'].encode('utf-8'))
    assert hashlib.sha256(path.read_bytes()).hexdigest()==fixture['csv_sha256']
    assert np.all(hp_kr[:-1]==[92,0]) and hp_kr[-1].tolist()==[91,10]
    template=ParametricEnvironment(path,backend=backend,seed=fixture['seed'],
        initial_environment=fixture['initial_environment'],initial_arena=fixture['initial_arena'],
        dt_schedule=dt,max_ticks=len(dt))
    binding=bind_initial_target_history(template,fixture['initial_target_history'])
    state=initial_state(fixture['initial'],binding.wave.env_schedule[0]);spaces={};hits=[];direct_hits=[]
    for tick in range(len(states)):
        if binding.pending_target is not None and binding.pending_target['tick']==tick:
            x,y=state[:2] if tick==0 else sample_position(state,binding.wave.env_schedule[tick],binding.wave.platform_table[tick])
            while binding.pending_target is not None and binding.pending_target['tick']==tick:
                binding=template.extend(binding,float(x),float(y))
        wave=binding.wave
        if tick:step_mask_into(state,int(actions[tick-1]),wave.env_schedule[tick],wave.platform_table[tick],state)
        assert state.tobytes()==states[tick].tobytes(),tick
        if binding.identity not in spaces:spaces[binding.identity]=bake_cspace(wave,cell_size=8.)
        if collision_query(wave.geometry_white,wave.geometry_blue,tick,state,0.,spaces[binding.identity].payload):hits.append(tick)
        if any(quad_intersects_box(poly,state[0],state[1],2.,2.) for poly in wave.geometry_polygons[tick]):direct_hits.append(tick)
    assert hits==direct_hits==[fixture['first_collision_frame']]

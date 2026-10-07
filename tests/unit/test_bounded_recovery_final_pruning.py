"""The actual width-1000 Final loss, with all real local retained ancestors.

Fixture ticks 0..42 are source ticks 7600..7642. Only time-array indices are
rebased; state bytes, controls, environment rows and parent indices are exact.
Full-frame-zero acceptance is covered separately by scalar-verified searches.
"""
from pathlib import Path
from types import SimpleNamespace
import time

import numpy as np

from nohit.engine import bounded_frontier as module
from nohit.engine.cspace import bake_cspace, collision_query
from nohit.engine.discrete_operator import step_mask_into
from nohit.engine.exact_state_dedup import unique_state_indices
from nohit.engine.local_relation import _expand, _internal_layer_keys
from nohit.engine.control_quotient import control_classes


def test_actual_pruned_final_continuation_is_recovered_with_its_real_ancestry():
    path=Path(__file__).parents[1]/'fixtures'/'final_width_pruning.npz'
    with np.load(path,allow_pickle=False) as saved:
        data={name:saved[name] for name in saved.files}
    wave=SimpleNamespace(env_schedule=data['environment'],platform_table=data['platforms'],
        geometry_white=data['white'],geometry_blue=data['blue'],geometry_polygons=data['polygons'],
        origin=(239,226),dimensions=(165,165),termination_reason='endattack')
    space=bake_cspace(wave,cell_size=8.)
    masks=np.array([group[0] for group in control_classes(wave.env_schedule[1:2],range(16),
        next_environment=wave.env_schedule[2])],np.int64)
    following,parents,controls=_expand(data['states_0'],masks,0,1,wave.env_schedule,
        wave.platform_table,wave.geometry_white,wave.geometry_blue,space.payload)
    unique=unique_state_indices(following,wave.env_schedule[2])
    child=data['trajectory'][1]
    edge=np.flatnonzero((parents==103)&(controls==10))
    assert len(edge)==1 and following[edge[0]].tobytes()==child.tobytes()
    key=_internal_layer_keys(child[None,:],wave.env_schedule[2])[0]
    assert np.any(_internal_layer_keys(following[unique],wave.env_schedule[2])==key)
    assert not np.any(_internal_layer_keys(data['states_1'],wave.env_schedule[2])==key)

    result=module.BoundedFrontierResult(reached_tick=42)
    binding=SimpleNamespace(wave=wave,complete=True,pending_target=None,identity='captured',
        history=((1977,43,66.77500000055615,265.9999999999386),))
    result.bindings=[binding]
    for tick in range(43):
        states=data[f'states_{tick}']
        result.layers.append(module.FrontierLayer(tick,states,np.zeros(len(states),np.int64),
            data[f'parents_{tick}'],data[f'masks_{tick}']))
    # The original last retained layer has no next safe input at all.
    all_masks=np.arange(16,dtype=np.int64)
    dead_next=_expand(result.layers[-1].states,all_masks,42,1,wave.env_schedule,
        wave.platform_table,wave.geometry_white,wave.geometry_blue,space.payload)
    assert len(dead_next[0])==0
    result.stats=dict(recovery_attempts=0,recovery_macro_edges=0,recovery_count=0,
        recovery_discarded_states=0,recoveries=[])
    assert module._recover_frontier(result,tuple(all_masks),1000,np.random.default_rng(42),
        lambda bound:space,time.perf_counter()+10,256)
    assert result.reached_tick==43 and result.stats['recovery_count']==1
    assert result.stats['recoveries'][0]['start_tick']==0
    original_keys={row.tobytes() for row in data['states_0']}
    # Every returned macro retains a genuine captured parent and every actual
    # intermediate control/state; no survivor borrows a different history.
    for index in range(len(result.layers[-1].states)):
        actions,trace=result.witness(index)
        assert trace[0].tobytes() in original_keys
        state=trace[0].copy()
        for tick,mask in enumerate(actions,1):
            assert mask in all_masks
            step_mask_into(state,mask,wave.env_schedule[tick],wave.platform_table[tick],state)
            assert state.tobytes()==trace[tick].tobytes()
            assert not collision_query(wave.geometry_white,wave.geometry_blue,tick,state,0.,space.payload)
    assert np.all(result.layers[-1].states[:,5]==0)

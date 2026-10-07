"""Dispatch changes resource use while preserving the complete edge relation."""
from pathlib import Path
import hashlib
import json
import os
import subprocess
import sys

import numpy as np
import pytest
from numba import config, get_num_threads, set_num_threads

from nohit.engine.expansion_dispatch import expand_dispatch, expansion_workers, prepare_expansion
from nohit.engine.local_relation import _expand


FIXTURES = Path(__file__).resolve().parents[1] / 'fixtures'


def real_intro_batch():
    metadata = json.loads((FIXTURES / 'intro_expansion_9000.json').read_text(encoding='utf-8'))
    path = FIXTURES / 'intro_expansion_9000.npz'
    assert hashlib.sha256(path.read_bytes()).hexdigest() == metadata['sha256']
    with np.load(path, allow_pickle=False) as stored:
        arrays = {name: stored[name] for name in stored.files}
    return (arrays['states'], arrays['controls'], 0, metadata['hold'], arrays['env'], arrays['platforms'],
            arrays['white'], arrays['blue'],
            (arrays['cells'], arrays['polygons'], metadata['ox'], metadata['oy'], metadata['cell_size']))


@pytest.mark.parametrize('edges,expected', [(0,0),(9,0),(63,0),(64,1),(511,1),(512,2),(2047,2),(2048,None),(9000,None)])
def test_measured_policy_keeps_small_batches_serial_and_caps_workers(edges,expected):
    if expected is None:
        expected = 8 if os.environ.get('OMP_WAIT_POLICY','').upper() == 'PASSIVE' else 2
    assert expansion_workers(edges) == min(expected, config.NUMBA_NUM_THREADS)


@pytest.mark.parametrize('policy,expected', [(None,2),('ACTIVE',2),('PASSIVE',8),('passive',8)])
def test_startup_wait_policy_chooses_a_bounded_thread_team(policy,expected):
    environment = dict(os.environ)
    if policy is None:
        environment.pop('OMP_WAIT_POLICY',None)
    else:
        environment['OMP_WAIT_POLICY'] = policy
    output = subprocess.check_output([sys.executable,'-c',
        'from nohit.engine.expansion_dispatch import expansion_workers; print(expansion_workers(9000))'],
        env=environment,text=True)
    assert int(output.strip()) == min(expected,config.NUMBA_NUM_THREADS)


@pytest.mark.parametrize('edge_count', [-1, True, 1.5])
def test_invalid_edge_count_is_rejected(edge_count):
    with pytest.raises(ValueError, match='edge_count'):
        expansion_workers(edge_count)


@pytest.mark.parametrize('state_count', [0,1,8,81,225,1000])
def test_every_dispatch_size_preserves_real_edges_and_inputs(state_count):
    args = list(real_intro_batch())
    args[0] = args[0][:state_count]
    before = args[0].tobytes(), args[1].tobytes()
    expected = _expand(*args)
    previous = get_num_threads()
    actual = expand_dispatch(*args)
    for got, want in zip(actual, expected):
        assert got.dtype == want.dtype and got.shape == want.shape
        assert got.tobytes() == want.tobytes()
    if state_count == 1000:
        assert len(actual[0]) == 8550
    assert (args[0].tobytes(), args[1].tobytes()) == before
    assert get_num_threads() == previous


def test_preparation_advances_no_state_and_restores_thread_mask_and_environment():
    args = real_intro_batch()
    state_bytes = args[0].tobytes()
    environment = dict(os.environ)
    previous = get_num_threads()
    try:
        set_num_threads(min(3,config.NUMBA_NUM_THREADS))
        assert prepare_expansion(*args) is None
        assert get_num_threads() == min(3,config.NUMBA_NUM_THREADS)
        assert args[0].tobytes() == state_bytes
        assert dict(os.environ) == environment
    finally:
        set_num_threads(previous)

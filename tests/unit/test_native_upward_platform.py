"""Observed native upward-platform contact, independent of model parity."""
import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

from nohit.engine.native_backend import step_batch
from nohit.engine.source_oracle import scalar_module


ROOT = Path(__file__).resolve().parents[2]


def test_current_export_enables_both_vertical_platform_directions():
    data = json.loads((ROOT / 'c2-sans-fight/data.js').read_text(encoding='utf-8-sig'))
    def event(value, sid):
        if isinstance(value, list):
            if len(value) > 4 and value[0] == 0 and value[4] == sid:
                return value
            for child in value:
                found = event(child, sid)
                if found is not None:
                    return found
        elif isinstance(value, dict):
            for child in value.values():
                found = event(child, sid)
                if found is not None:
                    return found
    solid = event(data, 8364383427250982)
    branches = solid[7][1][7]
    assert [branch[4] for branch in branches] == [4274121673613992, 2332670214936478]
    assert [branch[5][0][9][1][1][1] for branch in branches] == [90, 270]
    # The upward bbox comparison is >= (5), not <= (3) in the old excerpt.
    assert branches[1][5][3][9][1] == [8, 5]
    carry = event(data, 6626973457028389)
    assert carry is not None and carry[5][3][9][1] == [8, 5]


@pytest.mark.parametrize('backend', ['scalar', 'native'])
def test_upward_slam_replays_the_observed_native_platform_contact(backend):
    fixture = json.loads((ROOT / 'tests/fixtures/native_csv_upward_platform_contact.json').read_text())
    assert hashlib.sha256((ROOT / 'c2-sans-fight/data.js').read_bytes()).hexdigest() == fixture['source_data_sha256']
    before = np.array(fixture['before'], dtype=np.float64)
    environment = np.array(fixture['environment'], dtype=np.float64)
    platforms = np.array(fixture['platforms'], dtype=np.float64)
    if backend == 'native':
        actual = step_batch(before[None], np.array([fixture['input']], dtype=np.int64), environment, platforms)[0]
    else:
        actual = np.empty(11)
        scalar_module('discrete_operator').step_mask_into(before, fixture['input'], environment, platforms, actual)
    np.testing.assert_array_equal(actual, fixture['after'])

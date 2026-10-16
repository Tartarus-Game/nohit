"""Canonical source compilation preserves current tensors and honest boundaries."""
import numpy as np
import pytest

from nohit.engine.compact_wave import CANONICAL_ATTACK_NAMES, ROOT, compile_wave


@pytest.mark.parametrize('name', sorted(CANONICAL_ATTACK_NAMES-{'sans_realhell_extreme'}))
def test_source_world_arrays_are_finite_and_keep_unresolved_observations(name):
    wave = compile_wave(ROOT/'c2-sans-fight'/(name+'.csv'), allow_partial=True)
    count = len(wave.env_schedule)
    assert count > 0 and wave.env_schedule.shape == (count,22)
    assert wave.platform_table.shape[0] == count and wave.platform_table.shape[2] == 9
    assert wave.num_platforms.shape == (count,)
    assert np.isfinite(wave.env_schedule).all() and np.isfinite(wave.platform_table).all()
    assert np.all(wave.dt > 0.)
    for geometry in (wave.geometry_white,wave.geometry_blue,wave.geometry_polygons):
        assert geometry.shape[0] == count and not np.isinf(geometry).any()
    if wave.pending_target is not None:
        assert not wave.complete and wave.termination_reason == 'pending_target'
    if wave.complete:
        assert wave.termination_reason == 'endattack'

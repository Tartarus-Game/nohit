import pytest

from nohit.dashboard.acceptance_clock import validate_compensated_clock


def trace():
    return dict(clock='original-runtime-realtime-catchup-240hz',
                compensation=dict(error=None, droppedSteps=0),
                trace=dict(runs=[dict(rows=[dict(tick=i, dt=1/240) for i in range(8)])]))


def test_compensated_clock_accepts_contiguous_fixed_steps():
    validate_compensated_clock(trace())


@pytest.mark.parametrize('dt', [0, 1/60, float('nan'), float('inf'), None])
def test_compensated_clock_rejects_changed_dt(dt):
    data = trace()
    data['trace']['runs'][0]['rows'][3]['dt'] = dt
    with pytest.raises(ValueError, match='timestep'):
        validate_compensated_clock(data)


@pytest.mark.parametrize('tick', [2, 4])
def test_compensated_clock_rejects_skips_and_duplicates(tick):
    data = trace()
    data['trace']['runs'][0]['rows'][3]['tick'] = tick
    with pytest.raises(ValueError, match='skipped or duplicated'):
        validate_compensated_clock(data)


@pytest.mark.parametrize('stats', [None, {}, dict(error='failed', droppedSteps=0), dict(error=None, droppedSteps=1)])
def test_compensated_clock_rejects_missing_or_failed_compensation(stats):
    data = trace()
    data['compensation'] = stats
    with pytest.raises(ValueError, match='Compensation'):
        validate_compensated_clock(data)

"""Public CSV entry points admit native default target destination names."""
import pytest

from nohit.dashboard.csv_api import solve_csv_request
from nohit.engine.canonical_solver import model_issues
from nohit.engine.csv_solver import solve_csv


INITIAL = [320., 304., 0., 0., 0., 0., 0., 1., 750., 0., 0.]
HISTORY = [[0, 1, 320., 304.]]
CALLS = ['GetHeartPos', 'GetHeartPos,x', 'GetHeartPos,,y',
         'GetHeartPos,x,', 'GetHeartPos,,']


def run_entry(tmp_path, entry, call, history=HISTORY):
    text = '0,' + call + '\n0.05,EndAttack\n'
    settings = dict(dt_schedule=[1/30]*4, max_ticks=4, width=1,
                    initial_target_history=history)
    if entry == 'api':
        return solve_csv_request(dict(custom_csv=text, initial=INITIAL,
                                      request_id='short-target-admission', **settings))
    path = tmp_path/'short-target.csv'
    path.write_text(text, encoding='utf-8')
    return solve_csv(path, INITIAL, **settings)


@pytest.mark.parametrize('entry', ['solver', 'api'])
@pytest.mark.parametrize('call', CALLS)
def test_native_default_target_destinations_reach_complete_verified_public_result(tmp_path, entry, call):
    result = run_entry(tmp_path, entry, call)
    assert result['status'] == 'candidate_found', result.get('issues', result.get('reason'))
    assert result['verified'] is True
    assert result['target_history'] == HISTORY
    assert result['completion']['kind'] == 'endattack'
    assert result['completion']['model_verified'] is True
    assert result['original_replay_passed'] is False
    assert result['trajectory'][0] == INITIAL
    assert len(result['actions']) + 1 == len(result['trajectory']) == len(result['dt_sequence'])
    assert len(result['actions']) == len(result['confirm_sequence'])
    if entry == 'api':
        assert result['provenance']['request_id'] == 'short-target-admission'
        assert result['visualization']['frame_count'] == len(result['trajectory'])


@pytest.mark.parametrize('entry', ['solver', 'api'])
def test_admission_does_not_invent_an_omitted_observed_target(tmp_path, entry):
    with pytest.raises(ValueError, match='omits an observed tick-zero GetHeartPos'):
        run_entry(tmp_path, entry, 'GetHeartPos', history=[])


@pytest.mark.parametrize('call', CALLS)
def test_short_target_still_requires_player_history_model(tmp_path, call):
    path = tmp_path/'short-target.csv'
    path.write_text('0,' + call + '\n0.05,EndAttack\n', encoding='utf-8')
    assert model_issues(path, allow_player_history=True) == []
    issues = model_issues(path, allow_player_history=False)
    assert [issue['reason'] for issue in issues] == ['environment_depends_on_player_history']

"""Production TAS scheduling contracts without running a second solver/server."""
import json
from urllib.parse import urlencode

import pytest

from nohit.dashboard.server import DashboardHandler
from nohit.engine.canonical_solver import ranking_weights


class ResponseCapture:
    handle_get_tas = DashboardHandler.handle_get_tas

    def send_json_response(self, payload):
        self.status = 200
        self.payload = payload

    def send_json_error(self, message, status):
        self.status = int(status)
        self.payload = {"error": message}


@pytest.fixture
def schedule(monkeypatch):
    """Exercise the real request handler with deterministic solver outcomes."""
    import nohit.engine.canonical_solver as canonical

    def request(*, outcomes=(), frames=(), **parameters):
        calls = []

        def solve(path, initial, **options):
            index = len(calls)
            calls.append(dict(path=path, initial=initial, **options))
            status = outcomes[index] if index < len(outcomes) else "resource_limit"
            return dict(status=status, planner="canonical-dag-dp", actions=[0] if status == "candidate_found" else [],
                        control_ticks=options.get('decision_ticks',4),control_hz=240//options.get('decision_ticks',4),physics_hz=240,
                        trajectory=[], ranking_weights=ranking_weights(options.get("weights")),
                        lookahead_policy=options.get("lookahead_policy", "navigation"),
                        allow_cancel=options.get("allow_cancel", True),
                        control_alphabet_size=32 if options.get("allow_cancel", True) else 16,
                        lookahead=options["lookahead"], frame=frames[index] if index < len(frames) else index,
                        expansions=min(100, options["max_nodes"]), search_limited=status == "resource_limit",
                        deadlock_proven=False, optimality_proven=False, complete_original_input_timing=False,
                        weights_affect_safety=False)

        monkeypatch.setattr(canonical, "solve_attack", solve)
        query = dict(wave="sans_platforms4.csv", initial=json.dumps([175, 327, 0, 0, 0]), max_nodes=500000)
        query.update(parameters)
        handler = ResponseCapture()
        handler.handle_get_tas(urlencode(query))
        assert handler.status == 200, handler.payload
        return handler.payload, calls

    return request


@pytest.mark.parametrize("budget", [1, 50000, 50001, 100001, 249999, 250000, 250001, 500000, 2000000])
def test_all_limited_attempts_conserve_the_requested_total_budget(schedule, budget):
    result, calls = schedule(max_nodes=budget)
    assert sum(call["max_nodes"] for call in calls) == budget
    assert all(call["max_nodes"] > 0 for call in calls)
    assert result["requested_max_nodes"] == budget
    assert sum(attempt["max_nodes"] for attempt in result["evaluation_attempts"]) == budget
    assert result["total_expansions"] == sum(attempt["expansions"] for attempt in result["evaluation_attempts"])
    assert result["total_expansions"] <= budget
    assert result["automatic_order_changed"] == (len(calls) > 1)
    assert result["search_status"] == "resource_limit" and result["search_limited"]
    assert not result["candidate_found"] and not result["deadlock_proven"]
    assert result["is_deadlock"] is None and not result["complete_original_input_timing"]


def test_default_profiles_include_coast_then_subset_and_retry_the_furthest_full_profile(schedule):
    result, calls = schedule(frames=[10, 5, 30, 100, 80, 999, 110])
    assert [(call.get("lookahead_policy", "navigation"), call["lookahead"]) for call in calls] == [
        ("navigation", 60), ("navigation", 60), ("coast", 60), ("coast", 120), ("coast", 240),
        ("navigation", 60), ("coast", 120)]
    assert [call["max_nodes"] for call in calls] == [50000] * 5 + [200000, 50000]
    assert [call.get("allow_cancel", True) for call in calls] == [True] * 5 + [False, True]
    assert calls[-1]["weights"] == calls[3]["weights"]
    assert result["evaluation_attempts"][-1]["reached_frame"] == 110
    assert result["search_status"] == "resource_limit" and not result["deadlock_proven"]


@pytest.mark.parametrize("budget", [250001, 449999, 450000, 450001, 500000])
def test_exhausted_subset_is_unknown_for_the_full_graph_and_resumes_full_graph_when_funded(schedule, budget):
    result, calls = schedule(max_nodes=budget, outcomes=["resource_limit"] * 5 + ["exhausted_in_declared_model"],
                             frames=[10, 5, 30, 100, 80, 999, 110])
    assert len(calls) == (6 if budget <= 450000 else 7)
    assert calls[5]["allow_cancel"] is False
    assert result["evaluation_attempts"][5]["status"] == "exhausted_in_declared_model"
    assert result["evaluation_attempts"][5]["allow_cancel"] is False
    assert sum(call["max_nodes"] for call in calls) == budget
    assert result["search_status"] == "resource_limit" and result["search_limited"]
    assert not result["candidate_found"] and not result["deadlock_proven"] and result["is_deadlock"] is None
    if budget > 450000:
        assert calls[-1].get("allow_cancel", True) is True
        assert calls[-1]["lookahead_policy"] == "coast" and calls[-1]["lookahead"] == 120
    else:
        assert result["complete_in_original_game"] is False


def test_success_in_the_subset_is_a_valid_witness_and_stops_further_search(schedule):
    result, calls = schedule(outcomes=["resource_limit"] * 5 + ["candidate_found"])
    assert len(calls) == 6 and sum(call["max_nodes"] for call in calls) == 450000
    assert result["candidate_found"] and result["control_alphabet_size"] == 16
    assert calls[-1]["allow_cancel"] is False


def test_single_mode_domain_is_never_expanded_to_cancel_controls(schedule):
    result, calls = schedule(allow_cancel=0, max_nodes=500000)
    assert len(calls) == 6
    assert all(call["allow_cancel"] is False for call in calls)
    assert all(attempt["allow_cancel"] is False for attempt in result["evaluation_attempts"])
    assert sum(call["max_nodes"] for call in calls) == 500000


@pytest.mark.parametrize("horizon", [120, 240])
def test_matching_coast_horizons_are_not_repeated_in_the_short_profile_round(schedule, horizon):
    _, calls = schedule(max_nodes=200000, lookahead=horizon)
    short_coast = [(call["lookahead_policy"], call["lookahead"]) for call in calls
                   if call.get("lookahead_policy") == "coast"]
    assert set(short_coast) == {("coast", 120), ("coast", 240)}
    assert len(short_coast) == len(set(short_coast))


@pytest.mark.parametrize("weights", [dict.fromkeys(("clearance", "lookahead", "center", "switches"), 0),
                                    {"center": 9, "switches": 3}, {}])
def test_explicit_weights_pin_one_attempt_without_overrides(schedule, weights):
    result, calls = schedule(weights=json.dumps(weights), max_nodes=500000)
    assert len(calls) == 1 and calls[0]["weights"] == weights
    assert calls[0]["max_nodes"] == 500000
    assert result["ranking_weights"] == ranking_weights(weights)
    assert not result["automatic_order_changed"] and not result["weights_affect_safety"]


def test_explicit_policy_keeps_its_horizon_and_actual_boundary_inputs(schedule):
    environment = [113, 231, 548, 391, 1, 1, 0, 1 / 240, 750, 0, 0, 0, 0, 0,
                   113, 231, 548, 391, 113, 231, 548, 391]
    clock = 72216.66666665919
    result, calls = schedule(lookahead_policy="coast", lookahead=120, allow_cancel=0, seed=731,
                             initial_environment=json.dumps(environment), clock_start_ms=clock)
    assert len(calls) == 1
    call = calls[0]
    assert (call["lookahead_policy"], call["lookahead"], call["allow_cancel"]) == ("coast", 120, False)
    assert call["initial_environment"] == environment and call["clock_start_ms"] == clock and call["seed"] == 731
    assert not result["automatic_order_changed"]


@pytest.mark.parametrize("terminal", ["candidate_found", "exhausted_in_declared_model", "initial_state_required"])
def test_profile_round_stops_on_any_non_budget_result(schedule, terminal):
    result, calls = schedule(outcomes=["resource_limit", "resource_limit", terminal])
    assert len(calls) == 3 and sum(call["max_nodes"] for call in calls) == 150000
    assert result["search_status"] == terminal
    assert result["candidate_found"] == (terminal == "candidate_found")
    assert not result["deadlock_proven"] and result["is_deadlock"] is None


def test_successful_first_attempt_does_not_spend_the_rest_of_the_budget(schedule):
    result, calls = schedule(outcomes=["candidate_found"])
    assert result["candidate_found"] and len(calls) == 1 and calls[0]["max_nodes"] == 50000
    assert not result["automatic_order_changed"]


def test_physical_tick_control_domain_reaches_solver_and_response(schedule):
    result,calls=schedule(decision_ticks=1,outcomes=['candidate_found'])
    assert calls[0]['decision_ticks']==1
    assert result['control_ticks']==1 and result['control_hz']==240 and result['fps']==240


def test_long_eof_timeline_contract_reaches_the_same_solver(schedule):
    _,calls=schedule(max_ticks=120000,termination_policy='eof_hazards_drained',outcomes=['candidate_found'])
    assert calls[0]['max_ticks']==120000
    assert calls[0]['termination_policy']=='eof_hazards_drained'

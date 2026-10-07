"""Fresh EOF solver -> real API formatter -> production TAS runner, no native game."""
import json
from pathlib import Path
import shutil
import subprocess
from urllib.parse import urlencode
import pytest
from nohit.dashboard import server
from nohit.engine.execution_schedule import execution_schedule


@pytest.mark.parametrize('hold',[1,4])
def test_public_eof_response_and_runner_consume_every_tick(tmp_path,monkeypatch,hold):
    path=tmp_path/'sans_eof.csv'
    path.write_text('0,HeartMode,1\n0.02,CombatZoneSpeed,480\n')
    monkeypatch.setattr(server,'C2_REPO_DIR',tmp_path)
    handler=object.__new__(server.DashboardHandler)
    responses=[]
    handler.send_json_response=responses.append
    handler.send_json_error=lambda *error:pytest.fail(str(error))
    query=urlencode(dict(wave=path.name,seed=42,
        initial=json.dumps([320,304,0,0,0,0,1,1,750,0,0]),
        clock_start_ms=81808.33333333702,decision_ticks=hold,
        termination_policy='eof_hazards_drained',max_ticks=1000,
        weights=json.dumps(dict(clearance=0,lookahead=0,center=0,switches=0))))
    handler.handle_get_tas(query)
    plan=responses[0]
    assert plan['candidate_found'] and plan['execution_includes_terminal_tail']
    assert plan['control_ticks']==1 and plan['control_hz']==plan['physics_hz']==plan['fps']==240
    assert plan['actions']==plan['action_sequence']
    assert plan['solver_control_ticks']==hold
    tail=plan['terminal_tail'];boundary=tail['start_tick']
    physical=[a for a in plan['solver_actions'] for _ in range(hold)][:boundary]+tail['actions']
    assert physical==plan['actions']
    node=shutil.which('node')
    if node is None:pytest.skip('Node unavailable for production runner integration')
    script=Path(__file__).resolve().parents[2]/'tools/tas_execution_probe.mjs'
    run=subprocess.run([node,str(script)],input=json.dumps(plan),text=True,capture_output=True,check=True)
    evidence=json.loads(run.stdout)
    assert evidence['consumed']==physical+[0]


@pytest.mark.parametrize('boundary',[4,5,6,7,8])
def test_partial_distinct_action_blocks_reach_runtime_without_duplicate_tail(boundary):
    hold=4;actions=[2,4][:((boundary+3)//4)];carry=(-boundary)%hold
    bridge=[actions[-1]]*carry+[1,8,0]
    result=dict(status='candidate_found',actions=actions,control_ticks=hold,
        terminal_tail=dict(status='proven',start_tick=boundary,control_ticks=1,
            carry_ticks=carry,actions=bridge,states=[[]]*(len(bridge)+1),dt_sequence=[1/240]*len(bridge)))
    execution=execution_schedule(result)
    plan=dict(planner='canonical-dag-dp',candidate_found=True,physics_hz=240,
        control_hz=240,control_ticks=1,action_sequence=execution['actions'])
    node=shutil.which('node')
    if node is None:pytest.skip('Node unavailable for production runner integration')
    script=Path(__file__).resolve().parents[2]/'tools/tas_execution_probe.mjs'
    run=subprocess.run([node,str(script)],input=json.dumps(plan),text=True,capture_output=True,check=True)
    consumed=json.loads(run.stdout)['consumed']
    assert consumed==[a for a in actions for _ in range(hold)]+[1,8,0,0]

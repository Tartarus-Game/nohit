import pytest
from nohit.engine.execution_schedule import execution_schedule


@pytest.mark.parametrize('boundary',[4,5,6,7,8])
def test_tail_carry_is_not_executed_twice(boundary):
    hold=4;actions=[2]*((boundary+3)//4);carry=(-boundary)%4
    bridge=[2]*carry+[0]
    result=dict(status='candidate_found',actions=actions,control_ticks=hold,
        terminal_tail=dict(status='proven',start_tick=boundary,control_ticks=1,
            carry_ticks=carry,actions=bridge,states=[[]]*(len(bridge)+1),dt_sequence=[1/240]*len(bridge)))
    plan=execution_schedule(result)
    assert plan['actions']==[2]*(boundary+carry)+[0]
    assert plan['control_ticks']==1


def test_unproved_tail_is_not_installed():
    with pytest.raises(ValueError,match='unproved'):
        execution_schedule(dict(status='candidate_found',actions=[0],terminal_tail={'status':'unknown'}))

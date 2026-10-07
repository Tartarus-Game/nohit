"""Native TLLoadLine snapshots every $ argument before delayed execution."""
import csv
from pathlib import Path
import pytest
from nohit.engine.compact_wave import TimelineVM


def test_loaded_arguments_survive_later_variable_changes():
    vm=TimelineVM()
    vm.vars.update(delay=.1,destination=17.,value=23.)
    loaded=vm.load_line(('$delay',None,'SET','set',['$destination','$value']))
    vm.vars.update(delay=.2,destination=99.,value=100.)
    assert loaded==(.1,'set',(17.,23.))


def test_dynamic_getheartpos_names_are_resolved_before_either_assignment():
    vm=TimelineVM(heart_samples={(0,2):(123.,456.)})
    vm.run([['0','SET','HeartY','17'],['0','GetHeartPos','HeartY','$HeartY'],['0','EndAttack']])
    assert vm.vars['HeartY']==123.
    assert vm.vars['17']==456.
    assert '$HeartY' not in vm.vars and '123' not in vm.vars


def test_bare_names_and_loaded_dollar_strings_are_not_recursively_resolved():
    vm=TimelineVM()
    vm.run([['0','SET','number','3'],['0','SET','literal','number'],
            ['0','SET','copy','$literal'],['0','EndAttack']])
    assert vm.vars['number']=='3'  # SET preserves literal string type.
    assert vm.vars['literal']=='number' and vm.vars['copy']=='number'
    vm.vars['a']='$number'
    assert vm.load_line(('0',0.,'SET','set',['b','$a']))[2]==('b','$number')
    assert vm.eval_arg('$number')=='$number'


def test_delay_uses_loaded_snapshot_not_execution_time_dictionary():
    class ExternalMutationAfterLoad(TimelineVM):
        def load_line(self,row):
            result=super().load_line(row)
            if row[0]=='$delay':
                self.vars.update(delay=0.,value=999.)
            return result
    vm=ExternalMutationAfterLoad()
    wave=vm.run([['0','SET','delay','0.1'],['0','SET','value','17'],
                 ['$delay','SET','result','$value'],['0','EndAttack']])
    assert vm.vars['result']=='17'
    assert wave['ticks']>=25


@pytest.mark.parametrize('source_line',[844,862,880,898,916,934])
def test_realhell_dynamic_destination_rows_preserve_named_heart_y(source_line):
    root=Path(__file__).resolve().parents[2]
    rows=list(csv.reader((root/'Real HELL 困难模式(1).csv').read_text(encoding='utf-8-sig').splitlines()))
    row=rows[source_line-1]
    assert row[1:4]==['GetHeartPos','HeartX','$HeartY']
    vm=TimelineVM(heart_samples={(0,1):(321.5,303.25)})
    vm.vars['HeartY']=297.5
    vm.run([row,['0','EndAttack']])
    assert vm.vars['HeartX']==321.5
    assert vm.vars['HeartY']==297.5
    assert vm.vars['297.5']==303.25
    assert '$HeartY' not in vm.vars


def test_taken_self_jump_reloads_arguments():
    vm=TimelineVM(max_ticks=10)
    wave=vm.run([['0','SET','n','3'],['0','SUB','n','$n','1'],
                 ['0','JMPNZ','2','$n'],['0','EndAttack']])
    assert wave['complete'] and vm.vars['n']==0.

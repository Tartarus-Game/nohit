"""Source admission checks; no search kernels or JIT preparation."""
import math
from .timeline_csv import read_timeline_rows
from .native_function_dispatch import audited_no_action_command

STATIC_COMMANDS={'combatzoneresize','heartteleport','heartmode','tlpause','endattack','bonev','boneh','bonevrepeat','bonehrepeat'}
PURE_COMMANDS={'set','add','sub','mul','rnd','jmpe','jmpne','jmpnl','jmprel','jmpabs'}
STATIC_COMMANDS |= {'combatzoneresizeinstant','combatzonespeed','heartmaxfallspeed',
    'sansslamdamage','sansslam','platform','platformrepeat','bonestab','sinebones','gasterblaster','tlresume','blackscreen'}
PURE_COMMANDS |= {'div','mod','floor','sin','cos','deg','rad','angle','jmpz','jmpnz','jmpl','jmpg','jmpng'}
COSMETIC_COMMANDS={'sansanimation','sanshead','sansbody','sanstext','sound','music','sanslegs','sansface','wait'}
COSMETIC_COMMANDS |= {'sanssweat','sansrepeat','sansendrepeat','sanstorso','sansx'}
ARITY={'combatzoneresize':4,'heartteleport':2,'heartmode':1,'bonev':5,'boneh':5,
       'bonevrepeat':7,'bonehrepeat':7,'set':2,'add':3,'sub':3,'mul':3,'rnd':2,
       'jmpe':3,'jmpne':3,'jmpnl':3,'jmprel':1,'jmpabs':1}
ARITY.update(combatzoneresizeinstant=4,combatzonespeed=1,heartmaxfallspeed=1,
    sansslamdamage=1,sansslam=1,platform=5,platformrepeat=7,bonestab=4,sinebones=4,gasterblaster=8,blackscreen=1)
REQUIRED_TEXT_ARGUMENTS={command:(0,) for command in (
    'set','add','sub','mul','div','mod','floor','sin','cos','deg','rad','angle','rnd')}
# GetHeartPos destinations may be absent (native numeric 0 -> key "0") or
# explicit empty strings (key ""). The shared nine-slot dispatcher preserves
# that distinction; target-history admission below remains independently gated.
def model_issues(path, allow_player_history=False,termination_policy='endattack',allow_scripted_healing=False,allow_scripted_damage=False):
    return timeline_issues(read_timeline_rows(path), allow_player_history=allow_player_history,
        termination_policy=termination_policy, allow_scripted_healing=allow_scripted_healing,
        allow_scripted_damage=allow_scripted_damage)


def native_source_diagnostics(rows, **settings):
    """Separate blocking model gaps from source-bound native empty calls."""
    issues=[];warnings=[]
    for issue in timeline_issues(rows, **settings):
        if (issue.get('reason')=='mechanism_not_validated' and
                audited_no_action_command(issue.get('command','').strip())):
            warnings.append(dict(issue,reason='native_function_has_no_handler'))
        else:
            issues.append(issue)
    return dict(issues=issues,warnings=warnings)


def timeline_issues(rows, allow_player_history=False,termination_policy='endattack',allow_scripted_healing=False,allow_scripted_damage=False):
    """Check already captured native rows without reading a mutable source again."""
    if termination_policy not in ('endattack','eof_hazards_drained'):
        raise ValueError('invalid termination policy')
    issues=[]
    elapsed=0.
    preparation_finished=False
    has_end=False
    for number,row in enumerate(rows,1):
        if len(row)<2: continue
        cmd=row[1].strip().lower()
        if not cmd: continue
        healing=False
        if cmd=='damageplayer' and (allow_scripted_healing or allow_scripted_damage):
            # An explicit opt-in models only the physical projection of literal
            # healing. HP/KR and native health callbacks still require replay.
            # Positive literals require a separate explicit physical-projection opt-in.
            # Missing, dynamic and nonfinite effects are always rejected.
            try:
                amount=float(row[2])
                healing=math.isfinite(amount) and (amount<0 or allow_scripted_damage)
            except (IndexError,ValueError):
                pass
        if cmd not in STATIC_COMMANDS|PURE_COMMANDS|COSMETIC_COMMANDS and not cmd.startswith(':') and not (cmd=='getheartpos' and allow_player_history):
            if not healing:
                issues.append({'line':number,'command':row[1],'reason':
                    'environment_depends_on_player_history' if cmd=='getheartpos' else 'mechanism_not_validated'})
        try:
            delay=float(row[0] or 0)
            if not math.isfinite(delay) or delay<0: raise ValueError()
            elapsed+=delay
        except ValueError:
            if not row[0].strip().startswith('$'):
                issues.append({'line':number,'reason':'invalid_or_dynamic_timeline'})
        args=[x.strip() for x in row[2:]]
        # Construct's CSV/function numeric conversion maps absent/empty cells
        # to zero. Keep the current arithmetic-destination admission restriction;
        # GetHeartPos accepts native default/empty keys through shared dispatch.
        if any(index>=len(args) or not args[index] for index in REQUIRED_TEXT_ARGUMENTS.get(cmd,())):
            issues.append({'line':number,'reason':'missing_arguments'})
        for arg in args:
            try:
                if not math.isfinite(float(arg)):
                    issues.append({'line':number,'reason':'nonfinite_argument'})
            except ValueError: pass # variable references and labels are interpreted by TimelineVM
        if cmd=='heartmode':
            try:
                mode=int(float(args[0] or '0')) if args else 0
                if mode not in (0,1):raise ValueError()
            except (ValueError,OverflowError):
                issues.append({'line':number,'reason':'unvalidated_heart_mode'})
        if cmd=='tlpause':
            if preparation_finished: issues.append({'line':number,'reason':'mid_attack_pause'})
            preparation_finished=True
        has_end |= cmd=='endattack'
    if not has_end and termination_policy=='endattack': issues.append({'reason':'missing_endattack'})
    return issues

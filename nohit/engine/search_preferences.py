"""Request-local ranking preferences. They never change physics or safety."""
from contextvars import ContextVar

PREFERENCES = ContextVar('nohit_search_preferences', default=None)


def preferences(objective='balanced', operation_weight=None, held_weight=None, diagnostic_routes=32):
    if objective not in ('balanced', 'fewest_operations', 'human_friendly'):
        raise ValueError('objective must be balanced, fewest_operations or human_friendly')
    defaults = (12, 1) if objective == 'balanced' else (1000, 0)
    weights = tuple(default if value is None else value for value, default in
                    zip((operation_weight, held_weight), defaults))
    if any(type(value) is not int or not 0 <= value <= 1000 for value in weights) or not any(weights):
        raise ValueError('operation_weight and held_weight must be integers in [0,1000], not both zero')
    if type(diagnostic_routes) is not int or not 1 <= diagnostic_routes <= 256:
        raise ValueError('diagnostic_routes must be an integer in [1,256]')
    return dict(objective=objective, operation_weight=weights[0], held_weight=weights[1],
                diagnostic_routes=diagnostic_routes)


def confirm_for_state(state, tick, initial_confirm=False):
    if tick==0:return initial_confirm
    if current()['objective']!='human_friendly':return tick%2==0
    dialogue=state.dialogue
    if not dialogue or not dialogue.alive or not dialogue.interactive or tick%2 or state.dialogue_last_input[0]:return False
    complete=dialogue.current_char==dialogue.length
    schedule=state.program.dt_schedule
    if not complete and schedule is not None and tick<len(schedule):
        from .dialogue_operator import CHAR_PERIOD
        complete=(dialogue.current_char+1==dialogue.length and dialogue.t+schedule[tick]>=CHAR_PERIOD)
    # Keep the existing confirmation clock slots while omitting every unused
    # press. The RPGText phase may finish its last character in this tick.
    return complete


def current():
    return PREFERENCES.get() or preferences()


def input_cost(actions, previous=0, config=None):
    config = config or current()
    word = [int(mask) for mask in actions]
    churn = sum(mask != (word[i-1] if i else previous) for i, mask in enumerate(word))
    held = sum(mask != 0 for mask in word)
    total = churn * config['operation_weight'] + held * config['held_weight']
    return dict(frames=len(word), churn=churn, held_frames=held,
                churn_weight=config['operation_weight'], held_weight=config['held_weight'],
                total=total, reward=-total, objective=config['objective'],
                scope='arrow_mask_changes_and_held_frames', optimality_proven=False)

from types import SimpleNamespace
import numpy as np
from nohit.engine.parametric_environment import ParametricEnvironment
from nohit.engine.initial_target_history import bind_initial_target_history
from nohit.engine.source_oracle import scalar_module
from nohit.engine.csv_completion import wave_terminal,controlled_terminal
def certify_previous(path, initial, settings, actions, expected, confirms, initial_confirm, previous_confirm, initial_target_history, has_dialogue):
    """Original source operator replay with exact suspension-time observations."""
    player = scalar_module('discrete_operator')
    joint = scalar_module('joint_transition')
    template = ParametricEnvironment(path, backend='resumable' if has_dialogue else 'reference', **settings)
    binding = bind_initial_target_history(template, initial_target_history)
    state = player.initial_state(initial, binding.wave.env_schedule[0])
    controlled = None
    base = None
    first = None
    history = []
    primed = False
    for tick in range(len(actions) + 1):
        if controlled is None:
            while binding.pending_target is not None and binding.pending_target['tick'] == tick:
                frame = binding.wave
                xy = state[:2] if tick == 0 else player.sample_position(state, frame.env_schedule[tick], frame.platform_table[tick])
                binding = template.extend(binding, float(xy[0]), float(xy[1]))
            if binding.wave.termination_reason == 'dialogue_boundary' and binding.resume_state.request['tick'] == tick:
                base = binding
                history = list(binding.history)
                first = max(1, tick)
                prior_confirm = previous_confirm if tick == 0 else initial_confirm if tick == 1 else confirms[tick - 2]
                controlled = template.begin_controlled(binding, previous_input_code=int(state[4]) | (32 if prior_confirm else 0))
                if tick == 0:
                    primed = True
                    controlled = template.step_controlled(controlled, int(state[4]) | (32 if initial_confirm else 0))
                    if controlled.frame is None or controlled.status not in ('ready', 'terminal'):
                        return None
            if controlled is None:
                if tick >= len(binding.wave.env_schedule):
                    return None
                wave = binding.wave
                frame = SimpleNamespace(env=wave.env_schedule[tick], platforms=wave.platform_table[tick], white=wave.geometry_white[tick], blue=wave.geometry_blue[tick], polygons=wave.geometry_polygons[tick])
                if tick:
                    player.step_mask_into(state, actions[tick - 1], frame.env, frame.platforms, state)
                if joint.frame_collision(frame, state):
                    return None
        if controlled is not None:
            if tick:
                edge = joint.step_joint(template, joint.JointState(tuple(state), controlled), int(actions[tick - 1]) | (32 if confirms[tick - 1] else 0))
                if edge.state is None:
                    return None
                controlled = edge.state.environment
                state = np.asarray(edge.state.player)
            elif joint.frame_collision(controlled.frame, state):
                return None
            if controlled.frame.tick != tick:
                return None
            rows = controlled.frame.target_history
            if tick == max(0, first - 1) and primed:
                rows = rows[len([r for r in history if r[0] == tick]):]
            elif tick == first:
                rows = rows[len([r for r in history if r[0] == tick]):]
            history.extend(rows)
        if state.tobytes() != expected[tick].tobytes():
            return None
    if controlled is not None:
        if controlled.status != 'terminal' or controlled.reason != 'endattack':
            return None
        return (base, tuple(history), controlled_terminal(controlled, template), controlled.identity, first - 1, primed)
    if not binding.complete or len(binding.wave.env_schedule) != len(actions) + 1:
        return None
    return (binding, binding.history, wave_terminal(binding.wave), None, None, False)

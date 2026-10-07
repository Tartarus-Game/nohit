"""Bind already observed frame-zero reads without inventing future targets."""
import math


def normalize_initial_target_history(history):
    """None retains offline sampling; an explicit list must be complete.

    Coordinates are caller-observed boundary facts, not assertions about the
    post-frame player position. Source line/order and teleport consistency are
    checked again by ParametricEnvironment.bind on both replay backends.
    """
    if history is None:
        return None
    if not isinstance(history, (list, tuple)):
        raise ValueError('initial_target_history must be a sequence of tick-zero observations')
    normalized = []
    for row in history:
        if not isinstance(row, (list, tuple)) or len(row) != 4:
            raise ValueError('initial_target_history rows must be [tick,line,x,y]')
        tick, line, x, y = row
        if type(tick) is not int or tick != 0 or type(line) is not int or line < 1:
            raise ValueError('initial_target_history accepts only tick 0 and integer source lines')
        if any(type(value) not in (int, float) or not math.isfinite(value) for value in (x, y)):
            raise ValueError('initial_target_history coordinates must be finite numbers')
        normalized.append((0, line, float(x), float(y)))
    return tuple(normalized)


def bind_initial_target_history(template, history):
    """Materialize the exact observed prefix, rejecting omitted tick-zero reads."""
    history = normalize_initial_target_history(history)
    binding = template.bind(() if history is None else history)
    if history is not None and binding.pending_target is not None and binding.pending_target['tick'] == 0:
        raise ValueError('initial_target_history omits an observed tick-zero GetHeartPos')
    return binding

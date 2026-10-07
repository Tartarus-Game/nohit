"""Pure RPGText event-sheet phase; does not stop physics or execute callbacks.

Source: repo_jcw87/Event sheets/RPGText.xml. The caller runs this AFTER the
current tick's Timeline phase, including newly created text. EndSansText's
TLResume affects the next Timeline phase, not commands earlier in this tick.
Confirm is separate from the existing LRUD/Cancel physics input mask.
"""
from dataclasses import dataclass, replace
import math


CHAR_PERIOD = 1. / 30.
CONFIRM_BIT = 32
MOVEMENT_MASK = 31


def split_control(control: int):
    """Decode unified LRUD/Cancel/Confirm without changing the physics mask.

    Bits 0..4 retain the existing movement operator contract. Confirm is bit
    5 and must never be passed to old 32-entry action tables as another axis.
    """
    if type(control) is not int or not 0 <= control < 64:
        raise ValueError('unified control must be an integer in [0, 63]')
    return control & MOVEMENT_MASK, bool(control & CONFIRM_BIT), bool(control & 16)


def utf16_length(text: str) -> int:
    """Construct/JavaScript len counts UTF-16 units, including lone surrogates."""
    return len(text.encode('utf-16-le', errors='surrogatepass')) // 2


@dataclass(frozen=True)
class DialogueState:
    text: str
    current_char: int = 0
    t: float = 0.
    interactive: bool = True
    timeout: float = 0.
    end_func: str = 'EndSansText'
    alive: bool = True

    @property
    def length(self):
        return utf16_length(self.text)

    @property
    def displayed_text(self):
        data = self.text.encode('utf-16-le', errors='surrogatepass')[:2*self.current_char]
        return data.decode('utf-16-le', errors='surrogatepass')


@dataclass(frozen=True)
class DialogueStep:
    state: DialogueState
    destroyed: bool = False
    callback: str | None = None


def step_dialogue(state: DialogueState, dt: float, *, confirm: bool = False,
                  previous_confirm: bool = False, cancel: bool = False,
                  previous_cancel: bool = False) -> DialogueStep:
    """Evaluate one RPGText phase and return an opaque immediate callback.

    This does not validate mode-specific input legality: MODE_SINGLE rejects
    Cancel in the outer game, even though Cancel has text-skip semantics here.
    Dead instances never emit their callback a second time. If a callback
    creates another object, the caller must handle native event selection and
    phase scheduling; this function is only a single existing text instance.
    """
    if not isinstance(state, DialogueState):
        raise TypeError('DialogueState required')
    if not isinstance(state.text, str) or not isinstance(state.end_func, str):
        raise ValueError('text and end_func must be strings')
    if (type(state.current_char) is not int or not 0 <= state.current_char <= state.length
            or not math.isfinite(state.t) or state.t < 0.
            or not math.isfinite(state.timeout) or state.timeout < 0.):
        raise ValueError('invalid native text state')
    if not math.isfinite(dt) or dt < 0.:
        raise ValueError('dt must be finite and nonnegative')
    if any(v not in (0, 1) for v in (confirm, previous_confirm, cancel, previous_cancel)):
        raise ValueError('VPad edge inputs must be zero or one')
    if not state.alive:
        return DialogueStep(state)

    t = state.t + dt
    char = state.current_char
    if char < state.length and t >= CHAR_PERIOD:
        t -= CHAR_PERIOD
        char += 1  # One event block, not a while loop or floor(t / period).
    out = replace(state, t=t, current_char=char)
    destroyed = False
    if state.interactive:
        # Confirm is evaluated BEFORE Cancel; a simultaneous skip cannot also
        # dismiss an incomplete line in this same phase.
        if confirm > previous_confirm and char == state.length:
            destroyed = True
        elif cancel > previous_cancel:
            out = replace(out, current_char=state.length, t=0.)
    elif char == state.length and state.timeout > 0.:
        timeout = state.timeout - min(dt, state.timeout)
        out = replace(out, timeout=timeout)
        destroyed = timeout == 0.
    if destroyed:
        out = replace(out, alive=False)
    return DialogueStep(out, destroyed, state.end_func if destroyed and state.end_func else None)

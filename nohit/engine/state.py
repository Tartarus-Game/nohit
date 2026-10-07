"""
nohit.engine.state
~~~~~~~~~~~~~~~~~~
5D Micro-State Representation, 32-bit Integer Packing, and Discrete Control Alphabet.
Implements Feature 8 (STATE_PACKING) and Feature 9 (DISCRETE_ACTIONS) anchored to docs.txt.
"""

from __future__ import annotations

from typing import Sequence, Tuple, Union
import numpy as np

from nohit.common.constants import (
    ACTIONS,
    SOUL_MAX_X,
    SOUL_MAX_Y,
    V_MIN,
    V_MAX,
    TAU_MAX,
    V_OFFSET,
)
from nohit.common.types import Action, ALL_ACTIONS, State


# ==============================================================================
# Scalar State Packing & Unpacking (Feature 8, docs.txt § 4)
# ==============================================================================
#
# vy is mode-dependent:
#   * "docs" mode  : discrete px/frame velocity, range [V_MIN, V_MAX] = [-12, 8].
#                    A fixed *100 scaling reproduces these exactly.
#   * "c2" mode    : the stepper stores vy * VY_SCALE (see nohit.engine.dynamics)
#                    to keep the ~0.05 px/frame^2 gravity steps from rounding
#                    away. With VY_SCALE = 64 the reachable range is
#                    [-12.5 * 64, ~4 * 64] = [-800, 256].
#
# To hold BOTH without breaking either, vy is packed as a signed value scaled by
# 100 with a bias of 900, requiring 11 bits:
#     docs: -12 -> 100*100 =  10000  ...  8 -> 1700   (in range)
#     c2  : -800 -> 100*100 = -79000 ... 256 -> 17256 (NOT in range)
# so instead the scaling is chosen per maximum magnitude below.
VY_KEY_SCALE: int = 1
"""Quantisation of ``vy`` in the packed key.

Both models store ``vy`` as an integer that is already their native unit:

  * ``docs`` -- integer px/frame in [-12, 8].
  * ``c2``   -- ``px_per_frame * dynamics.VY_SCALE`` (=64), i.e. 1/64 px/frame
                granularity, in [-800, 256].

Scale 1 is therefore exact for both, and any coarser scale merges states that
differ by real physical amounts (at 64, twelve distinct gravity accumulations
collapse onto one key). Use :func:`configure_vy_quantisation` only if a future
model stores vy in a unit finer than its packed resolution.
"""

VY_KEY_BIAS: int = 500
"""Bias applied before packing so negative velocities stay positive.

The 10-bit field holds [0, 1023]. Reachable ranges:

  * ``c2``   -- vy = px/frame * ``dynamics.VY_SCALE`` (=16). Terminal velocity
                is -750 px/s = -12.5 px/frame -> -200 (exactly the field's
                floor); the jump impulse peak is +180 px/s = +3.0 px/frame
                -> +48.   So [-200, 48] maps to [0, 248].
  * ``docs`` -- integer px/frame in [-12, 8] -> [188, 208].

MUST stay consistent with ``dynamics.VY_SCALE``: if that scale grows, the
negative side overflows the field and the packed key wraps."""

VY_KEY_BITS: int = 10
VY_KEY_MASK: int = (1 << VY_KEY_BITS) - 1


def configure_vy_quantisation(scale: int, bias: int = VY_KEY_BIAS) -> None:
    """Sets the vy quantisation used by the pack/unpack helpers.

    Call this once per solve with the scale matching the physics model, before
    packing any state.
    """
    global VY_KEY_SCALE, VY_KEY_BIAS
    if scale < 1:
        raise ValueError(f"vy quantisation scale must be >= 1, got {scale}")
    VY_KEY_SCALE = int(scale)
    VY_KEY_BIAS = int(bias)


def vy_quantisation_for_mode(physics_mode: str) -> int:
    """Returns the vy scale that packs ``physics_mode`` losslessly.

    Both models already store vy in their native integer unit, so this is 1;
    the helper exists so the intent is explicit at the call sites and a future
    finer-grained model has one place to change.
    """
    _ = physics_mode
    return 1

# Bit layout (exactly 32 bits, every field preserved):
#   bits  0..8  : x          (9 bits, [0, 511])
#   bits  9..16 : y          (8 bits, [0, 255])
#   bits 17..26 : vy + 500   (10 bits, covers [-500, 523] exactly)
#   bit  27     : kappa      (1 bit)
#   bits 28..31 : tau        (4 bits, [0, 15], the docs jump-hold counter)
#
# `vy` is stored in the model's native integer unit (px/frame for "docs",
# px/frame * VY_SCALE for "c2"). The 10-bit field with a bias of 500 covers:
#   * c2   -- VY_SCALE = 40 gives [-500, +120], i.e. [-12.5, +3.0] px/frame
#   * docs -- [-12, 8] -> [488, 508]
#
# VY_SCALE = 40 is not arbitrary: the authoritative gravity step is
# 0.05 px/frame^2 = 1/20, and 40 is the largest multiple of 20 whose product
# with the 12.5 px/frame terminal velocity still fits the field. That makes the
# gravity increment exactly 2 cells, so gravity integrates WITHOUT quantisation
# error -- the previous scales (16, 32) rounded 0.05 up to 0.0625 (+25%), which
# capped the planner's jump at 21 px against the engine's 72 px.
#
# `tau` keeps its 4 bits: it is the docs jump-hold counter (0..15) and selects
# the ascent gravity branch, so truncating it would merge real states.
_X_BITS = 9
_Y_SHIFT = _X_BITS                       # 9
_VY_SHIFT = _Y_SHIFT + 8                 # 17
_KAPPA_SHIFT = _VY_SHIFT + VY_KEY_BITS   # 28
_TAU_SHIFT = _KAPPA_SHIFT + 1            # 29
_TAU_BITS = 4
_X_MASK = (1 << _X_BITS) - 1


def pack_state(
    x_or_state: Union[int, Tuple[int, int, int, int, int], State],
    y: int | None = None,
    vy: int | None = None,
    kappa: int | None = None,
    tau: int | None = None,
) -> int:
    """Packs 5D micro-state (x, y, vy, kappa, tau) into a 32-bit unsigned key.

    Every field is preserved; ``vy`` is biased by :data:`VY_KEY_BIAS` so both
    the ``docs`` (px/frame) and ``c2`` (px/frame * 64) models pack losslessly.
    ``x`` and ``y`` are masked to 8 bits each, which covers every arena in use
    (the largest observed is 409x179 -> x needs 9 bits, so x is masked to the
    arena width by the caller via :func:`configure_xy_bounds` if ever needed).

    Accepts either 5 scalar arguments or a single 5-tuple / State object.
    """
    if y is None:
        if isinstance(x_or_state, State):
            x, y_val, vy_val, kappa_val, tau_val = (
                x_or_state.x,
                x_or_state.y,
                x_or_state.vy,
                x_or_state.kappa,
                x_or_state.tau,
            )
        else:
            x, y_val, vy_val, kappa_val, tau_val = x_or_state
    else:
        x = x_or_state
        y_val = y
        vy_val = vy
        kappa_val = kappa
        tau_val = tau

    vy_key = (int(vy_val) + VY_KEY_BIAS) & VY_KEY_MASK
    return int(
        (int(x) & _X_MASK)
        | ((int(y_val) & 0xFF) << _Y_SHIFT)
        | (vy_key << _VY_SHIFT)
        | ((int(kappa_val) & 0x01) << _KAPPA_SHIFT)
        | ((int(tau_val) & ((1 << _TAU_BITS) - 1)) << _TAU_SHIFT)
    )


def unpack_state(packed: int | np.integer) -> Tuple[int, int, int, int, int]:
    """Decodes a 32-bit key back into (x, y, vy, kappa, tau)."""
    p = int(packed)
    x = p & _X_MASK
    y = (p >> _Y_SHIFT) & 0xFF
    vy = ((p >> _VY_SHIFT) & VY_KEY_MASK) - VY_KEY_BIAS
    kappa = (p >> _KAPPA_SHIFT) & 0x01
    tau = (p >> _TAU_SHIFT) & ((1 << _TAU_BITS) - 1)
    return (x, y, vy, kappa, tau)


def unpack_state_to_state(packed: int | np.integer) -> State:
    """Decodes a 32-bit integer key into a State dataclass instance."""
    x, y, vy, kappa, tau = unpack_state(packed)
    return State(x=x, y=y, vy=vy, kappa=kappa, tau=tau)


# ==============================================================================
# Vectorized State Packing & Unpacking (High-Performance DP Acceleration)
# ==============================================================================

def pack_states_vec(
    x: np.ndarray,
    y: np.ndarray,
    vy: np.ndarray,
    kappa: np.ndarray,
    tau: np.ndarray,
) -> np.ndarray:
    """Vectorized bit-packing of the 5 coordinate arrays into uint32 keys."""
    vy_key = (vy.astype(np.int64) + VY_KEY_BIAS).astype(np.uint32) & np.uint32(VY_KEY_MASK)
    return (
        (x.astype(np.uint32) & np.uint32(_X_MASK))
        | ((y.astype(np.uint32) & np.uint32(0xFF)) << np.uint32(_Y_SHIFT))
        | (vy_key << np.uint32(_VY_SHIFT))
        | ((kappa.astype(np.uint32) & np.uint32(0x01)) << np.uint32(_KAPPA_SHIFT))
        | ((tau.astype(np.uint32) & np.uint32((1 << _TAU_BITS) - 1)) << np.uint32(_TAU_SHIFT))
    )


def pack_states_array(states: np.ndarray) -> np.ndarray:
    """Vectorized bit-packing of an (N, 5) state array into a 1D uint32 array."""
    if states.ndim == 1:
        states = states.reshape(1, -1)
    if states.shape[0] == 0:
        return np.empty(0, dtype=np.uint32)
    return pack_states_vec(
        states[:, 0],
        states[:, 1],
        states[:, 2],
        states[:, 3],
        states[:, 4],
    )


def unpack_states_vec(
    packed: np.ndarray,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Vectorized bit-unpacking into 5 arrays. ``tau`` decodes to zeros.

    The vy arithmetic is done in int64: ``(key - bias) * scale`` reaches
    ``-800 * 64 = -51200`` for the c2 model, which overflows int32 before the
    final narrowing.
    """
    p = packed.astype(np.uint32)
    x = (p & np.uint32(_X_MASK)).astype(np.int32)
    y = ((p >> np.uint32(_Y_SHIFT)) & np.uint32(0xFF)).astype(np.int32)
    vy_raw = ((p >> np.uint32(_VY_SHIFT)) & np.uint32(VY_KEY_MASK)).astype(np.int64)
    vy = (vy_raw - np.int64(VY_KEY_BIAS)).astype(np.int32)
    kappa = ((p >> np.uint32(_KAPPA_SHIFT)) & np.uint32(0x01)).astype(np.int32)
    tau = ((p >> np.uint32(_TAU_SHIFT)) & np.uint32((1 << _TAU_BITS) - 1)).astype(np.int32)
    return x, y, vy, kappa, tau


def unpack_states_to_array(packed: np.ndarray) -> np.ndarray:
    """Vectorized bit-unpacking of a 1D uint32 array into an (N, 5) int32 state array."""
    if len(packed) == 0:
        return np.empty((0, 5), dtype=np.int32)
    x, y, vy, kappa, tau = unpack_states_vec(packed)
    return np.column_stack([x, y, vy, kappa, tau]).astype(np.int32)


__all__ = [
    "ACTIONS",
    "Action",
    "ALL_ACTIONS",
    "State",
    "pack_state",
    "unpack_state",
    "unpack_state_to_state",
    "pack_states_vec",
    "pack_states_array",
    "unpack_states_vec",
    "unpack_states_to_array",
]

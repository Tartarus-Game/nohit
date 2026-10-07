"""
nohit.engine
~~~~~~~~~~~~
Discrete hybrid dynamics forward reachable set DP solver.
Implements Milestone 2: nohit.engine (Hybrid Lattice DP Solver).
"""

from __future__ import annotations

from nohit.engine.state import (
    ACTIONS,
    Action,
    ALL_ACTIONS,
    State,
    pack_state,
    unpack_state,
    unpack_state_to_state,
    pack_states_vec,
    pack_states_array,
    unpack_states_vec,
    unpack_states_to_array,
)
from nohit.engine.dynamics import (
    step_dynamics,
    step_dynamics_batch,
)
from nohit.engine.solver import (
    solve_lattice_dp,
    SolveResult,
    SolveStats,
)

__all__ = [
    # State representation & packing
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
    # Forward dynamics
    "step_dynamics",
    "step_dynamics_batch",
    # DP Solver
    "solve_lattice_dp",
    "SolveResult",
    "SolveStats",
]

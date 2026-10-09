"""
nohit.engine
~~~~~~~~~~~~
Discrete hybrid dynamics forward reachable set DP solver.
Implements Milestone 2: nohit.engine (Hybrid Lattice DP Solver).
"""

from __future__ import annotations

# Legacy package exports are resolved only when requested. Importing the CSV
# solver must not eagerly load the retired lattice solver and its JIT graph.
from importlib import import_module

_EXPORTS = {'ACTIONS': 'state', 'Action': 'state', 'ALL_ACTIONS': 'state', 'State': 'state', 'pack_state': 'state', 'unpack_state': 'state', 'unpack_state_to_state': 'state', 'pack_states_vec': 'state', 'pack_states_array': 'state', 'unpack_states_vec': 'state', 'unpack_states_to_array': 'state', 'step_dynamics': 'dynamics', 'step_dynamics_batch': 'dynamics', 'solve_lattice_dp': 'solver', 'SolveResult': 'solver', 'SolveStats': 'solver'}

def __getattr__(name):
    if name not in _EXPORTS:
        raise AttributeError(name)
    value = getattr(import_module('.' + _EXPORTS[name], __name__), name)
    globals()[name] = value
    return value

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

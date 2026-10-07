"""Test Op-4: Native Trajectory Reconstructor."""
import time
import numpy as np
from pathlib import Path
from numba import njit
from nohit.engine.compact_wave import ROOT, compile_wave
from nohit.engine.compact_lattice import native_micro_into

@njit(cache=True)
def reconstruct_trace(initial, actions, schedule):
    layers = len(actions)
    trace = np.empty((layers + 1, initial.size), np.float64)
    trace[0] = initial
    state = initial.copy()
    for frame_index in range(layers):
        ux = actions[frame_index, 0]
        up = actions[frame_index, 1]
        for micro in range(4):
            tick = frame_index * 4 + micro + 1
            native_micro_into(state, ux, up, schedule[tick], state)
        trace[frame_index + 1] = state
    return trace

def main():
    schedule, geometry, initial = compile_wave(ROOT/'c2-sans-fight/sans_platforms4hard.csv')
    # Dummy actions or real actions
    import json
    data = json.load(open(ROOT/'tools/operator-results/compact-platforms4hard.json'))
    actions = np.array(data['actions'], dtype=np.int8)
    
    # 1. Baseline Python loop
    t0 = time.perf_counter()
    trace_py = [initial.tolist()]
    state_py = initial.copy()
    for frame_index, action in enumerate(actions):
        for micro in range(4):
            native_micro_into(state_py, *action, schedule[frame_index*4+micro+1], state_py)
        trace_py.append(state_py.tolist())
    t1 = time.perf_counter()
    print(f'Baseline Python loop time: {(t1-t0)*1000:.3f} ms')
    
    # 2. Native reconstruct_trace (first call, including JIT compile)
    t2 = time.perf_counter()
    trace_native = reconstruct_trace(initial, actions, schedule)
    t3 = time.perf_counter()
    print(f'Native reconstruct_trace (cold/first call): {(t3-t2)*1000:.3f} ms')
    
    # 3. Native reconstruct_trace (second call, warm)
    t4 = time.perf_counter()
    trace_warm = reconstruct_trace(initial, actions, schedule)
    t5 = time.perf_counter()
    print(f'Native reconstruct_trace (warm): {(t5-t4)*1000:.3f} ms')
    
    # Verify bitwise exact equality
    diff = np.max(np.abs(np.array(trace_py) - trace_native))
    print(f'Max absolute difference between Python and Native trace: {diff}')
    assert diff == 0.0, 'Traces must be bitwise identical!'
    print('Traces are 100% bitwise identical!')

if __name__ == '__main__':
    main()

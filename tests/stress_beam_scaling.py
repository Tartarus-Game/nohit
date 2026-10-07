import time
import numpy as np
from nohit.engine.compact_lattice import search_frs_dp_bellman
from nohit.engine.compact_wave import ROOT, compile_wave, prepare_collision_native

schedule, geometry, initial = compile_wave(ROOT / 'c2-sans-fight/sans_platforms4hard.csv')
mask = prepare_collision_native(geometry, margin_x=1.0, margin_y=2.0)
starts = np.tile(initial, 9)
for g in range(3):
    starts[g * 15 + 8] = 0.75
    starts[g * 15 + 13] = 0.0

# Warm up JIT
search_frs_dp_bellman(mask, schedule, starts, max_states=1000, max_beam=10)

print(f"{'beam':>6} | {'status':>6} | {'frame':>5} | {'expansions':>10} | {'time_ms':>10}")
print("-" * 50)

for beam in [1, 2, 5, 10, 20, 50, 100, 200, 500, 1000, 2000, 5000]:
    t0 = time.perf_counter()
    status, frame, exp, visits, actions = search_frs_dp_bellman(
        mask, schedule, starts, max_states=30000, max_beam=beam
    )
    t1 = time.perf_counter()
    dur_ms = (t1 - t0) * 1000
    print(f"{beam:6d} | {status:6d} | {frame:5d} | {exp:10d} | {dur_ms:10.2f}")

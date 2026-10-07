import tracemalloc
import gc
import numpy as np
from nohit.engine.compact_lattice import search_frs_dp_bellman
from nohit.engine.compact_wave import ROOT, compile_wave, prepare_collision_native

schedule, geometry, initial = compile_wave(ROOT / 'c2-sans-fight/sans_platforms4hard.csv')
mask = prepare_collision_native(geometry, margin_x=1.0, margin_y=2.0)
starts = np.tile(initial, 9)
for g in range(3):
    starts[g * 15 + 8] = 0.75
    starts[g * 15 + 13] = 0.0

# Warm up
search_frs_dp_bellman(mask, schedule, starts, max_states=1000, max_beam=10)
gc.collect()

tracemalloc.start()
snap0 = tracemalloc.take_snapshot()

history = []
for i in range(1, 31):
    status, frame, exp, visits, actions = search_frs_dp_bellman(
        mask, schedule, starts, max_states=30000, max_beam=100
    )
    if i % 10 == 0:
        gc.collect()
        current, peak = tracemalloc.get_traced_memory()
        history.append((i, current / (1024*1024), peak / (1024*1024)))
        print(f"Iteration {i:2d}: Traced Current = {current / (1024*1024):.3f} MB, Peak = {peak / (1024*1024):.3f} MB")

drift = history[-1][1] - history[0][1]
print(f"Traced memory drift between iter 10 and iter 30: {drift:+.4f} MB")

import numpy as np
from nohit.engine.compact_solver import solve_platforms4hard
from nohit.engine.compact_wave import ROOT, compile_wave, prepare_collision_native
from nohit.engine.compact_lattice import blocked_xy, product_micro_into, native_micro_into

res = solve_platforms4hard()
actions = np.array(res['actions'], dtype=np.int8)
schedule, geometry, initial = compile_wave(ROOT / 'c2-sans-fight/sans_platforms4hard.csv')
mask = prepare_collision_native(geometry, margin_x=1.0, margin_y=2.0)

starts = np.tile(initial, 9)
for g in range(3):
    starts[g * 15 + 8] = 0.75
    starts[g * 15 + 13] = 0.0

# 1. Action profile
action_counts = {}
for a in actions:
    key = (int(a[0]), int(a[1]))
    action_counts[key] = action_counts.get(key, 0) + 1
print('Action distribution:', sorted(action_counts.items()))

# 2. Check nominal trajectory
state = initial.copy()
nom_hits = 0
min_x, max_x = float('inf'), float('-inf')
min_y, max_y = float('inf'), float('-inf')
min_dist_overall = 999.0
min_dist_tick = -1

for frame, (ux, up) in enumerate(actions):
    for m in range(4):
        tick = frame * 4 + m + 1
        native_micro_into(state, ux, up, schedule[tick], state)
        x, y = state[0], state[1]
        min_x = min(min_x, x)
        max_x = max(max_x, x)
        min_y = min(min_y, y)
        max_y = max(max_y, y)
        if blocked_xy(mask, tick, x, y):
            nom_hits += 1
        # Check clearance: probe radius 1..10
        cur_clearance = 10.0
        for r in range(1, 10):
            found_hazard = False
            for dx in range(-r, r+1):
                for dy in (-r, r):
                    if blocked_xy(mask, tick, x + dx, y + dy):
                        found_hazard = True
                        break
                if found_hazard:
                    break
                for dy in range(-r+1, r):
                    for dx in (-r, r):
                        if blocked_xy(mask, tick, x + dx, y + dy):
                            found_hazard = True
                            break
                    if found_hazard:
                        break
            if found_hazard:
                cur_clearance = float(r)
                break
        if cur_clearance < min_dist_overall:
            min_dist_overall = cur_clearance
            min_dist_tick = tick

print(f'Nominal trajectory: hits={nom_hits}, x_range=[{min_x:.2f}, {max_x:.2f}], y_range=[{min_y:.2f}, {max_y:.2f}]')
print(f'Minimum clearance to mask hazard: {min_dist_overall} px at tick {min_dist_tick}')

# 3. Product trajectory
prod_state = starts.copy()
prod_hits = [0] * 9
for frame, (ux, up) in enumerate(actions):
    for m in range(4):
        tick = frame * 4 + m + 1
        product_micro_into(prod_state, ux, up, schedule[tick], prod_state, tick)
        for mem in range(9):
            if blocked_xy(mask, tick, prod_state[mem*5], prod_state[mem*5+1]):
                prod_hits[mem] += 1
print('Product trajectory 9 members hits:', prod_hits, 'Total hits:', sum(prod_hits))

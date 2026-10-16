import numpy as np

# Compare float simulation vs discrete rounded simulation
def compare_float_vs_discrete():
    # 1. Float simulation
    y_float = 0.0
    vy_float = 0.0
    k_float = 1
    
    # 2. Discrete simulation
    y_disc = 0.0
    vy_disc = 0.0
    k_disc = 1
    
    errors = []
    
    for f in range(40):
        # Float step
        if k_float == 1:
            vy_float = 6.0
            k_float = 0
        else:
            ds = -vy_float * 30.0
            if ds <= -120: g = 0.2
            elif ds <= -30: g = 0.5
            elif ds <= 15: g = 0.2
            else: g = 0.6
            vy_float = max(-25.0, vy_float - g)
            
        y_float += vy_float
        if y_float <= 0.0:
            y_float = 0.0
            vy_float = 0.0
            k_float = 1
            
        # Discrete step (storing vy as float in state or int)
        if k_disc == 1:
            vy_disc = 6.0
            k_disc = 0
        else:
            ds = -vy_disc * 30.0
            if ds <= -120: g = 0.2
            elif ds <= -30: g = 0.5
            elif ds <= 15: g = 0.2
            else: g = 0.6
            vy_disc = max(-25.0, vy_disc - g)
            
        y_disc += vy_disc
        if y_disc <= 0.0:
            y_disc = 0.0
            vy_disc = 0.0
            k_disc = 1
            
        err = abs(y_float - y_disc)
        errors.append((f, y_float, y_disc, err))
        
    print(f"Max error between float and discrete: {max(e[3] for e in errors):.4f} px")

compare_float_vs_discrete()

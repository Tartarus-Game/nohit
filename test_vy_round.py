def test_integer_rounded_vy():
    y_float = 0.0
    vy_float = 0.0
    k_float = 1
    
    y_int = 0
    vy_int = 0
    k_int = 1
    
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
            
        # If state carries float internally during the DP step:
        # Notice in solver.py:
        # curr_states is numpy array of shape (N, 5):
        # We can keep curr_states as float or int, but what if state key packs integer?
        
    print(f"Float jump apex: {y_float}")

test_integer_rounded_vy()

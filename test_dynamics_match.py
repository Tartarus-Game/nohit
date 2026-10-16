import numpy as np

def test_c2_step_dynamics():
    # Simulate jump using step_dynamics logic
    y = 0.0
    vy = 0.0
    kappa = 1
    tau = 0
    
    dt = 1.0 / 30.0
    traj_step = []
    
    # Hold jump for 30 frames
    for f in range(50):
        uy = 1 if f < 30 else 0
        
        # Ground jump trigger
        if kappa == 1 and uy == 1:
            vy = 180.0 * dt  # 6.0 px/f
            kappa = 0
            tau = 1
        elif kappa == 0:
            # Cutoff on key release
            if uy == 0 and vy > 30.0 * dt:
                vy = 30.0 * dt
                
            down_speed = -vy / dt  # in px/s
            if down_speed <= -120.0:
                grav = 180.0
            elif down_speed <= -30.0:
                grav = 450.0
            elif down_speed <= 15.0:
                grav = 180.0
            else:
                grav = 540.0
                
            vy = vy - grav * dt * dt
            if vy < -750.0 * dt:
                vy = -750.0 * dt
                
        y_next = y + vy
        if y_next <= 0.0:
            y = 0.0
            vy = 0.0
            kappa = 1
            tau = 0
            traj_step.append((f, y, vy))
            break
        else:
            y = y_next
            traj_step.append((f, y, vy))
            
    print(f"Total frames: {len(traj_step)}")
    print(f"Apex height: {max(t[1] for t in traj_step):.2f} px at frame {np.argmax([t[1] for t in traj_step])}")
    print(f"Sample frames (0, 5, 10, 15, 20, 25, 30, 35):")
    for idx in [0, 5, 10, 15, 20, 25, 30, 35]:
        if idx < len(traj_step):
            print(f"  Frame {idx}: y={traj_step[idx][1]:.2f}, vy={traj_step[idx][2]:.2f}")

test_c2_step_dynamics()

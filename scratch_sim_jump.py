# Exact simulation of C2 PlayerMovement jump at 30 FPS (dt = 1/30)

def simulate_c2_jump(hold_frames=30):
    dt = 1.0 / 30.0
    y = 0.0
    dy = -180.0  # Initial jump speed (negative is UP in C2)
    cutoff = -30.0
    history = []
    
    for f in range(50):
        is_held = (f < hold_frames)
        
        # In C2: key release cutoff
        if not is_held and dy < cutoff:
            dy = cutoff
            
        down_speed = dy
        # Gravity logic from Battle.xml:
        # DownSpeed < 240 and DownSpeed > 15 -> 540
        # DownSpeed <= 15 and DownSpeed > -30 -> 180
        # DownSpeed <= -30 and DownSpeed > -120 -> 450
        # DownSpeed <= -120 -> 180
        if down_speed <= -120:
            gravity = 180.0
        elif down_speed <= -30:
            gravity = 450.0
        elif down_speed <= 15:
            gravity = 180.0
        else:
            gravity = 540.0
            
        # Apply gravity
        dy += gravity * dt
        if dy > 750.0:
            dy = 750.0
            
        # Move
        y -= dy * dt  # upward is positive y in our convention
        if y < 0:
            y = 0.0
            dy = 0.0
            history.append((f, y, -dy))
            break
            
        history.append((f, y, -dy))
        
    return history

full_jump = simulate_c2_jump(hold_frames=30)
short_jump = simulate_c2_jump(hold_frames=2)

print("Full jump:")
print(f"Total duration: {len(full_jump)} frames ({len(full_jump)/30:.2f}s)")
max_h = max(h[1] for h in full_jump)
print(f"Max height: {max_h:.2f} px")

print("\nShort tap jump (2 frames):")
print(f"Total duration: {len(short_jump)} frames ({len(short_jump)/30:.2f}s)")
max_short_h = max(h[1] for h in short_jump)
print(f"Max height: {max_short_h:.2f} px")

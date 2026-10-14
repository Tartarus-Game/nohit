extends RefCounted
## DESIGNATED SLOT: replace this file with your original red/blue operator.
## mask bits: left=1 right=2 up=4 down=8; store all latches in state.
func step(state: Dictionary, mask: int, delta: float) -> void:
	var axis := Vector2(int(bool(mask & 2)) - int(bool(mask & 1)), int(bool(mask & 8)) - int(bool(mask & 4)))
	if state.mode == "red":
		state.velocity = axis.normalized() * 120.0
	else:
		state.velocity.x = axis.x * 120.0
		if state.position.y >= 94.0 and mask & 4 and not state.previous_mask & 4:
			state.velocity.y = -180.0
		state.velocity.y += 420.0 * delta
	state.position += state.velocity * delta
	state.position = state.position.clamp(Vector2(6, 6), Vector2(94, 94))
	if state.position.y >= 94.0:
		state.velocity.y = minf(state.velocity.y, 0.0)
	state.previous_mask = mask

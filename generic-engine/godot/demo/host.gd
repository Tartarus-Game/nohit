extends Node2D
const Baker = preload("res://addons/nohit/native_baker.gd")
var state: Dictionary
var soul_shape := CircleShape2D.new()
var bullet_shape := RectangleShape2D.new()
var tracking := false
var blocked := false
var jump_trial := false
func reset(mode: String, follows: bool = false, impossible: bool = false) -> void:
	tracking = follows
	blocked = impossible
	soul_shape.radius = 3.0
	bullet_shape.size = Vector2(8, 28) if not blocked else Vector2(200, 200)
	state = {"tick": 0, "position": Vector2(50, 94 if mode == "blue" else 50), "velocity": Vector2.ZERO,
		"mode": mode, "previous_mask": 0, "damage": 0, "bullet_y": 50.0}
func capture() -> Dictionary:
	return state
func restore(snapshot: Dictionary) -> void:
	state = snapshot
func advance(mask: int, delta: float, controller: RefCounted) -> void:
	controller.step(state, mask, delta)
	state.tick += 1
	if tracking:
		state.bullet_y = move_toward(state.bullet_y, state.position.y, 0.5)
	if Baker.overlaps(player_shapes(), hazard_shapes()):
		state.damage += 1
func player_shapes() -> Array:
	return [{"shape": soul_shape, "transform": Transform2D(0.0, state.position)}]
func hazard_shapes() -> Array:
	if jump_trial:
		if state.tick < 10 or state.tick > 30:
			return []
		var floor_bar := RectangleShape2D.new()
		floor_bar.size = Vector2(110, 8)
		return [{"shape": floor_bar, "transform": Transform2D(0.0, Vector2(50, 94))}]
	var x: float = 110.0 - state.tick * 2.0
	return [{"shape": bullet_shape, "transform": Transform2D(0.2, Vector2(50, 50) if blocked else Vector2(x, state.bullet_y))}]
func damage_count() -> int:
	return state.damage
func finished() -> bool:
	return state.tick >= 45
func actions() -> Array:
	return [0, 1, 2, 4, 8, 5, 6, 9, 10]
func rank() -> float:
	if jump_trial:
		return state.position.y
	return -absf(state.position.y - state.bullet_y) - 0.01 * absf(state.position.x - 50.0)

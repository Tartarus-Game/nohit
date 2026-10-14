extends SceneTree
const Host = preload("res://demo/host.gd")
const Bridge = preload("res://addons/nohit/bridge.gd")
const Solver = preload("res://addons/nohit/solver.gd")
const Controller = preload("res://demo/soul_controller.gd")
const Nondeterministic = preload("res://demo/nondeterministic_host.gd")
const Baker = preload("res://addons/nohit/native_baker.gd")
var failures := 0
func check(value: bool, label: String) -> void:
	if not value:
		failures += 1
		push_error(label)
func _initialize() -> void:
	call_deferred("run")
func run() -> void:
	var host := Host.new()
	root.add_child(host)
	var bridge := Bridge.new()
	root.add_child(bridge)
	bridge.configure(host, Controller)
	var results: Array = []
	for mode in ["red", "blue"]:
		for tracking in [false, true]:
			host.reset(mode, tracking)
			var initial: Dictionary = host.capture().duplicate(true)
			var result: Dictionary = Solver.new().solve(bridge, 32, 60, 10.0, 1.0 / 60.0)
			check(result.status == "verified_adapter_route", mode + " search")
			check(var_to_bytes(initial) == var_to_bytes(host.capture()), "restore initial")
			result["mode"] = mode
			result["tracking"] = tracking
			results.append(result)
	host.reset("blue")
	host.jump_trial = true
	var jump_result: Dictionary = Solver.new().solve(bridge, 64, 60, 10.0, 1.0 / 60.0)
	check(jump_result.status == "verified_adapter_route" and jump_result.route.any(func(mask): return bool(mask & 4)), "blue jump required")
	jump_result["scenario"] = "blue_floor_bar_requires_jump"
	results.append(jump_result)
	host.jump_trial = false
	var bad_host := Nondeterministic.new()
	root.add_child(bad_host)
	bad_host.reset("red")
	bridge.configure(bad_host, Controller)
	check(Solver.new().solve(bridge, 4, 60, 10.0, 1.0 / 60.0).status == "replay_failed", "hidden state divergence rejected")
	bridge.configure(host, Controller)
	host.reset("red", false, true)
	check(Solver.new().solve(bridge, 32, 60, 2.0, 1.0 / 60.0).status == "unknown", "blocked stays unknown")
	var circle := CircleShape2D.new()
	circle.radius = 3.0
	var rectangle := RectangleShape2D.new()
	rectangle.size = Vector2(8, 28)
	var player: Array = [{"shape": circle, "transform": Transform2D.IDENTITY}]
	var hazards: Array = [{"shape": rectangle, "transform": Transform2D(0.7, Vector2(25, 25))}]
	var baked: Dictionary = Baker.bake_samples(player, hazards, Rect2(0, 0, 50, 50), 2.0)
	for y in baked.rows:
		for x in baked.columns:
			var i: int = y * baked.columns + x
			var expected: bool = circle.collide(Transform2D(0.0, Vector2(x, y) * 2.0), rectangle, hazards[0].transform)
			check(bool(baked.bits[i >> 3] & (1 << (i & 7))) == expected, "bake parity")
	var area := Area2D.new()
	var shape_node := CollisionShape2D.new()
	shape_node.shape = rectangle
	area.add_child(shape_node)
	root.add_child(area)
	area.position = Vector2(30, 20)
	var frozen: Array = Baker.capture(area)
	rectangle.size = Vector2(1, 1)
	check(frozen.size() == 1 and frozen[0].shape.size == Vector2(8, 28), "shape snapshot isolates animation mutation")
	shape_node.disabled = true
	check(Baker.capture(area).is_empty(), "disabled shapes excluded")
	var output := {"engine": Engine.get_version_info(), "failures": failures, "bake_samples": baked.columns * baked.rows, "results": results}
	var file := FileAccess.open("res://demo/test-results.json", FileAccess.WRITE)
	file.store_string(JSON.stringify(output, "\t"))
	print(JSON.stringify(output))
	quit(0 if failures == 0 else 1)

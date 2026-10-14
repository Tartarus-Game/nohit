extends "res://demo/host.gd"
const Controller = preload("res://demo/soul_controller.gd")
var replay_controller := Controller.new()
var route: Array = []
var cursor := 0
var label := Label.new()
func _ready() -> void:
	reset("blue" if "--blue" in OS.get_cmdline_user_args() else "red", true)
	$NoHitBridge.configure(self, Controller)
	add_child(label)
	label.position = Vector2(115, 10)
	label.text = "Searching with native Godot collision..."
	call_deferred("start_test")
func start_test() -> void:
	var result: Dictionary = $NoHitTester.run_test()
	print(JSON.stringify(result))
	if result.status == "verified_adapter_route":
		route = result.route
		label.text = "Adapter replay: %s\n%.1f ms\nThis demo is not a third-party game verdict." % [state.mode, result.elapsed_ms]
	else:
		label.text = "Search result: " + result.status
func _physics_process(delta: float) -> void:
	if cursor < route.size():
		advance(route[cursor], delta, replay_controller)
		cursor += 1
		if cursor == route.size():
			label.text += "\nReplay complete; damage events: %d" % damage_count()
	queue_redraw()
func _draw() -> void:
	if state.is_empty():
		return
	draw_rect(Rect2(3, 3, 94, 94), Color.GRAY, false, 1.0)
	draw_circle(state.position, 3.0, Color.RED if state.mode == "red" else Color.BLUE)
	for h in hazard_shapes():
		draw_set_transform_matrix(h.transform)
		h.shape.draw(get_canvas_item(), Color.WHITE)
	draw_set_transform_matrix(Transform2D.IDENTITY)

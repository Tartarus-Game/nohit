extends SceneTree
## Runs the ORIGINAL project main scene, autoloads, physics and damage code.
## Captures at the next physics boundary, before injecting the next input.
var adapter
var request = {}
var frames = []
var route = []
var tick = 0
var initial = {}
var ending_ticks = -1
var active = false
var output = ""
var failure = ""

func _initialize():
	call_deferred("setup")

func read_json(path):
	var file = FileAccess.open(path, FileAccess.READ)
	if file == null:
		return null
	return JSON.parse_string(file.get_as_text())

func write_json(path, value):
	var file = FileAccess.open(path, FileAccess.WRITE)
	if file == null:
		return false
	file.store_string(JSON.stringify(value))
	return true

func wait_physics():
	await physics_frame

func setup():
	var request_path = ""
	for arg in OS.get_cmdline_user_args():
		if arg.begins_with("--nohit-request="):
			request_path = arg.substr(16)
		if arg.begins_with("--nohit-output="):
			output = arg.substr(15)
	var parsed = read_json(request_path)
	if not parsed is Dictionary or output == "":
		push_error("NoHit: provide --nohit-request=<JSON> --nohit-output=<JSON>")
		quit(3)
		return
	request = parsed
	if not valid_request():
		complete("invalid_request")
		return
	seed(int(request.seed))
	var scene_path = request.get("scene", ProjectSettings.get_setting("application/run/main_scene", ""))
	var packed = load(scene_path)
	var script = load("res://nohit_adapter.gd")
	if not packed is PackedScene or script == null:
		failure = "Missing main scene or res://nohit_adapter.gd"
		complete("invalid_adapter")
		return
	var game = packed.instantiate()
	root.add_child(game)
	current_scene = game
	adapter = script.new()
	root.add_child(adapter)
	adapter.configure(game)
	for _i in range(int(request.get("warmup_ticks", 120))):
		if adapter.nohit_is_ready():
			break
		await wait_physics()
	if not adapter.nohit_is_ready():
		failure = "Adapter readiness timeout"
		complete("invalid_adapter")
		return
	for action in adapter.action_names:
		if not InputMap.has_action(action):
			failure = "InputMap action missing: " + str(action)
			complete("invalid_adapter")
			return
		Input.action_release(action)
	adapter.nohit_begin(int(request.seed))
	for action in adapter.action_names:
		if not InputMap.has_action(action):
			failure = "InputMap action missing: " + str(action)
			complete("invalid_adapter")
			return
	initial = observe()
	if failure != "" or not adapter.nohit_contract().get("damage_audit", false) or initial.is_empty():
		failure = failure if failure != "" else "Connect damage/KR audit and return a nonempty observation"
		complete("invalid_adapter")
		return
	if adapter.damage_events != 0 or adapter.kr_events != 0:
		complete("hit")
		return
	if adapter.attack_done:
		failure = "Attack already finished before the first native frame"
		complete("invalid_adapter")
		return
	active = true
	physics_frame.connect(boundary)

func valid_request():
	if request.get("schema") != "nohit.live.v1" or not request.get("route") is Array:
		return false
	if not request.get("seed") is float and not request.get("seed") is int:
		return false
	if request.get("max_ticks", 0) < 1 or request.get("max_ticks", 0) > 1000000:
		return false
	for mask in request.route:
		if not (mask is int or mask is float) or mask != int(mask) or mask < 0 or mask > 255:
			return false
	return request.get("settle_ticks", 2) >= 1 and request.get("settle_ticks", 2) <= 60

func observe():
	var value = adapter.nohit_observe()
	if not value is Dictionary or not json_value(value):
		failure = "Observation must contain only finite JSON values (no Nodes, Vector2, Resources)"
		return {}
	# Serialize now: observers may reuse mutable dictionaries later.
	return JSON.parse_string(JSON.stringify(value))

func json_value(value):
	if value == null or value is bool or value is int or value is String:
		return true
	if value is float:
		return is_finite(value)
	if value is Array:
		for item in value:
			if not json_value(item): return false
		return true
	if value is Dictionary:
		for key in value:
			if not key is String or not json_value(value[key]): return false
		return true
	return false

func boundary():
	if not active: return
	if tick > 0:
		var observation = observe()
		frames.append({"tick": tick, "state": observation,
			"damage_events": adapter.damage_events, "kr_events": adapter.kr_events,
			"finished": adapter.attack_done})
		if failure != "":
			complete("invalid_adapter")
			return
		if adapter.damage_events > 0 or adapter.kr_events > 0:
			complete("hit")
			return
		if adapter.attack_done:
			if ending_ticks < 0: ending_ticks = 0
			ending_ticks += 1
			if ending_ticks > int(request.get("settle_ticks", 2)):
				complete("native_route_candidate")
				return
	if tick >= int(request.max_ticks):
		complete("unknown")
		return
	var mask = 0
	if tick < request.route.size():
		mask = int(request.route[tick])
	elif request.get("repeat_last", false) and not request.route.is_empty():
		mask = int(request.route.back())
	adapter.nohit_apply_input(mask)
	route.append(mask)
	tick += 1

func complete(status):
	active = false
	var result = {"schema": "nohit.live.result.v1", "status": status, "reason": failure,
		"engine": Engine.get_version_info(), "seed": request.get("seed"),
		"initial": initial, "route": route, "frames": frames, "ticks": tick,
		"contract": adapter.nohit_contract() if adapter != null else {},
		"attack_completed": adapter.attack_done if adapter != null else false,
		"damage_events": adapter.damage_events if adapter != null else 0,
		"kr_events": adapter.kr_events if adapter != null else 0,
		"verification": "native frames; fresh-process replay and negative control required"}
	if output == "" or not write_json(output, result):
		push_error("NoHit: cannot write output")
		quit(3)
		return
	print("NOHIT_LIVE ", status, " ticks=", tick)
	quit(0 if status == "native_route_candidate" else 2)

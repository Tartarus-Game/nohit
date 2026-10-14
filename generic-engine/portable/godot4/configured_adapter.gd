extends "res://addons/nohit_live/adapter_base.gd"
## Optional declarative adapter for games with existing native signals/hooks.
var config = {}
var config_error = ""

func configure(scene):
	game = scene
	var file = FileAccess.open("res://nohit_config.json", FileAccess.READ)
	var parsed = JSON.parse_string(file.get_as_text()) if file != null else null
	if not parsed is Dictionary:
		config_error = "Missing/invalid nohit_config.json"
		return
	config = parsed
	if config.get("schema") != "nohit.config.v1" or not config.get("observations") is Dictionary or config.observations.is_empty():
		config_error = "Invalid config schema or empty observations"
	if config.get("has_kr") != false and not config.has("kr_signal"):
		config_error = "Declare has_kr=false or connect the KR signal"
	if not config.has("damage_signal") or not config.has("finished_signal") or not config.has("start_method"):
		config_error = "Damage, completion signals and start method are required"
	action_names = config.get("actions", action_names)
	if config.has("input_viewport_path"):
		input_viewport = resolve(config.input_viewport_path)

func resolve(path):
	return game.get_node_or_null(NodePath(path))

func nohit_is_ready():
	# Invalid configuration fails immediately with actionable diagnostics.
	if config_error != "": return true
	return resolve(config.get("ready_path", ".")) != null

func hook(spec, callback):
	if not spec is Dictionary: return false
	var node = resolve(spec.get("path", "."))
	var signal_name = spec.get("signal", "")
	if node == null or not node.has_signal(signal_name):
		config_error = "Missing signal " + str(spec)
		return false
	node.connect(signal_name, Callable(self, callback))
	return true

func on_damage(_a = null, _b = null, _c = null, _d = null):
	record_damage()

func on_kr(_a = null, _b = null, _c = null, _d = null):
	record_kr()

func on_finished(_a = null, _b = null, _c = null, _d = null):
	mark_finished()

func nohit_begin(attack_seed):
	if config_error != "":
		push_error("NoHit config: " + config_error)
		return
	if not hook(config.damage_signal, "on_damage") or not hook(config.finished_signal, "on_finished"):
		push_error("NoHit config: " + config_error)
		return
	if config.has("kr_signal") and not hook(config.kr_signal, "on_kr"):
		push_error("NoHit config: " + config_error)
		return
	var target = resolve(config.get("start_path", "."))
	if target == null or not target.has_method(config.start_method):
		push_error("NoHit config: missing attack start method")
		return
	var arguments = config.get("start_arguments", ["$seed"]).duplicate(true)
	for i in range(arguments.size()):
		if arguments[i] is String and arguments[i] == "$seed": arguments[i] = attack_seed
	enable_damage_audit()
	target.callv(config.start_method, arguments)

func nohit_observe():
	var result = {}
	for key in config.get("observations", {}):
		var spec = config.observations[key]
		var node = resolve(spec.get("path", "."))
		if node == null: return {}
		result[key] = node.get_indexed(NodePath(spec.get("property", "")))
	return result

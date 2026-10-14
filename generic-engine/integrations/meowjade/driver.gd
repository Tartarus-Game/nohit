extends Node
var container: SceneContainer
var battle: BattleMain
var soul: SoulBattle
var tick := 0
var active := false
var damage_calls := 0
var heal_calls := 0
var route: Array = []
var states: Array = []
var scenario := "circle_white_red"
var output := "user://native-result.json"
var replay: Array = []
var replay_mode := false
var seed_value := 1
var horizon := 300
var attack_done := false
var native_overlap_ticks := 0
var strategy := "idle"
var hit_events: Array = []
var circle_node: Node
var spawned_ids := {}
var observed_bullets := 0
var start_usec := 0
var expected_bullets := 6
var bake_enabled := false
var baked_frames: Array = []
var entry: Dictionary = {}
var hp_drop_ticks := 0
const Baker = preload("res://nohit_integration/native_baker.gd")
const SoulScript = preload("res://nohit_integration/audited_soul.gd")
const ACTION_NAMES = ["ui_left", "ui_right", "ui_up", "ui_down"]

func _ready() -> void:
	process_physics_priority = -10000
	add_to_group("nohit_audit")
	for argument in OS.get_cmdline_user_args():
		var parts := argument.split("=", true, 1)
		if parts.size() != 2: continue
		match parts[0]:
			"--scenario": scenario = parts[1]
			"--out": output = parts[1]
			"--seed": seed_value = int(parts[1])
			"--bake": bake_enabled = parts[1] == "1"
			"--strategy": strategy = parts[1]
			"--plan": replay = JSON.parse_string(FileAccess.get_file_as_string(parts[1])).route
			"--replay":
				replay = JSON.parse_string(FileAccess.get_file_as_string(parts[1])).route
				replay_mode = true
	seed(seed_value)
	call_deferred("setup")

func setup() -> void:
	container = load("res://Singletons/scene_container.tscn").instantiate()
	add_child(container)
	container.change_scene_to_file("res://Battle/battle.tscn")
	battle = container.current_scene
	soul = battle.Soul_Battle
	Global.player_hp = Global.player_max_hp
	Global.player_kr = 0
	battle.Box.change_size(Vector2(140, 140), false)
	await get_tree().create_timer(1.0, false).timeout
	soul.enable()
	soul.global_position = Vector2(320, 350)
	soul.set_mode(SoulBattle.BLUE if scenario.ends_with("blue") else SoulBattle.RED)
	if scenario == "default_attack":
		var attack: Node = battle.Attacks.add_attack(load("res://Battle/Attacks/default_attack.tscn"))
		attack.throw.connect(battle.enemies[0].throw)
		attack.remove_attack.connect(func(_id): attack_done = true)
		attack.start_attack()
		horizon = 4000
	else:
		var circle: Node = load("res://Battle/Bullets/bullet_circle.tscn").instantiate()
		battle.AttacksParent.add_child(circle)
		circle_node = circle
		circle.position = soul.position
		# Parameters from the upstream default_attack.gd circular-wave section.
		if scenario.begins_with("circle_blue") or scenario.begins_with("circle_orange"):
			expected_bullets = 30
			circle.bullet_circle(load("res://Battle/Bullets/defaultbullet.tscn"), 100, 30, 80, 0.5).set_mode(Bullet.MODE_BLUE if scenario.begins_with("circle_blue") else Bullet.MODE_ORANGE).set_destroy_time(BulletCircle.FADE_OFF_SCREEN)
		else:
			circle.bullet_circle(load("res://Battle/Bullets/defaultbullet.tscn"), 250, 6, 80, 0.6)
		circle.tree_exited.connect(func(): attack_done = true)
	entry = {"x": soul.global_position.x, "y": soul.global_position.y, "hp": Global.player_hp, "kr": Global.player_kr, "tl": [battle.Box.TL.global_position.x, battle.Box.TL.global_position.y], "br": [battle.Box.BR.global_position.x, battle.Box.BR.global_position.y]}
	active = true
	start_usec = Time.get_ticks_usec()
	print("NOHIT_ENTRY ", soul.global_position, " mode=", soul.mode, " special=", soul.special_bullet_mode)

func choose_action() -> int:
	if not replay.is_empty(): return int(replay[mini(tick, replay.size()-1)])
	if strategy == "orbit": return [1, 4, 2, 8][(tick / 10) % 4]
	if strategy == "idle": return 0
	if strategy == "up": return 4
	if strategy == "left": return 1
	if strategy == "right": return 2
	if strategy == "down": return 8
	if strategy == "diagonal": return [5, 6, 9, 10][seed_value % 4]
	return 0

func _physics_process(_delta: float) -> void:
	if not active: return
	if tick > 0:
		states.append({"tick": tick, "x": soul.global_position.x, "y": soul.global_position.y,
			"vx": soul.velocity.x, "vy": soul.velocity.y, "mode": soul.mode, "hp": Global.player_hp, "kr": Global.player_kr, "invulnerable": soul.invulnerable, "monitoring": soul.Area.monitoring, "monitorable": soul.Area.monitorable, "body_shape_disabled": soul.Collision.disabled})
		for area in soul.Area.get_overlapping_areas():
			if area is BulletArea:
				native_overlap_ticks += 1
				break
	if is_instance_valid(circle_node):
		for bullet in circle_node.get_node("Bullets").get_children():
			spawned_ids[bullet.get_instance_id()] = true
		observed_bullets = spawned_ids.size()
		attack_done = observed_bullets == expected_bullets and circle_node.get_node("Bullets").get_child_count() == 0
		if expected_bullets == 30 and observed_bullets == expected_bullets:
			var all_left := true
			var center: Vector2 = circle_node.global_position
			for bullet in circle_node.get_node("Bullets").get_children():
				# Native scene bullets continue linearly after crossing the target.
				# Past 250 pixels, all are outside this 140-pixel arena and outward.
				if bullet.global_position.distance_to(center) < 250 or bullet.velocity.dot(bullet.global_position - center) <= 0:
					all_left = false
			attack_done = all_left
	if Global.player_hp < int(entry.hp): hp_drop_ticks += 1
	if bake_enabled and tick % 15 == 0: bake_native_frame()
	if damage_calls > 0:
		finish("hit")
		return
	if tick >= horizon:
		finish("native_nohit" if attack_done and hp_drop_ticks == 0 and Global.player_kr == 0 else "unknown")
		return
	var action: int = int(replay[tick]) if replay_mode and tick < replay.size() else choose_action()
	if replay_mode and tick >= replay.size():
		finish("replay_length_mismatch")
		return
	for bit in 4:
		if action & (1 << bit): Input.action_press(ACTION_NAMES[bit])
		else: Input.action_release(ACTION_NAMES[bit])
	route.append(action)
	tick += 1

func on_damage(area: BulletArea) -> void:
	damage_calls += 1
	hit_events.append({"tick": tick, "damage": area.damage, "kind": area.damage_mode})
func on_heal(_area: BulletArea) -> void:
	heal_calls += 1
func finish(status: String) -> void:
	active = false
	for name in ACTION_NAMES: Input.action_release(name)
	var result := {"status": status, "scenario": scenario, "strategy": strategy, "seed": seed_value,
		"ticks": tick, "attack_completed": attack_done, "damage_calls": damage_calls, "heal_calls": heal_calls,
		"hp": Global.player_hp, "kr": Global.player_kr, "native_overlap_ticks": native_overlap_ticks, "observed_bullets": observed_bullets, "special_bullet_mode": soul.special_bullet_mode,
		"route": route, "states": states, "baked_frames": baked_frames, "entry": entry, "hp_drop_ticks": hp_drop_ticks, "expected_bullets": expected_bullets, "hit_events": hit_events, "replay": replay_mode,
		"elapsed_ms": (Time.get_ticks_usec() - start_usec) / 1000.0, "engine": Engine.get_version_info(),
		"upstream": JSON.parse_string(FileAccess.get_file_as_string("res://nohit_integration/upstream.json"))}
	var file := FileAccess.open(output, FileAccess.WRITE)
	file.store_string(JSON.stringify(result, "\t"))
	print("NOHIT_RESULT ", status, " ticks=", tick, " damage=", damage_calls)
	var exit_code := 0 if status == "native_nohit" else 2
	# Let queue_free process before terminating native physics resources.
	container.queue_free()
	await get_tree().process_frame
	await get_tree().process_frame
	get_tree().quit(exit_code)

func bake_native_frame() -> void:
	var player_shapes: Array = Baker.capture(soul.Area)
	for p in player_shapes:
		p.transform.origin -= soul.global_position
	var layers := {0: [], 2: [], 3: []}
	var areas: Array[BulletArea] = []
	collect_areas(battle, areas)
	for area in areas:
		if area.monitorable and layers.has(area.damage_mode):
			layers[area.damage_mode].append_array(Baker.capture(area))
	var bounds := Rect2(battle.Box.TL.global_position, battle.Box.BR.global_position - battle.Box.TL.global_position)
	var frame := {"tick": tick, "bounds": [bounds.position.x, bounds.position.y, bounds.size.x, bounds.size.y], "spacing": 10, "layers": {}}
	for kind in layers:
		var sample: Dictionary = Baker.bake_samples(player_shapes, layers[kind], bounds, 10.0)
		frame.layers[str(kind)] = {"columns": sample.columns, "rows": sample.rows, "bits_hex": sample.bits.hex_encode()}
	baked_frames.append(frame)

func collect_areas(node: Node, out: Array[BulletArea]) -> void:
	if node is BulletArea: out.append(node)
	for child in node.get_children(): collect_areas(child, out)

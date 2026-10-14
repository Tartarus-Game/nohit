extends "res://addons/nohit_live/adapter_base.gd"
## Real upstream adapter for the shared live runner, Godot 3.5.3.
var view
var battle
var soul
var requested_battle = false
var loading_ticks = 0
var seen = {}

func nohit_is_ready():
	if not requested_battle:
		view = game.find_node("Viewport", true, false)
		view.loadScene(0)
		requested_battle = true
	loading_ticks += 1
	return loading_ticks >= 60 and is_instance_valid(view.curscene) and view.curscene.has_node("HeartLayer/PlayerHeart")

func nohit_begin(attack_seed):
	battle = view.curscene
	soul = battle.get_node("HeartLayer/PlayerHeart")
	input_viewport = soul.get_viewport()
	battle.get_node("Hud").menuNo = -1
	add_to_group("nohit_audit")
	action_names = ["ui_left", "ui_right", "ui_up", "ui_down", "ui_cancel"]
	var attacks = battle.get_node("Attacks")
	attacks.attack = 1 # Original full bonegap attack, unchanged.
	attacks.connect("menuEnable", self, "mark_finished")
	enable_damage_audit()
	seed(attack_seed)
	attacks.runAttack()

func on_damage(hp, kr):
	record_damage(hp)
	if kr > 0: record_kr(kr)

func nohit_observe():
	for bullet in get_tree().get_nodes_in_group("Bullet"):
		seen[bullet.get_instance_id()] = true
	var globals = get_node("/root/global")
	return {"x": soul.position.x, "y": soul.position.y,
		"vx": soul.motion_velocity.x, "vy": soul.motion_velocity.y,
		"hp": globals.hp, "kr": globals.kr, "mode": soul.mode,
		"inv": soul.invCount, "observed_bullets": seen.size()}

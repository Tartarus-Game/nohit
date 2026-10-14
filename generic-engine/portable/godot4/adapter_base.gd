extends Node
## Portable live adapter: no snapshots and no replacement soul physics.
## Use the subclass for game-specific startup and observations.
var game = null
var input_viewport = null
var damage_events = 0
var kr_events = 0
var audit_connected = false
var attack_done = false
var previous_mask = 0
var action_names = ["ui_left", "ui_right", "ui_up", "ui_down"]

func configure(scene):
	game = scene

func nohit_is_ready():
	return true

func nohit_begin(_seed):
	# Override: connect original damage/KR and attack-end hooks, then start attack.
	pass

func enable_damage_audit():
	# Call only after hooking ALL original damage and KR entry points.
	audit_connected = true

func record_damage(_amount = null):
	# Record contacts even if HP is later restored or damage rounds to zero.
	damage_events += 1

func record_kr(_amount = null):
	kr_events += 1

func mark_finished():
	# Call from the original attack-end event, never a test duration timeout.
	attack_done = true

func nohit_apply_input(mask):
	# Edge events reach _input as well as Input.is_action_pressed().
	for i in range(action_names.size()):
		var now = bool(mask & (1 << i))
		var before = bool(previous_mask & (1 << i))
		if now != before:
			var event = InputEventAction.new()
			event.action = action_names[i]
			event.pressed = now
			event.strength = 1.0 if now else 0.0
			if now:
				Input.action_press(action_names[i])
			else:
				Input.action_release(action_names[i])
			var viewport = input_viewport if input_viewport != null else game.get_viewport()
			viewport.push_input(event)
	previous_mask = mask

func nohit_observe():
	# Override with JSON-compatible values: soul coordinates/velocity/HP/KR,
	# mode and other important audit values. This is not a full world snapshot.
	return {}

func nohit_contract():
	return {"schema": "nohit.live.v1", "damage_audit": audit_connected,
		"input_bits": action_names, "observation": "game supplied JSON projection"}

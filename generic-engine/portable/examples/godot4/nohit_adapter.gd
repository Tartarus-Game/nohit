extends "res://addons/nohit_live/adapter_base.gd"

func nohit_begin(attack_seed):
	game.damaged.connect(record_damage)
	game.attack_finished.connect(mark_finished)
	enable_damage_audit() # Fixture has no KR system.
	game.start_attack(attack_seed)

func nohit_observe():
	return {"x": game.soul_position.x, "y": game.soul_position.y,
		"hp": game.hp, "attack_tick": game.tick}

extends "res://addons/nohit_live/adapter_base.gd"

func nohit_begin(attack_seed):
	game.connect("damaged", self, "record_damage")
	game.connect("attack_finished", self, "mark_finished")
	enable_damage_audit() # Fixture has no KR system.
	game.start_attack(attack_seed)

func nohit_observe():
	return {"x": game.soul_position.x, "y": game.soul_position.y,
		"hp": game.hp, "attack_tick": game.tick}

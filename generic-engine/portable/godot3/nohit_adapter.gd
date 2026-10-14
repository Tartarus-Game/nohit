extends "res://addons/nohit_live/adapter_base.gd"
## Edit only this file for your game. Keep the original soul and damage code.
## Replace example paths/signals below with your existing ones.
# var soul

func nohit_is_ready():
	return true # e.g. game.has_node("Battle/Soul")

func nohit_begin(_seed):
	# soul = game.get_node("Battle/Soul")
	# soul.connect("damaged", self, "record_damage")
	# soul.connect("kr_contact", self, "record_kr")
	# game.connect("attack_finished", self, "mark_finished")
	# enable_damage_audit()
	# game.start_attack(_seed)
	# Alternatively insert record_damage()/record_kr() calls in original entries.
	# Start all custom RandomNumberGenerator instances with _seed as well.
	pass

func nohit_observe():
	# return {"x": soul.position.x, "y": soul.position.y,
	#   "vx": soul.velocity.x, "vy": soul.velocity.y,
	#   "hp": soul.hp, "kr": soul.kr, "mode": soul.mode}
	return {} # Deliberately rejected until observations and audit are connected.

extends "res://Battle/Soul/soul.gd"
## Observe then delegate unchanged to original hurt/heal implementation.
func hurt(area: BulletArea) -> void:
	get_tree().call_group("nohit_audit", "on_damage", area)
	super.hurt(area)
func heal(area: BulletArea) -> void:
	get_tree().call_group("nohit_audit", "on_heal", area)
	super.heal(area)

func _exit_tree() -> void:
	# Upstream instantiates both mode nodes even when they are never parented.
	# Release those detached nodes only during teardown, after the audit ended.
	for node in ModeNodes.values():
		if is_instance_valid(node) and node.get_parent() == null:
			node.free()

extends Node
## Attach a game-owned host and its red/blue soul controller here.
## The host owns frame order, damage rules, world snapshots and completion.
@export var host_path: NodePath
@export var controller_script: Script
var host: Node
var controller: RefCounted

func configure(game_host: Node, soul_script: Script) -> void:
	host = game_host
	controller = soul_script.new()

func _ready() -> void:
	if not host_path.is_empty() and controller_script:
		configure(get_node(host_path), controller_script)

func validate() -> bool:
	if host == null or controller == null:
		return false
	for method in ["capture", "restore", "advance", "damage_count", "finished", "actions", "rank"]:
		if not host.has_method(method):
			push_error("NoHit host missing method: " + method)
			return false
	return controller.has_method("step")

func snapshot() -> Dictionary:
	# Contract: only detached Variant values; no shared mutable Nodes/Resources.
	return host.capture().duplicate(true)

func restore(state: Dictionary) -> void:
	host.restore(state.duplicate(true))

func step(mask: int, delta: float) -> void:
	host.advance(mask, delta, controller)

extends Node
## Insert this node below a configured bridge. Search is engine independent.
@export var bridge_path: NodePath
@export var width: int = 256
@export var max_ticks: int = 600
@export var seconds: float = 10.0
@export var delta: float = 1.0 / 60.0
signal completed(result: Dictionary)
const Solver = preload("res://addons/nohit/solver.gd")
func run_test() -> Dictionary:
	var bridge = get_node(bridge_path)
	var result: Dictionary = Solver.new().solve(bridge, width, max_ticks, seconds, delta)
	completed.emit(result)
	return result

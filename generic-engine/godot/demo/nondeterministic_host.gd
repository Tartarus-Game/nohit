extends "res://demo/host.gd"
var hidden_counter := 0
func advance(mask: int, delta: float, controller: RefCounted) -> void:
	super.advance(mask, delta, controller)
	hidden_counter += 1
	state["unrestored_rng_like_value"] = hidden_counter

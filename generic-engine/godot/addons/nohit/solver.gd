extends RefCounted
## Bounded search. No route = unknown. Full world state retained per branch.
func digest(state: Dictionary) -> String:
	var context := HashingContext.new()
	context.start(HashingContext.HASH_SHA256)
	context.update(var_to_bytes(state))
	return context.finish().hex_encode()

func solve(bridge: Node, width: int, max_ticks: int, seconds: float, delta: float) -> Dictionary:
	if width < 1 or max_ticks < 1 or seconds <= 0.0 or delta <= 0.0 or not bridge.validate():
		return {"status": "invalid_adapter"}
	var start_usec := Time.get_ticks_usec()
	var initial: Dictionary = bridge.snapshot()
	var initial_damage: int = bridge.host.damage_count()
	var records: Array = [{"parent": -1, "action": 0, "digest": digest(initial)}]
	var frontier: Array = [{"state": initial, "record": 0, "rank": 0.0}]
	var expanded := 0
	for tick in max_ticks:
		var next: Array = []
		var seen := {}
		for parent in frontier:
			bridge.restore(parent.state)
			for action in bridge.host.actions():
				if (Time.get_ticks_usec() - start_usec) / 1000000.0 >= seconds:
					bridge.restore(initial)
					return {"status": "unknown", "reason": "budget", "ticks": tick, "expanded": expanded}
				bridge.restore(parent.state)
				bridge.step(action, delta)
				expanded += 1
				if bridge.host.damage_count() != initial_damage:
					continue
				var state: Dictionary = bridge.snapshot()
				# Exact bytes dedup. Never quantize away hidden state or RNG.
				var key := var_to_bytes(state).hex_encode()
				if seen.has(key):
					continue
				seen[key] = true
				var record := records.size()
				records.append({"parent": parent.record, "action": action, "digest": digest(state)})
				if bridge.host.finished():
					var route: Array = []
					var digests: Array = []
					while record != 0:
						route.push_front(records[record].action)
						digests.push_front(records[record].digest)
						record = records[record].parent
					bridge.restore(initial)
					for i in route.size():
						bridge.step(route[i], delta)
						if bridge.host.damage_count() != initial_damage or digest(bridge.snapshot()) != digests[i]:
							bridge.restore(initial)
							return {"status": "replay_failed", "tick": i}
					var passed: bool = bridge.host.finished()
					bridge.restore(initial)
					return {"status": "verified_adapter_route" if passed else "replay_failed", "route": route,
						"ticks": route.size(), "expanded": expanded, "elapsed_ms": (Time.get_ticks_usec() - start_usec) / 1000.0,
						"verification": "same host full-state deterministic replay; independent real-game replay still required"}
				next.append({"state": state, "record": record, "rank": bridge.host.rank()})
		if next.is_empty():
			bridge.restore(initial)
			return {"status": "unknown", "reason": "frontier_exhausted", "ticks": tick, "expanded": expanded}
		next.sort_custom(func(a, b): return a.rank < b.rank)
		if next.size() > width:
			next.resize(width)
		frontier = next
	bridge.restore(initial)
	return {"status": "unknown", "reason": "horizon", "expanded": expanded}

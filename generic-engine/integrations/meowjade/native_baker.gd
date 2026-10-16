extends RefCounted
## Geometry only. Damage semantics and collision filters remain host-owned.
## No raster/polygon reimplementation: Shape2D.collide calls Godot physics.
static func capture(object: CollisionObject2D) -> Array:
	var out: Array = []
	for owner in object.get_shape_owners():
		if object.is_shape_owner_disabled(owner):
			continue
		var transform: Transform2D = object.global_transform * object.shape_owner_get_transform(owner)
		for i in object.shape_owner_get_shape_count(owner):
			out.append({"shape": object.shape_owner_get_shape(owner, i).duplicate(true), "transform": transform})
	return out

static func overlaps(player: Array, hazards: Array, offset: Vector2 = Vector2.ZERO) -> bool:
	for p in player:
		var transform: Transform2D = p.transform
		transform.origin += offset
		for h in hazards:
			if p.shape.collide(transform, h.shape, h.transform):
				return true
	return false

static func bake_samples(player: Array, hazards: Array, bounds: Rect2, spacing: float) -> Dictionary:
	assert(spacing > 0.0 and bounds.size.x > 0.0 and bounds.size.y > 0.0)
	var columns: int = int(ceil(bounds.size.x / spacing))
	var rows: int = int(ceil(bounds.size.y / spacing))
	var bits := PackedByteArray()
	bits.resize((columns * rows + 7) / 8)
	bits.fill(0)
	for y in rows:
		for x in columns:
			var i: int = y * columns + x
			if overlaps(player, hazards, bounds.position + Vector2(x, y) * spacing):
				bits[i >> 3] |= 1 << (i & 7)
	return {"columns": columns, "rows": rows, "spacing": spacing, "origin": bounds.position,
		"bits": bits, "meaning": "native overlap at sample points only; not a continuous free-space certificate"}

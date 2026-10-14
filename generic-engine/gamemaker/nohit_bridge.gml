/// Prototype for GMS2.3+. Not runtime-validated in this environment.
/// Call NoHitBake from the soul instance's context, after the game's collision phase.
/// classify(instance_id) returns caller-defined bit flags (white/blue/orange/solid).
/// This samples the LIVE engine masks; it does not simulate future frames.
function NoHitBake(_objects, _left, _top, _columns, _rows, _spacing, _classify) {
    if (_columns <= 0 || _rows <= 0 || _spacing <= 0) show_error("Invalid bake bounds", true);
    var _cells = array_create(_columns * _rows, 0);
    var _hits = ds_list_create();
    for (var _row = 0; _row < _rows; ++_row) {
        for (var _col = 0; _col < _columns; ++_col) {
            ds_list_clear(_hits);
            var _count = instance_place_list(_left + _col * _spacing, _top + _row * _spacing, _objects, _hits, false);
            var _flags = 0;
            for (var _i = 0; _i < _count; ++_i) _flags = _flags | _classify(_hits[| _i]);
            _cells[_row * _columns + _col] = _flags;
        }
    }
    ds_list_destroy(_hits);
    return {columns: _columns, rows: _rows, spacing: _spacing, left: _left, top: _top, cells: _cells,
        meaning: "native-mask sample points; not a continuous safe-space certificate"};
}

/// Route input query; connect to the game's OWN input abstraction.
function NoHitInput(_mask, _previous, _bit, _kind) {
    var _now = (_mask & _bit) != 0;
    var _before = (_previous & _bit) != 0;
    switch (_kind) {
        case "held": return _now;
        case "pressed": return _now && !_before;
        case "released": return !_now && _before;
    }
    return false;
}

/// Count all damage/KR contacts at the original health entry points.
/// Do not set HP, disable collision, or grant invulnerability for verification.
function NoHitAudit() constructor {
    damage_calls = 0;
    kr_contacts = 0;
    record_damage = function(_amount) { if (_amount >= 0) damage_calls += 1; };
    record_kr = function(_amount) { if (_amount > 0) kr_contacts += 1; };
    passed = function(_completed) { return _completed && damage_calls == 0 && kr_contacts == 0; };
}

/// GameMaker 2.3+ live bridge. Source template; no runtime acceptance yet.
/// NoHitLive.begin_step() must run once at the game's input boundary.
/// The NEXT boundary audits the completed native step, including End Step.
function NoHitLive(_adapter, _request, _output_path) constructor {
    adapter = _adapter;
    request = _request;
    output_path = _output_path;
    tick = 0;
    frames = [];
    route = [];
    initial = {};
    input_mask = 0;
    previous_mask = 0;
    damage_events = 0;
    kr_events = 0;
    audit_connected = false;
    attack_done = false;
    ending_ticks = -1;
    active = false;
    result = undefined;

    enable_damage_audit = function() { audit_connected = true; };
    record_damage = function() { damage_events += 1; };
    record_kr = function() { kr_events += 1; };
    mark_finished = function() { attack_done = true; };
    held = function(_bit) { return (input_mask & _bit) != 0; };
    pressed = function(_bit) { return held(_bit) && (previous_mask & _bit) == 0; };
    released = function(_bit) { return !held(_bit) && (previous_mask & _bit) != 0; };

    finish = function(_status) {
        active = false;
        result = {schema: "nohit.live.result.v1", status: _status,
            seed: request.seed, initial: initial, route: route, frames: frames,
            ticks: tick, attack_completed: attack_done,
            damage_events: damage_events, kr_events: kr_events,
            contract: {schema: "nohit.live.v1", damage_audit: audit_connected,
                observation: "game supplied JSON projection"},
            verification: "native steps; fresh process replay and damage control required"};
        var _file = file_text_open_write(output_path);
        file_text_write_string(_file, json_stringify(result));
        file_text_close(_file);
        show_debug_message("NOHIT_LIVE " + _status);
        // The game decides whether to game_end(); do not interrupt normal play.
    };

    start = function() {
        if (request.schema != "nohit.live.v1" || !is_array(request.route)
            || request.max_ticks < 1 || request.settle_ticks < 1) {
            finish("invalid_request");
            return;
        }
        random_set_seed(request.seed);
        adapter.begin(self, request.seed);
        initial = json_parse(json_stringify(adapter.observe()));
        if (!audit_connected || !is_struct(initial) || attack_done) {
            finish("invalid_adapter");
            return;
        }
        active = true;
    };

    begin_step = function() {
        if (!active) return;
        if (tick > 0) {
            var _state = json_parse(json_stringify(adapter.observe()));
            array_push(frames, {tick: tick, state: _state,
                damage_events: damage_events, kr_events: kr_events, finished: attack_done});
            if (damage_events > 0 || kr_events > 0) { finish("hit"); return; }
            if (attack_done) {
                if (ending_ticks < 0) ending_ticks = 0;
                ending_ticks += 1;
                if (ending_ticks > request.settle_ticks) { finish("native_route_candidate"); return; }
            }
        }
        if (tick >= request.max_ticks) { finish("unknown"); return; }
        previous_mask = input_mask;
        input_mask = 0;
        var _length = array_length(request.route);
        if (tick < _length) input_mask = request.route[tick];
        else if (request.repeat_last && _length > 0) input_mask = request.route[_length - 1];
        array_push(route, input_mask);
        tick += 1;
    };
}

/// Replace calls in the game's OWN input abstraction, preserving normal input.
function NoHitHeld(_bit, _normal_input) {
    if (variable_global_exists("nohit") && is_struct(global.nohit) && global.nohit.active)
        return global.nohit.held(_bit);
    return _normal_input;
}
function NoHitPressed(_bit, _normal_input) {
    if (variable_global_exists("nohit") && is_struct(global.nohit) && global.nohit.active)
        return global.nohit.pressed(_bit);
    return _normal_input;
}
function NoHitReleased(_bit, _normal_input) {
    if (variable_global_exists("nohit") && is_struct(global.nohit) && global.nohit.active)
        return global.nohit.released(_bit);
    return _normal_input;
}

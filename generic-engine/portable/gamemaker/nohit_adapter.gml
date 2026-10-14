/// Replace placeholders with your existing objects, damage and attack hooks.
/// This does NOT replace any soul movement, collision or color damage rules.
function MyNoHitAdapter() constructor {
    begin = function(_session, _seed) {
        // Hook ALL original damage/KR entry points and attack-end event first.
        // _session.enable_damage_audit();
        // start_my_attack(_seed);
    };
    observe = function() {
        // return {x: obj_soul.x, y: obj_soul.y, hp: global.hp,
        //   kr: global.kr, mode: obj_soul.mode, velocity_y: obj_soul.vspeed};
        return {}; // Fill with real, JSON-compatible values.
    };
}

/// In the test controller's Create event (only in an explicit test build):
/// global.nohit = new NoHitLive(new MyNoHitAdapter(), request, "nohit-result.json");
/// global.nohit.start();
///
/// At your existing input boundary, before soul movement, once per step:
/// if (variable_global_exists("nohit")) global.nohit.begin_step();
///
/// In the ORIGINAL damage function, leave original damage logic intact:
/// if (variable_global_exists("nohit")) global.nohit.record_damage();
/// KR entry: global.nohit.record_kr(); attack-end: global.nohit.mark_finished();
///
/// In the original input wrapper, retain pressed/released semantics:
/// jump = NoHitPressed(4, keyboard_check_pressed(vk_up));
/// left = NoHitHeld(1, keyboard_check(vk_left));

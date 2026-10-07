"""Fail-closed, independent verifier for saved automatic CSV native evidence.

Input: {controller: __CSV_TAS, observer: __CUSTOM_WAVE,
        finalSnapshot: __CUSTOM_WAVE.capture(), source?: __CSV_SOURCE,
        clock?: __TAS_CLOCK}. JSON serialization omits functions.

The controller's completed flag alone never establishes success. EndAttack
retains its separately verified native menu reset. EOF instead checks every
finite state and independently observed, source-bound fixed-point closure under
permanent neutral input. Neither result covers other RNG seeds or authenticates
the process that produced the JSON.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path

DT = 1 / 30
STATE_FIELDS = ('x', 'y', 'dx', 'dy', 'keymask', 'slammed', 'mode',
                'direction', 'max_fall', 'slam_damage', 'damage')
TICK_FIELDS = ('tick', 'HP', 'KR', 'SimulatorMode', 'keymask', 'confirm',
               'line', 'T', 'running', 'pendingCount')
SHARED_EVENTS = {'tlplay', 'tlpause', 'tlresume', 'endattack', 'damageplayer'}
PLATFORM_SIDS = {1226268899238104, 6981383464931416}
EOF_SOURCE_HASHES = {
    'c2runtime.js': '664b5d93dbd5159976d490663ac64c49c8eb7dc68c9aac92fba940b6fa2a3de9',
    'data.js': '9f70e7179fe4260002321a75e5170e96583439bb39988b92ed93da42a0a402c7',
}
# Match JSON.parse/JSON.stringify in the original JavaScript runtime. Above
# 2**53, source integer spellings can differ from native binary64 identities.
EOF_FAMILIES = {
    9590353435551898: {3019589746608161, 6503092777075739, 8140934880742138,
                     4163262150020477, 3868174782291034, *PLATFORM_SIDS},
    6631597198329078: {7974524067202295, 761861833921609, 5246535965326995},
    9784977049754560: {165116925986465},
}
EOF_ATTACK_TYPES = {3019589746608161, 3868174782291034, 9836012384209520,
    7974524067202295, 8140934880742138, 6503092777075739, 4163262150020477,
    336730486351203, 508841962091807, 165116925986465}.union(*EOF_FAMILIES.values())
EOF_RPG_TYPES = {6163397057824361, 501546311307215, 1422059525027614, 5575857119740264}
EOF_OWNED_KEYS = {37, 38, 39, 40, 65, 68, 83, 87, 88, 16, 90, 13}
EOF_CALLBACK_CONTRACT = 'original-custom-empty-eof-v1'


def finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def integer(value):
    return type(value) is int


def vector(value, length):
    return isinstance(value, list) and len(value) == length and all(map(finite, value))


def verify_eof_completion(require, completion, plan, observer, final, controller_rows,
                          raw, start, actions, confirms, trajectory):
    """Independent source-bound sufficient closure; never call a model certifier.

    Pinned original event data supplies the exhaustive spawn/callback inventory.
    Native observations establish quiescent callbacks and the actual physical release.
    The final analytic fixed point concerns player/arena/inputs, not Timeline T.
    This verifies saved evidence, not authenticity of the producing process.
    """
    def obj(value, code):
        return value if require(isinstance(value, dict), code, 'Missing native EOF object') else {}

    def indexed(value, ids, code):
        valid = isinstance(value, list) and all(isinstance(v, dict) and integer(v.get('sid')) for v in value)
        valid = valid and len(value) == len(ids) and {v['sid'] for v in value} == ids
        require(valid, code, 'Incomplete or duplicate source-bound type/family inventory')
        return {v['sid']: v for v in value} if valid else {}

    def released_keys(value):
        return (isinstance(value, list) and len(value) == len(EOF_OWNED_KEYS)
                and all(isinstance(v, dict) and integer(v.get('code')) and v.get('pressed') is False for v in value)
                and {v['code'] for v in value} == EOF_OWNED_KEYS)

    def passive_ui(value):
        # RPGText.xml:13 increments T unconditionally. Empty FullText/EndFunc,
        # Interactive=0 and Timeout=0 close typing, input, destruction and its
        # callback (:21, :68, :117, :154). Original BattleFont has no private
        # variables: all eight native vars are the RPGText family fields.
        valid = isinstance(value, list) and len(value) == 3
        identities = {}
        names = set()
        if valid:
            for row in value:
                if not isinstance(row, dict):
                    valid = False
                    break
                fields = row.get('fields')
                valid = (integer(row.get('uid')) and row['uid'] >= 0
                    and integer(row.get('typeSid')) and row['typeSid'] == 6163397057824361
                    and integer(row.get('familyOffset')) and row['familyOffset'] == 0
                    and isinstance(fields, list) and len(fields) == 8
                    and isinstance(fields[0], str) and fields[0] in {'HP', 'PlayerName', 'QuitMessage'}
                    and fields[1:4] == ['', '', '']
                    and all(finite(fields[i]) and fields[i] == 0 for i in (4, 5, 7))
                    and finite(fields[6]) and fields[6] >= 0
                    and isinstance(row.get('vars'), list) and row['vars'] == fields
                    and all(finite(row['vars'][i]) for i in (4, 5, 6, 7)))
                if not valid:
                    break
                identities[row['uid']] = tuple(fields[:6] + fields[7:])
                names.add(fields[0])
        valid = valid and len(identities) == 3 and names == {'HP', 'PlayerName', 'QuitMessage'}
        require(valid, 'eof_dialogue', 'Only the three original passive UI texts with empty callback fields may remain')
        return identities if valid else None

    n = len(actions)
    e, d = completion.get('eof_tick'), completion.get('drain_tick')
    valid_ticks = require(integer(start) and integer(e) and integer(d) and 0 <= e <= d <= n - 2
        and all(integer(completion.get(k)) for k in ('tick', 'release_start_tick', 'release_tick_count'))
        and completion.get('tick') == plan.get('reached_tick') == n
        and completion.get('release_start_tick') == d + 1
        and completion.get('release_tick_count') == n - d,
        'eof_completion_ticks', 'EOF/drain/release boundaries must name at least two executed neutral ticks')
    require(plan.get('termination_policy') == 'eof_hazards_drained',
            'eof_policy', 'EOF requires the explicit Custom EOF policy')
    require(valid_ticks and confirms[d:] == [False] * (n-d) and actions[d:] == [0] * (n-d),
            'eof_release_controls', 'The public physical schedule must already contain the entire neutral bridge')
    certificate = obj(completion.get('certificate'), 'eof_certificate')
    require(certificate.get('status') == 'proven'
            and certificate.get('proof') == 'static-empty-release-fixed-point-v1'
            and integer(certificate.get('policy_mask')) and certificate['policy_mask'] == 0
            and certificate.get('policy_confirm') is False,
            'eof_certificate', 'Unsupported model completion certificate')
    details = obj(certificate.get('terminal_details'), 'eof_certificate_details')
    require(details.get('timeline_exhausted') is True and details.get('pending_callbacks') == []
            and 'pending_dialogue' in details and details['pending_dialogue'] is None
            and details.get('arena_settled') is True and 'end_resize' in details and details['end_resize'] is None
            and isinstance(details.get('initial_callback_contract'), str)
            and all(integer(details.get(k)) and details[k] == 0 for k in
                    ('active_bones', 'active_stabs', 'active_blasters', 'active_platforms')),
            'eof_certificate_details', 'Model terminal obligations are incomplete')
    facts = obj(observer.get('eofTerminal'), 'eof_native_facts')
    drain = obj(facts.get('drain_snapshot'), 'eof_drain_snapshot')
    width = obj(facts.get('timeline'), 'eof_timeline').get('width')
    width_ok = integer(width) and width > 0
    eof_snapshot = obj(observer.get('eofSnapshot'), 'eof_observation')
    first_eof = next((i for i, row in enumerate(raw) if width_ok and integer(row[6]) and row[6] > width), None)
    require(valid_ticks and width_ok and first_eof == e and observer.get('eofObserved') is True
            and eof_snapshot.get('tick') == start + e and eof_snapshot.get('lineCount') == width
            and eof_snapshot.get('line') == raw[e][6],
            'eof_observation', 'First native EOF must agree with E and the observed Timeline width')

    def physical_record(value, relative, code):
        physical = obj(value, code)
        row = controller_rows[relative] if integer(relative) and 0 <= relative < len(controller_rows) else {}
        env = physical.get('initial_environment')
        valid = require(physical.get('tick') == row.get('tick') == start + relative
            and physical.get('initial') == row.get('state') and vector(physical.get('initial'), 11)
            and physical.get('dt') == row.get('dt') and physical.get('clock_start_ms') == row.get('clock_start_ms')
            and finite(physical.get('time')) and physical['time'] == row.get('time')
            and physical.get('running') == row.get('running') and physical.get('timeline') == row.get('T')
            and physical.get('vpad') == row.get('vpad') and vector(physical.get('vpad'), 14)
            and physical.get('HP') == 92 and physical.get('KR') == 0
            and physical.get('SimulatorMode') == 2 and physical.get('SingleAttack') == 'custom'
            and vector(env, 22), code, 'Independent physical state/clock/latches do not match the actual posttick')
        if valid:
            state = physical['initial']
            require(env[4:6] == state[6:8] and env[8] == state[8] and env[12] == state[9]
                    and env[7] == physical['dt'], code, 'Native physical environment disagrees with state')
        return physical

    def closed_native(value, relative, terminal):
        physical = physical_record(value.get('physical'), relative, 'eof_physical')
        require(integer(value.get('schema_version')) and value['schema_version'] == 1 and value.get('capture_phase') == 'posttick'
                and value.get('tick') == start + relative, 'eof_native_schema', 'Unsupported native EOF phase/schema')
        require(value.get('source_sha256') == EOF_SOURCE_HASHES
                and value.get('callback_contract') == EOF_CALLBACK_CONTRACT,
                'eof_source_contract', 'Native callback/geometry inventory is not bound to the audited original export')
        timeline = obj(value.get('timeline'), 'eof_timeline')
        native_row = raw[relative] if 0 <= relative < len(raw) else None
        require(width_ok and timeline.get('width') == width and timeline.get('width_field') == 'ra'
                and timeline.get('list_sid') == 456555951765879 and native_row is not None
                and integer(timeline.get('line')) and timeline['line'] > width
                and timeline['line'] == physical.get('line') == native_row[6] and native_row[9] == 0,
                'eof_timeline', 'Timeline is not natively exhausted with an empty entity inventory')
        families = indexed(value.get('attack_families'), set(EOF_FAMILIES), 'eof_attack_families')
        for sid, row in families.items():
            members = row.get('members')
            require(isinstance(members, list) and all(integer(v) for v in members)
                    and len(members) == len(EOF_FAMILIES[sid]) and set(members) == EOF_FAMILIES[sid],
                    'eof_attack_families', 'Original attack-family membership is incomplete')
        types = indexed(value.get('attack_types'), EOF_ATTACK_TYPES, 'eof_attack_types')
        require(bool(types) and all(integer(t.get('count')) and t['count'] == 0 for t in types.values()),
                'eof_active_entities', 'Native heads/warnings/beams/bones/platforms must all be absent')
        rpg = obj(value.get('rpgtext_family'), 'eof_dialogue')
        members = rpg.get('members')
        require(rpg.get('sid') == 8627438680975019 and isinstance(members, list)
                and all(integer(v) for v in members) and len(members) == len(EOF_RPG_TYPES)
                and set(members) == EOF_RPG_TYPES, 'eof_dialogue', 'Original RPGText family membership is missing')
        rpg_types = indexed(value.get('rpgtext_types'), EOF_RPG_TYPES, 'eof_dialogue')
        require(value.get('rpgtext_policy') == 'original-passive-ui-v1' and bool(rpg_types)
                and all(integer(t.get('count')) and t['count'] == (3 if sid == 6163397057824361 else 0)
                        for sid, t in rpg_types.items()),
                'eof_dialogue', 'Native RPGText counts must contain only the three original passive UI instances')
        ui_identities = passive_ui(physical.get('rpgtext'))
        wait = obj(value.get('wait_queue'), 'eof_wait_queue')
        require(wait.get('field') == 'Hd.fc' and wait.get('is_array') is True
                and integer(wait.get('length')) and wait['length'] == 0 and wait.get('entries') == [],
                'eof_wait_queue', 'Original System Wait queue is not explicitly observed as a typed empty array')
        pending = obj(value.get('pending_layout'), 'eof_layout')
        require(pending.get('field') == 'ih' and pending.get('present') is True
                and 'value' in pending and pending['value'] is None and value.get('loading') is False
                and value.get('layout') == {'sid': 8667945925241823, 'name': 'BattleScreen'}
                and value.get('globals') == {'SimulatorMode': 2, 'SingleAttack': 'custom'}
                and value.get('menu_state') == {'sid': 5359025861573384, 'value': 0},
                'eof_layout', 'Native Custom combat/layout/menu continuation is not closed')
        env = physical.get('initial_environment')
        arena = obj(physical.get('arena'), 'eof_arena')
        if vector(env, 22):
            require(arena.get('target') == env[:4] and arena.get('callback') == ''
                    and finite(arena.get('speed')) and arena.get('size') == [env[2]-env[0], env[3]-env[1]],
                    'eof_arena', 'Native arena or EndResize callback is not settled')
            if terminal:
                require(env[6] == env[9] == env[13] == 0 and env[:4] == env[14:18] == env[18:22],
                        'eof_environment', 'One-shot pulses or changing arena phases remain')
        return physical, ui_identities

    if not valid_ticks or not integer(start):
        return {'proof': None, 'verified': False}
    _, drain_ui = closed_native(drain, d, False)
    physical, terminal_ui = closed_native(facts, n, True)
    require(drain_ui is not None and terminal_ui == drain_ui,
            'eof_dialogue_identity', 'Original passive UI identities and all fields except their clocks must persist from D to N')
    require(released_keys(facts.get('owned_keys')) and physical.get('vpad') == [0] * 14
            and physical.get('physical_keymask') == 0 and physical.get('physical_confirm') is False
            and physical.get('initial_confirm') is False and physical.get('previous_confirm') is False,
            'eof_inputs', 'All owned keyboard keys and all fourteen current/previous VPad fields must be released')
    release = facts.get('release_snapshots')
    if require(isinstance(release, list) and len(release) == 2 and all(isinstance(v, dict) for v in release),
               'eof_release_observation', 'Two actual final neutral posttick snapshots are required'):
        for i, observed in zip((n-1, n), release):
            actual = physical_record(observed.get('physical'), i, 'eof_release_observation')
            pad = actual.get('vpad')
            require(released_keys(observed.get('owned_keys')) and vector(pad, 14) and pad[:7] == [0] * 7
                    and actual.get('physical_keymask') == 0 and actual.get('physical_confirm') is False,
                    'eof_release_observation', 'A final release tick still sampled an owned input')
        require(release[-1].get('physical') == facts.get('physical'),
                'eof_release_observation', 'Final independent release snapshot is not the certified posttick')
    state, env = physical.get('initial'), physical.get('initial_environment')
    expected_env = certificate.get('static_environment')
    require(vector(state, 11) and state == final.get('state') == certificate.get('invariant_state')
            and bool(trajectory) and state == trajectory[-1],
            'eof_endpoint', 'Every final native state component must exactly equal the executed endpoint and certificate')
    env_ok = vector(env, 22) and vector(expected_env, 22)
    require(env_ok and 0 < expected_env[7] <= DT and env[9] == expected_env[9] == 0
            and all(env[k] == expected_env[k] for k in range(22) if k not in (7, 10, 11)),
            'eof_environment', 'Native and model stationary environments differ; only dt and inactive teleport coordinates may differ')
    require(final.get('pending') == [], 'eof_active_entities', 'Final native pending objects are not empty')
    if not vector(state, 11) or not env_ok:
        return {'proof': None, 'verified': False}
    l, t, r, b = env[:4]
    native_arena = obj(physical.get('arena'), 'eof_arena')
    require(final.get('arena') == env[:4] and final.get('arenaTarget') == env[:4]
            and final.get('resizeSpeed') == native_arena.get('speed')
            and final.get('endResize') == '', 'eof_arena', 'Final independent arena snapshots disagree')
    require(state[2:5] == [0, 0, 0] and state[5] in (0, 1) and state[6] in (0, 1)
            and state[7] in (0, 1, 2, 3) and state[8] >= 0 and state[9:11] == [0, 0]
            and r-l >= 26 and b-t >= 26 and l+13 <= state[0] <= r-13 and t+13 <= state[1] <= b-13,
            'eof_fixed_point', 'Native player is moving, damaged, outside the unchanged clamp or has unsupported state')
    heart = obj(facts.get('heart_geometry'), 'eof_geometry')
    square = [state[0]-8, state[1]-8, state[0]+8, state[1]+8]
    require(heart.get('typeSid') == 5960708907117077 and integer(heart.get('uid'))
            and heart.get('x') == state[0] and heart.get('y') == state[1]
            and heart.get('width') == heart.get('height') == 16 and heart.get('bbox') == square
            and heart.get('angle') == state[7] * (math.pi/2) and heart.get('collisions_enabled') is True
            # Exported collision_poly.hr is already relative to the .5 hotspot,
            # unlike the caproj's 0..1 polygon coordinates.
            and heart.get('collision_polygon') in ([-.5, .5, -.5, -.5, .5, -.5, .5, .5],
                                                   [.5, .5, -.5, .5, -.5, -.5, .5, -.5]),
            'eof_geometry', 'Native heart must retain the audited full-square collision geometry')
    borders = facts.get('borders')
    expected_boxes = [[l,t,r,t+5], [l,t,l+5,b], [l,b-5,r,b], [r-5,t,r,b]]
    borders_ok = isinstance(borders, list) and len(borders) == 4 and all(isinstance(v, dict) for v in borders)
    if require(borders_ok, 'eof_geometry', 'All four native finite borders must be observed'):
        require(len({v.get('uid') for v in borders if integer(v.get('uid'))}) == 4,
                'eof_geometry', 'Border identities are missing or duplicated')
        for border, box in zip(borders, expected_boxes):
            require(border.get('typeSid') == 6657741784745805 and border.get('bbox') == box
                    and border.get('collisions_enabled') is True
                    and 'collision_polygon' in border and border['collision_polygon'] is None
                    and border.get('angle') == 0 and border.get('x') == box[0] and border.get('y') == box[1]
                    and border.get('width') == box[2]-box[0] and border.get('height') == box[3]-box[1],
                    'eof_geometry', 'Native finite-border geometry differs from the audited stationary arena')
    if state[6] == 1:
        # Sufficient native subset: downward blue, strictly positive overlap
        # at the original .2 gravity probe with the observed bottom border.
        require(state[7] == 1 and borders_ok and min(state[0]+8, r)-max(state[0]-8, l) > 1e-7
                and min(state[1]+8+.2, b)-max(state[1]-8+.2, b-5) > 1e-7,
                'eof_blue_support', 'Native downward border support is unproven; other blue directions are unsupported')
    return {'proof': 'original-native-static-empty-release-v1', 'source_sha256': EOF_SOURCE_HASHES,
            'eof_tick': e, 'drain_tick': d, 'release_ticks': n-d,
            'mode': 'red' if state[6] == 0 else 'blue_down_border', 'input_policy': 'all_owned_keys_released',
            'rpgtext_policy': 'original-passive-ui-v1'}


def derive_menu_velocity(previous, mask, dt, mode, arena=None):
    """Original Battle.xml's final input phase, after EndAttack/ResetVars.

    MenuState=1 places the heart at the button (2686) before PlayerMovement
    (3034). HeartMode preserves mode and sets angle=90 without clearing speed
    (485, 3074, 3107). Disabling CustomMovement does not disable these events.
    Blue mode is supported only with independently established empty platform
    geometry and a stable arena: the caller establishes those two facts; this
    function proves the final behavior sweep and menu solid probes are clear.
    No active-battle operator or model endpoint velocity is used here.
    """
    if not (vector(previous, 11) and integer(mask) and 0 <= mask < 16
            and finite(dt) and 0 < dt <= DT and mode in (0, 1)):
        raise ValueError('Invalid terminal velocity inputs')
    dx = 150 * (int(bool(mask & 2)) - int(bool(mask & 1)))
    if mode == 0:
        return dict(rule='original_red_menu_input', expected=[dx, 150 * (
            int(bool(mask & 8)) - int(bool(mask & 4)))])
    if not vector(arena, 4):
        raise ValueError('Blue menu transition requires an independently observed stable arena')
    x, y, vx, vy = previous[:4]
    l, t, r, b = arena
    # A strictly interior swept 16x16 heart cannot hit any of the four finite
    # 5px borders during horizontal/vertical CustomMovement substeps. This is
    # deliberately conservative; contact cases require a different proof.
    # Reject near-contact cases as well: cardinal-angle trig residuals and
    # native substep arithmetic can move a bbox by a few binary64 ULPs.
    clearance = 13 + 1e-7
    if not (l + clearance < min(x, x + vx*dt) <= max(x, x + vx*dt) < r - clearance
            and t + clearance < min(y, y + vy*dt) <= max(y, y + vy*dt) < b - clearance):
        raise ValueError('Final behavior sweep is not proven free of border contact')
    # Both downward probes (0.2 for gravity, 1 for a new Up press) are below
    # the finite borders at the original menu y=453. EndAttack destroys every
    # Attack9Patch member, including Platform1/2, before these probes.
    if not b < 453 - 8 - 1e-7:
        raise ValueError('Menu jump/gravity probes are not proven free of border contact')
    incoming_dy = vy
    released_up = bool(int(previous[4]) & 4) and not bool(mask & 4)
    if released_up and vy < -30:  # Battle.xml 3903-3920
        vy = -30
    # Local Gravity resets to zero each event invocation (3822); at >=240 no
    # branch assigns it. The remaining branches are 4054-4123.
    gravity = 0 if vy >= 240 else 540 if vy > 15 else 180 if vy > -30 else 450 if vy > -120 else 180
    final_dy = min(vy + gravity*dt, 750)
    return dict(rule='original_blue_menu_clear_sweep', expected=[dx, final_dy],
                incoming_dy=incoming_dy, released_up=released_up,
                gravity=gravity, dt=dt, reset_direction=1, arena=arena)


def verify_endattack_snapshots(require, event, final, previous_row, final_row, source_text):
    """Validate native before/after the direct Timeline EndAttack call.

    The before observation is after this tick's CustomMovement behavior, so
    platforms may have affected it. No model endpoint velocity is consulted.
    A third observation at PlayerMovement entry independently establishes the
    completed menu placement and deferred platform deletion before input.
    """
    code = 'terminal_native_snapshots'
    def obj(value):
        if require(isinstance(value, dict), code, 'Missing native EndAttack snapshot object'):
            return value
        return {}
    snapshots = obj(event.get('snapshots'))
    before, after = obj(snapshots.get('before')), obj(snapshots.get('after'))
    movement = obj(snapshots.get('before_movement'))
    pre, post = obj(before.get('physical')), obj(after.get('physical'))
    ready = obj(movement.get('physical'))
    caller = obj(snapshots.get('caller'))
    source_line = snapshots.get('source_line')
    lines = source_text.split('\n') if isinstance(source_text, str) else []
    source_ok = integer(source_line) and 1 <= source_line <= len(lines)
    source_row = lines[source_line-1] if source_ok else None
    loaded = caller.get('loaded_line')
    parameters = caller.get('action_parameters')
    loaded_args = [loaded[i] if i < len(loaded) else 0 for i in range(2,11)] if isinstance(loaded,list) else None
    require(snapshots.get('schema_version') == 1 and integer(snapshots.get('schema_version'))
            and snapshots.get('source') == 'timeline'
            and snapshots.get('error') is None
            and snapshots.get('source_sha256') == EOF_SOURCE_HASHES,
            code, 'EndAttack snapshots are not bound to the audited original source')
    require(source_ok and caller.get('source_line') == source_line
            and caller.get('raw_source_line') == source_row
            and len(source_row.split(',')) >= 2 and source_row.split(',')[1].strip().lower() == 'endattack'
            and all(not row.strip() for row in lines[source_line:])
            and caller.get('sheet') == 'Timeline' and caller.get('event_sid') == 441595194418922
            and caller.get('action_sid') == 9188948149072352
            and integer(caller.get('action_index')) and caller['action_index'] == 0
            and caller.get('loaded_line_sid') == 3081225054711249
            and isinstance(loaded, list) and len(loaded) == len(source_row.split(',')) and len(loaded) >= 2
            and isinstance(loaded[1], str) and loaded[1].lower() == 'endattack'
            and isinstance(parameters, list) and len(parameters) == 2
            and isinstance(parameters[0], str) and parameters[0].lower() == 'endattack'
            and parameters[1] == loaded_args == event.get('args'),
            code, 'Expected the actual final source line and native Timeline dispatch event/action')
    require(movement.get('event_sid') == 6451037740410459 and movement.get('sheet') == 'Battle'
            and movement.get('group_name') == 'playermovement',
            code, 'Missing the actual original PlayerMovement group-entry observation')
    states = []
    for record, physical, phase in ((before, pre, 'before_native_endattack'),
                                    (after, post, 'after_native_endattack'),
                                    (movement, ready, 'before_native_player_movement')):
        state, env, pad = physical.get('initial'), physical.get('initial_environment'), physical.get('vpad')
        good = require(record.get('capture_phase') == phase and integer(final_row.get('tick'))
            and physical.get('tick') == event.get('tick')
            and physical.get('tick') == final_row.get('tick', -1)-1
            and physical.get('time') == final_row.get('time')
            and physical.get('dt') == final_row.get('dt') and finite(physical.get('dt'))
            and physical.get('clock_start_ms') == final_row.get('clock_start_ms')
            and physical.get('HP') == 92 and physical.get('KR') == 0
            and physical.get('SimulatorMode') == 2 and physical.get('SingleAttack') == 'custom'
            and physical.get('line') == (final_row.get('line') if record is movement else source_line)
            and physical.get('running') == 1
            and finite(physical.get('timeline')) and vector(state, 11) and vector(env, 22)
            and vector(pad, 14) and pad == final_row.get('vpad'),
            code, 'Native trigger state, physical clock, inputs or health is incomplete')
        if not good:
            states.append(None)
            continue
        states.append(state)
        require(state[4] == final_row.get('mask') and physical.get('physical_keymask') == state[4]
            and physical.get('initial_confirm') is final_row.get('confirm')
            and physical.get('physical_confirm') is final_row.get('confirm')
            and physical.get('previous_confirm') is bool(pad[11])
            and bool(pad[7]) == bool(int(previous_row['state'][4]) & 4)
            and env[4:6] == state[6:8] and env[7:9] == [physical['dt'], state[8]] and env[12] == state[9],
            code, 'Native trigger latches or environment disagree with the actual public input')
        arena = obj(physical.get('arena'))
        require(arena.get('size') == [env[2]-env[0], env[3]-env[1]]
            and vector(arena.get('target'), 4) and finite(arena.get('speed'))
            and isinstance(arena.get('callback'), str), code, 'Native trigger arena is incomplete')
        heart = obj(record.get('heart_geometry'))
        require(heart.get('typeSid') == 5960708907117077 and integer(heart.get('uid'))
            and heart.get('x') == state[0] and heart.get('y') == state[1]
            and heart.get('width') == heart.get('height') == 16
            and heart.get('angle') == state[7] * (math.pi/2)
            and heart.get('bbox') == [state[0]-8,state[1]-8,state[0]+8,state[1]+8]
            and heart.get('collisions_enabled') is True
            and heart.get('collision_polygon') in ([-.5,.5,-.5,-.5,.5,-.5,.5,.5],
                                                   [.5,.5,-.5,.5,-.5,-.5,.5,-.5]),
            code, 'Native trigger heart does not have the audited collision square')
        borders = record.get('borders')
        l,t,r,b = env[:4]
        boxes = [[l,t,r,t+5],[l,t,l+5,b],[l,b-5,r,b],[r-5,t,r,b]]
        border_ok = isinstance(borders, list) and len(borders) == 4 and all(isinstance(v, dict) for v in borders)
        if require(border_ok, code, 'All four native trigger borders are required'):
            require(len({v.get('uid') for v in borders if integer(v.get('uid'))}) == 4,
                    code, 'Native trigger border identities are incomplete')
            for border,box in zip(borders,boxes):
                require(border.get('typeSid') == 6657741784745805 and border.get('bbox') == box
                    and border.get('x') == box[0] and border.get('y') == box[1]
                    and border.get('width') == box[2]-box[0] and border.get('height') == box[3]-box[1]
                    and border.get('angle') == 0 and border.get('collisions_enabled') is True
                    and 'collision_polygon' in border and border['collision_polygon'] is None,
                    code, 'Native trigger border geometry is not the audited finite rectangle')
        platforms = record.get('platforms')
        platform_ok = isinstance(platforms, list) and all(isinstance(v, dict) for v in platforms)
        if require(platform_ok, code, 'Native trigger platform inventory is missing'):
            require(len({v.get('uid') for v in platforms if integer(v.get('uid'))}) == len(platforms),
                    code, 'Native trigger platform identities are duplicated')
            for platform in platforms:
                require(platform.get('typeSid') in PLATFORM_SIDS and integer(platform.get('uid'))
                    and vector(platform.get('bbox'),4) and isinstance(platform.get('vars'),list)
                    and all(finite(platform.get(k)) for k in ('x','y','width','height','angle'))
                    and type(platform.get('collisions_enabled')) is bool
                    and 'collision_polygon' in platform,
                    code, 'Native trigger platform geometry/variables are incomplete')
    if any(state is None for state in states):
        return None
    a,z,m = states
    expected = a.copy()
    expected[7:10] = [1,750,0]
    require(z == expected and z[6] == final['state'][6]
            and a[10] == z[10] == 0 and z[5] == final['state'][5]
            and pre.get('timeline') == post.get('timeline')
            and pre['initial_environment'][:4] == post['initial_environment'][:4]
            and before.get('borders') == after.get('borders')
            and obj(before.get('heart_geometry')).get('uid') == obj(after.get('heart_geometry')).get('uid')
            and post.get('arena') == dict(target=[33,251,608,391],size=obj(pre.get('arena')).get('size'),speed=480,callback='MenuBattle'),
            code, 'EndAttack must preserve native position/velocity and apply only audited resets')
    # Original runtime c2runtime.js:131 queues destruction and removes from
    # type/family lists in Gb/ps. Trigger return at :148 need not flush during
    # event-sheet execution; top-level Av at :227 does. Never pretend that the
    # immediate after-call inventory is empty: observe actual deletion at the
    # later, independent PlayerMovement group entry.
    prior_platforms = before.get('platforms')
    remaining_platforms = after.get('platforms')
    residue_ok = isinstance(prior_platforms,list) and isinstance(remaining_platforms,list)
    if residue_ok:
        residue_ok = all(isinstance(row,dict) and row in prior_platforms for row in remaining_platforms)
    expected_ready = z.copy();expected_ready[:2] = final['state'][:2]
    require(residue_ok and movement.get('platforms') == [] and m == expected_ready
            and ready.get('timeline') == final_row.get('T')
            and ready.get('arena') == post.get('arena')
            and ready['initial_environment'] == post['initial_environment']
            and movement.get('borders') == after.get('borders')
            and obj(movement.get('heart_geometry')).get('uid') == obj(after.get('heart_geometry')).get('uid')
            and abs(m[0]-48) <= 1e-5 and m[1] == 453,
            code, 'PlayerMovement entry must observe actual platform deletion, original menu position and preserved velocity')
    # The menu placement runs before PlayerMovement. Both the .2 gravity probe
    # and the 1px jump probe are vertically disjoint from all observed borders.
    require(post['initial_environment'][3] < 453-8-1e-7,
            code, 'Native borders do not prove clear menu jump/gravity probes')
    return m


def derive_observed_menu_velocity(before, previous_mask, mask, dt):
    """Original post-EndAttack input phase, starting after native behavior."""
    dx = 150 * (int(bool(mask & 2)) - int(bool(mask & 1)))
    if before[6] == 0:
        return dict(rule='original_red_menu_input_from_native_trigger',
                    expected=[dx,150*(int(bool(mask&8))-int(bool(mask&4)))])
    vy = before[3]
    released_up = bool(previous_mask&4) and not bool(mask&4)
    if released_up and vy < -30:
        vy = -30
    gravity = 0 if vy>=240 else 540 if vy>15 else 180 if vy>-30 else 450 if vy>-120 else 180
    return dict(rule='original_blue_menu_input_from_native_trigger',expected=[dx,min(vy+gravity*dt,750)],
                incoming_dy=before[3],released_up=released_up,gravity=gravity,dt=dt,reset_direction=1)


def verify_record(data):
    errors = []
    def require(ok, code, detail):
        if not ok:
            errors.append({'code': code, 'detail': detail})
        return bool(ok)

    def obj(value, label):
        return value if require(isinstance(value, dict), 'object_schema', label) else {}

    def rows(value, label):
        return value if require(isinstance(value, list) and all(isinstance(x, dict) for x in value),
                                'rows_schema', label) else []

    data = obj(data, 'record')
    c = obj(data.get('controller'), 'controller')
    o = obj(data.get('observer'), 'observer')
    final = obj(data.get('finalSnapshot'), 'finalSnapshot')
    p = obj(c.get('plan'), 'controller.plan')
    b = obj(c.get('boundary'), 'controller.boundary')
    entry = obj(o.get('entry'), 'observer.entry')
    cr = rows(c.get('rows'), 'controller.rows')
    samples = rows(o.get('rows'), 'observer.rows')
    ce = rows(c.get('events'), 'controller.events')
    oe = rows(o.get('events'), 'observer.events')
    completion = p.get('completion')
    kind = completion.get('kind') if isinstance(completion, dict) else 'endattack'
    if completion is not None:
        require(isinstance(completion, dict) and integer(completion.get('schema_version'))
                and completion['schema_version'] == 1 and kind in ('endattack', 'eof_invariant')
                and completion.get('model_verified') is True and completion.get('native_verified') is False,
                'completion_schema', 'Unknown or incorrectly promoted model completion schema')
    is_eof = kind == 'eof_invariant'
    require(c.get('version') == o.get('version') == 1, 'version', 'Expected version 1 controller and observer')
    require(c.get('status') == 'completed' and c.get('error') is None and c.get('nativeEndAttack') is (not is_eof),
            'controller_state', 'Controller did not finish consistently')
    require(o.get('started') is True, 'observer_started', 'Observer did not start at native TLPlay')
    require(o.get('errors') == [], 'observer_errors', 'Observer errors are missing or nonempty')
    for owner, record in (('controller', c), ('observer', o)):
        require('firstDamage' in record and record['firstDamage'] is None,
                'first_damage', owner + ' recorded damage or omitted the field')

    text = o.get('sourceText')
    digest = hashlib.sha256(text.encode('utf-8')).hexdigest() if isinstance(text, str) else None
    require(digest is not None, 'source_text', 'Observer must retain the exact TLPlay source text')
    for label, value in (('controller', c.get('csv_sha256')), ('observer', o.get('csv_sha256')),
                         ('plan', p.get('csv_sha256'))):
        require(digest is not None and value == digest, 'source_hash', label + ' differs from observed UTF-8 source')
    require(isinstance(text, str) and o.get('csv_bytes') == len(text.encode('utf-8')),
            'source_bytes', 'Observer source byte count differs')
    if 'source' in data:
        source = obj(data['source'], 'source')
        require(source.get('text') == text and source.get('sha256') == digest,
                'bridge_source', 'Loaded source and independently observed TLPlay differ')
    clock = obj(data['clock'], 'clock') if 'clock' in data else {}
    clock_mode = clock.get('mode', 'fixed-30hz-native-clamp')
    clamp30 = clock_mode == 'fixed-30hz-native-clamp'
    require(clamp30 or clock_mode == 'fixed-native-timestamps', 'clock_kind', 'Unexpected native clock driver')
    nominal_hz = clock.get('physicsHz', 30 if clamp30 else None)
    hz_ok = require(finite(nominal_hz) and (nominal_hz == 30 if clamp30 else nominal_hz in (60,120,240)),
                    'clock_hz', 'Native timestamp mode requires its supported nominal physicsHz')
    step_ms = 1000/nominal_hz + (1e-6 if clamp30 else 0) if hz_ok else None
    require(step_ms is not None and clock.get('logicalStepMs', step_ms if clamp30 else None) == step_ms,
            'clock_step', 'Logical timestamp increment differs from the native clock protocol')

    require(p.get('status') == 'candidate_found' and p.get('verified') is True,
            'candidate', 'Expected a scalar-verified complete source-model candidate')
    require(p.get('control_ticks') == 1 and p.get('clock_protocol') == 'explicit_dt_schedule'
            and (not clamp30 or p.get('physics_hz') == p.get('control_hz') == 30),
            'plan_clock', 'Expected one action per explicitly scheduled native tick')
    actions = p.get('actions')
    action_ok = require(isinstance(actions, list) and all(integer(x) and 0 <= x < 16 for x in actions),
                        'actions', 'Actions must be arrow masks without Cancel')
    actions = actions if action_ok else []
    n = len(actions)
    confirms = p.get('confirm_sequence')
    confirm_ok = require(isinstance(confirms, list) and len(confirms) == n and all(type(x) is bool for x in confirms),
                         'confirm_sequence', 'Every action needs an explicit boolean Confirm')
    confirms = confirms if confirm_ok else []
    trajectory = p.get('trajectory')
    trajectory_ok = require(isinstance(trajectory, list) and len(trajectory) == n + 1
                            and all(vector(row, 11) for row in trajectory),
                            'trajectory', 'Expected n+1 finite 11-component model states')
    trajectory = trajectory if trajectory_ok else []
    # The captured frame-zero dt is an observed initial fact. Subsequent dt
    # must be recomputed using the exact binary64 operations of the JS driver;
    # nominal 1/hz and epsilon comparisons would hide timestamp phase errors.
    stamp, initial_dt = b.get('clock_start_ms'), b.get('dt')
    clock_boundary_ok = require(finite(stamp) and finite(initial_dt) and 0 < initial_dt <= DT
                                and (not clamp30 or initial_dt == DT),
                                'boundary_clock', 'Finite native timestamp and captured dt are required')
    timestamps, native_dts = [], []
    if clock_boundary_ok and step_ms is not None:
        timestamps.append(stamp)
        native_dts.append(initial_dt)
        for i in range(n):
            following = stamp + step_ms
            delta = min((following-stamp)/1000, DT)
            require(finite(following) and finite(delta) and delta > 0,
                    'timestamp_progress', f'Native timestamp stopped advancing at frame {i+1}')
            timestamps.append(following)
            native_dts.append(delta)
            stamp = following
    require(len(native_dts) == n+1 and p.get('dt_sequence') == native_dts,
            'dt_sequence', 'Model dt sequence differs from exact native timestamp subtraction')
    if clamp30:
        require(native_dts == [DT] * (n+1), 'native_clamp', '30 Hz clock must reach the original 1/30 clamp every tick')
    require(c.get('actionsApplied') == n, 'action_count', 'Applied action count differs from complete candidate')
    start = b.get('tick')
    valid_start = require(integer(start) and start >= 0, 'boundary_tick', 'Boundary tick is missing or invalid')
    end = start + n if valid_start else None
    require(vector(b.get('initial'), 11) and bool(trajectory) and b['initial'] == trajectory[0],
            'boundary_state', 'Captured source boundary differs from model frame 0')
    source_environment = c.get('source_environment', b.get('initial_environment'))
    require(vector(source_environment, 22) and source_environment == p.get('initial_environment'),
            'source_environment', 'Plan does not retain the observed pre-source environment')
    if 'source_arena' in c:
        require(isinstance(c['source_arena'], dict) and p.get('initial_arena') == c['source_arena'],
                'source_arena', 'Plan does not retain the observed pre-source arena target/size/speed/callback')
    require(vector(b.get('initial_environment'), 22), 'boundary_environment', 'Post-source environment is missing')
    if 'source_environment' in c:
        visualization = obj(p.get('visualization'), 'plan.visualization')
        frames = visualization.get('frames')
        frame_env = frames[0].get('env') if isinstance(frames, list) and frames and isinstance(frames[0], dict) else None
        require(vector(frame_env, 22) and vector(b.get('initial_environment'), 22)
                and all(frame_env[i] == b['initial_environment'][i] for i in (0, 1, 2, 3, 4, 5, 7, 8)),
                'boundary_environment', 'Rebuilt frame 0 does not match the observed post-source arena/physics')
    require(b.get('HP') == 92 and b.get('KR') == 0 and clock_boundary_ok
            and b.get('SimulatorMode') == 2 and b.get('SingleAttack') == 'custom',
            'boundary_context', 'Boundary must be undamaged native custom mode under the captured clock')
    for name in ('initial_confirm', 'previous_confirm'):
        require(type(b.get(name)) is bool and p.get(name) is b.get(name),
                'boundary_confirm', name + ' is missing or differs from the captured latch')
    require(len(cr) == n + 1, 'controller_coverage', 'Controller must retain frame 0 and every applied tick')

    raw = o.get('ticks')
    valid_raw = require(isinstance(raw, list) and len(raw) == n + 1
                        and all(isinstance(row, list) and len(row) == 10 for row in raw),
                        'observer_coverage', 'Independent per-tick evidence must cover exactly frame 0 through final input')
    raw = raw if valid_raw else []
    if 'tickFields' in o:
        require(o['tickFields'] == list(TICK_FIELDS), 'tick_fields', 'Unsupported observer column order')
    by_tick = {}
    for i, row in enumerate(raw):
        tick = row[0]
        require(integer(tick) and valid_start and tick == start + i,
                'observer_tick_gap', f'Independent tick index {i} is discontinuous')
        require(row[1:4] == [92, 0, 2], 'observer_damage_mode', f'HP/KR/custom mode mismatch at {tick}')
        require(integer(row[4]) and 0 <= row[4] < 16 and type(row[5]) is int and row[5] in (0, 1),
                'observer_input_schema', f'Invalid physical input at {tick}')
        require(integer(row[6]) and finite(row[7]) and row[8] in (0, 1)
                and integer(row[9]) and row[9] >= 0, 'observer_tick_schema', f'Invalid Timeline/object count at {tick}')
        expected_mask = actions[i-1] if i and action_ok else b.get('initial', [None] * 5)[4] if vector(b.get('initial'), 11) else None
        expected_confirm = confirms[i-1] if i and confirm_ok else b.get('initial_confirm') if not i else None
        require(row[4] == expected_mask and row[5] == expected_confirm,
                'observer_input_mismatch', f'Independent arrows/Confirm differ at {tick}')
        if integer(tick):
            by_tick[tick] = row

    diffs = []
    terminal_diffs = []
    matched_components = 0
    discrete = set(range(4, 11))
    for i, row in enumerate(cr):
        tick = row.get('tick')
        require(integer(tick) and valid_start and tick == start + i,
                'controller_tick_gap', f'Controller row {i} is discontinuous')
        expected_dt = native_dts[i] if i < len(native_dts) else None
        expected_stamp = timestamps[i] if i < len(timestamps) else None
        require(row.get('HP') == 92 and row.get('KR') == 0 and expected_dt is not None and row.get('dt') == expected_dt,
                'controller_damage_clock', f'Controller HP/KR/dt mismatch at {tick}')
        require(expected_stamp is not None and row.get('clock_start_ms') == expected_stamp,
                'controller_timestamp', dict(tick=tick,actual=row.get('clock_start_ms'),expected=expected_stamp))
        state = row.get('state')
        pad = row.get('vpad')
        state_ok = require(vector(state, 11), 'controller_state_schema', f'Invalid state at {tick}')
        pad_ok = require(isinstance(pad, list) and len(pad) >= 14 and all(finite(x) for x in pad),
                         'vpad_schema', f'Full VPad latch missing at {tick}')
        if pad_ok:
            mask = (1 if pad[2] else 0) | (2 if pad[3] else 0) | (4 if pad[0] else 0) | (8 if pad[1] else 0) | (16 if pad[5] else 0)
            if state_ok:
                require(state[4] == mask, 'state_vpad', f'State mask and physical VPad disagree at {tick}')
            if i == 0:
                require(pad == b.get('vpad') and bool(pad[4]) == b.get('initial_confirm')
                        and bool(pad[11]) == b.get('previous_confirm'), 'initial_vpad', 'Frame-0 latch differs from boundary')
            elif i <= n and confirm_ok:
                require(row.get('mask') == actions[i-1] and row.get('confirm') is confirms[i-1]
                        and mask == actions[i-1] and bool(pad[4]) is confirms[i-1],
                        'controller_input_mismatch', f'Applied action/Confirm differs at {tick}')
                expected_previous = b.get('initial_confirm') if i == 1 else confirms[i-2]
                require(bool(pad[11]) is expected_previous, 'confirm_latch', f'Previous Confirm differs at {tick}')
        raw_row = by_tick.get(tick) if integer(tick) else None
        require(raw_row is not None, 'cross_tick_missing', f'No independent row for controller tick {tick}')
        if raw_row and state_ok and pad_ok:
            values = [tick, row.get('HP'), row.get('KR'), 2, state[4], int(bool(pad[4])),
                      row.get('line'), row.get('T'), row.get('running')]
            require(values == raw_row[:9], 'controller_observer_mismatch', f'Timeline, inputs or HP differ at {tick}')
        if i and finite(row.get('time')) and finite(cr[i-1].get('time')):
            require(expected_dt is not None and abs(row['time'] - cr[i-1]['time'] - expected_dt) <= 1e-10,
                    'native_time_step', f'Native elapsed time differs at {tick}')
        else:
            require(finite(row.get('time')), 'native_time', f'Native time missing at {tick}')
        if state_ok and i < len(trajectory):
            for k, (actual, expected) in enumerate(zip(state, trajectory[i])):
                delta = abs(actual - expected)
                diff = dict(frame=i, tick=tick, component=k, field=STATE_FIELDS[k],
                            actual=actual, expected=expected, abs_error=delta)
                if i == n and not is_eof:
                    if delta:
                        terminal_diffs.append(diff)
                else:
                    matched_components += 1
                    if delta:
                        diffs.append(diff)
                    require(delta == 0 if k in discrete or i == n else delta <= 1e-7,
                            'trajectory_mismatch', diff)

    # Full independent snapshots cross-check the per-tick controller states.
    for snapshot in [*samples, final]:
        tick = snapshot.get('tick')
        raw_row = by_tick.get(tick) if integer(tick) else None
        require(raw_row is not None, 'sample_tick', f'Independent snapshot outside covered ticks: {tick}')
        state = snapshot.get('state')
        require(vector(state, 11), 'sample_state', f'Independent snapshot lacks full state at {tick}')
        index = tick - start if integer(tick) and valid_start else -1
        expected_dt = native_dts[index] if 0 <= index < len(native_dts) else None
        expected_stamp = timestamps[index] if 0 <= index < len(timestamps) else None
        require(expected_dt is not None and snapshot.get('dt') == expected_dt and snapshot.get('attack') == 'custom',
                'sample_context', f'Independent snapshot clock/attack mismatch at {tick}')
        require(expected_stamp is not None and snapshot.get('clock_start_ms') == expected_stamp,
                'sample_timestamp', dict(tick=tick,actual=snapshot.get('clock_start_ms'),expected=expected_stamp))
        if raw_row:
            values = [snapshot.get(k) for k in TICK_FIELDS[:9]] + [len(snapshot.get('pending', []))]
            require(values == raw_row, 'sample_raw_mismatch', f'Independent snapshot differs from raw tick {tick}')
            if 0 <= index < len(cr):
                require(state == cr[index].get('state'), 'independent_state_mismatch',
                        f'Independent state differs from controller at {tick}')
    require(bool(samples), 'observer_samples', 'Independent full-state samples are missing')
    require(entry.get('tick') == (start - 1 if valid_start else None)
            and entry.get('HP') == 92 and entry.get('KR') == 0
            and entry.get('SimulatorMode') == 2 and entry.get('attack') == 'custom',
            'entry_coverage', 'Observer must begin at TLPlay immediately preceding frame 0')
    require(clock_boundary_ok and entry.get('dt') == initial_dt and entry.get('clock_start_ms') == b.get('clock_start_ms'),
            'entry_clock', 'Independent TLPlay observation differs from captured frame-zero timestamp/dt')

    for label, events in (('controller', ce), ('observer', oe)):
        event_ok = all(integer(e.get('tick')) and isinstance(e.get('fn'), str) for e in events)
        require(event_ok and bool(events), 'event_schema', label + ' events are invalid or empty')
        if event_ok:
            require(all(a['tick'] <= z['tick'] for a, z in zip(events, events[1:])),
                    'event_order', label + ' events are out of order')
            require(valid_start and all(start-1 <= e['tick'] < end for e in events),
                    'event_coverage', label + ' event lies outside the observed source execution')
        ends = [e for e in events if e.get('fn') == 'endattack']
        plays = [e for e in events if e.get('fn') == 'tlplay']
        if is_eof:
            require(not ends and not any(e.get('fn') in ('resetvars', 'tlstop') for e in events),
                    'eof_unexpected_end', label + ' EOF may not be replaced by EndAttack, ResetVars or TLStop')
        else:
            require(len(ends) == 1 and ends[0].get('tick') == (end-1 if end is not None else None),
                    'native_endattack', label + ' must observe one EndAttack during exactly the final input tick')
        require(len(plays) == 1 and plays[0].get('tick') == entry.get('tick'),
                'native_tlplay', label + ' source was missing or replaced')
        for event in events:
            if event.get('fn') == 'damageplayer':
                # Even a zero-argument controller record cannot independently
                # establish absence of damage; observer arguments are required.
                if label == 'observer':
                    args = event.get('args')
                    require(isinstance(args, list) and len(args) >= 2 and all(finite(x) and x <= 0 for x in args[:2]),
                            'damage_event', 'Positive or unparseable native DamagePlayer event')
    require([(e.get('tick'), e.get('fn')) for e in ce if e.get('fn') in SHARED_EVENTS]
            == [(e.get('tick'), e.get('fn')) for e in oe if e.get('fn') in SHARED_EVENTS],
            'event_crosscheck', 'Controller and independent native event chain differ')

    # GetHeartPos runs before the late player clamp. Correlate its independent
    # trigger-phase sample, never the posttick row's heart position.
    target_events = [e for e in oe if e.get('fn') == 'getheartpos']
    observed_history = []
    for event in target_events:
        sample = event.get('sampled_position')
        line = event.get('source_line')
        if require(valid_start and integer(event.get('tick')) and integer(line) and line > 0
                   and vector(sample, 2), 'target_observation', 'GetHeartPos requires its source line and exact trigger-phase position'):
            observed_history.append([event['tick'] - (start-1), line, *sample])
    declared_history = p.get('target_history')
    history_ok = require(isinstance(declared_history, list)
                         and all(isinstance(row, list) and len(row) == 4
                                 and integer(row[0]) and row[0] >= 0 and integer(row[1]) and row[1] > 0
                                 and all(finite(x) for x in row[2:]) for row in declared_history),
                         'target_history_schema', 'Candidate needs a complete finite target history')
    require(history_ok and declared_history == observed_history, 'target_history_mismatch',
            dict(declared=declared_history, independently_observed=observed_history))
    initial_observations = [row for row in observed_history if row[0] == 0]
    if 'initial_target_history' in c or initial_observations:
        require(c.get('initial_target_history') == p.get('initial_target_history') == initial_observations,
                'initial_target_history_mismatch', 'Initial native target facts differ across observer/controller/plan')

    if is_eof:
        require(final.get('tick') == end, 'terminal_tick', 'EOF snapshot must be the exact final planned posttick')
        closure = verify_eof_completion(require, completion, p, o, final, cr, raw,
                                        start, actions, confirms, trajectory)
        closure['verified'] = not errors
        return dict(passed=not errors, scope='saved_native_csv_run', errors=errors,
            summary=dict(csv_sha256=digest, first_tick=start, final_tick=end, actions=n,
                clock_mode=clock_mode, nominal_physics_hz=nominal_hz,
                verified_timestamp_ticks=len(timestamps), independent_hp_kr_ticks=len(raw),
                compared_state_components=matched_components, final_state_compared=True,
                finite_nonzero_differences=diffs,
                terminal_policy='native_eof_safety_invariant_under_permanent_release',
                completion_kind='eof_invariant', nativeEndAttack=False,
                complete_in_original_game=False, original_replay_passed=not errors,
                safe_forever_under_release=not errors, native_closure=closure,
                observer_status=o.get('status'), controller_status=c.get('status')))

    # EndAttack resets the native menu. Its post-event state is not the model's
    # pre-menu endpoint and must never be silently treated as trajectory match.
    require(final.get('tick') == end, 'terminal_tick', 'Final snapshot must be the final action posttick, without a neutral extra tick')
    reset = [e for e in oe if e.get('fn') == 'combatzoneresize' and e.get('tick') == (end-1 if end is not None else None)
             and isinstance(e.get('args'), list) and e['args'][:5] == [33, 251, 608, 391, 'MenuBattle']]
    require(len(reset) == 1, 'menu_reset_event', 'Native EndAttack must request the original menu arena and callback')
    require(final.get('pending') == [], 'terminal_pending', 'Attack objects remain or pending-object observation is missing')
    require(final.get('arenaTarget') == [33, 251, 608, 391] and final.get('resizeSpeed') == 480,
            'menu_reset_arena', 'Native ResetVars/menu arena target mismatch')
    require(final.get('endResize') in ('', 'MenuBattle'), 'menu_reset_callback', 'Unexpected deferred arena callback')
    fs = final.get('state')
    terminal_velocity = None
    if vector(fs, 11):
        require(fs[8:11] == [750, 0, 0], 'menu_reset_vars', 'MaxFallSpeed/SlamDamage/damage reset mismatch')
        require(fs[5] in (0, 1) and fs[6] in (0, 1) and fs[7] == 1,
                'menu_reset_heart', 'ResetVars must leave a valid heart mode/latch and reset direction downward')
        if trajectory:
            for k in (4, 5, 6, 10):
                delta = abs(fs[k] - trajectory[-1][k])
                require(delta == 0 if k in discrete else delta <= 1e-7,
                        'terminal_unexplained_state', f'Final {STATE_FIELDS[k]} differs beyond the supported menu reset')
        # Verify the velocity transformation itself, not a dx/dy exception to
        # endpoint comparison. Restrict this rule to the observed original
        # EndAttack -> menu resize -> ResetVars -> HeartMode sequence. Older
        # captures predate ResetVars instrumentation; accept that exact older
        # projection too, without filtering arbitrary extra final-tick calls.
        terminal_events = [e for e in oe if e.get('tick') == (end-1 if end is not None else None)]
        names = [e.get('fn') for e in terminal_events]
        old_chain = ['endattack', 'combatzoneresize', 'heartmode']
        full_chain = ['endattack', 'combatzoneresize', 'resetvars', 'heartmode']
        observer_resets = [e for e in oe if e.get('fn') == 'resetvars']
        controller_resets = [e for e in ce if e.get('fn') == 'resetvars']
        reset_ok = not observer_resets and not controller_resets
        if names == full_chain:
            # Battle.xml:1168 calls ResetVars without parameters. The observer
            # captures nine Param slots; the native API returns zero for each
            # absent parameter. Cross-check this newly observed call explicitly.
            reset_args = terminal_events[2].get('args')
            reset_ok = (len(observer_resets) == len(controller_resets) == 1
                and observer_resets[0].get('tick') == controller_resets[0].get('tick') == end-1
                and vector(reset_args, 9) and reset_args == [0] * 9)
        chain_ok = require(names in (old_chain, full_chain) and reset_ok,
                           'terminal_velocity_scope', 'Unsupported native terminal event sequence')
        previous = cr[-2].get('state') if n and len(cr) >= 2 else None
        mode_args = terminal_events[-1].get('args') if chain_ok else None
        mode_ok = require(vector(previous, 11) and isinstance(mode_args, list) and bool(mode_args)
                          and finite(mode_args[0])
                          and mode_args[0] == previous[6] == fs[6],
                          'terminal_velocity_scope', 'ResetVars must preserve the independently observed incoming mode')
        arena = None
        geometry_ok = True
        native_before = None
        has_snapshots = bool(terminal_events) and 'snapshots' in terminal_events[0]
        if chain_ok and mode_ok and has_snapshots:
            native_before = verify_endattack_snapshots(require, terminal_events[0], final, cr[-2], cr[-1], text)
            geometry_ok = native_before is not None
        elif mode_ok and fs[6] == 1:
            earlier = [s for s in samples if integer(s.get('tick')) and s['tick'] < end]
            anchor = max(earlier, key=lambda s: s['tick']) if earlier else {}
            arena = anchor.get('arena')
            stable = (vector(arena, 4) and arena == anchor.get('arenaTarget')
                      and anchor.get('endResize') == '' and not any(
                          e.get('fn') in ('combatzoneresize', 'combatzoneresizeinstant')
                          and integer(e.get('tick')) and anchor['tick'] <= e['tick'] < end-1 for e in oe))
            lifecycle = o.get('lifecycles')
            lifecycle_ok = isinstance(lifecycle, list) and all(
                isinstance(e, dict) and e.get('kind') in ('created', 'destroyed')
                and integer(e.get('tick')) and (
                    isinstance(e.get('object'), dict) and integer(e['object'].get('typeSid'))
                    if e.get('kind') == 'created' else integer(e.get('typeSid')))
                for e in lifecycle)
            no_platforms = lifecycle_ok and not any(
                (e.get('object', {}).get('typeSid') if e['kind'] == 'created' else e.get('typeSid'))
                in PLATFORM_SIDS for e in lifecycle)
            no_platforms = no_platforms and all(
                isinstance(s.get('pending'), list) and all(isinstance(a, dict)
                    and integer(a.get('typeSid')) and a['typeSid'] not in PLATFORM_SIDS for a in s['pending'])
                for s in [entry, *samples])
            geometry_ok = require(stable and no_platforms, 'terminal_velocity_scope',
                                  'Blue terminal rule needs an independently stable arena and no native platform lifecycles')
        if chain_ok and mode_ok and geometry_ok and actions and native_dts:
            try:
                terminal_velocity = (derive_observed_menu_velocity(native_before, int(previous[4]), actions[-1], native_dts[-1])
                    if has_snapshots else derive_menu_velocity(previous, actions[-1], native_dts[-1], fs[6], arena))
                terminal_velocity['actual'] = fs[2:4]
                for k, expected in zip((2, 3), terminal_velocity['expected']):
                    require(fs[k] == expected, 'terminal_unexplained_state',
                            dict(field=STATE_FIELDS[k], actual=fs[k], expected=expected,
                                 rule=terminal_velocity['rule']))
            except ValueError as error:
                require(False, 'terminal_velocity_scope', str(error))
        # MODE_SINGLE's bottom button selection has this original layout
        # coordinate. Keep the native layer-transform roundoff explicit.
        require(abs(fs[0] - 48) <= 1e-5 and abs(fs[1] - 453) <= 1e-7,
                'menu_heart_position', 'Final heart is not at the original custom-mode menu button')
    summary = dict(csv_sha256=digest, first_tick=start, final_tick=end, actions=n,
                   clock_mode=clock_mode,nominal_physics_hz=nominal_hz,
                   verified_timestamp_ticks=len(timestamps),distinct_native_dt_values=len(set(native_dts)),
                   independent_hp_kr_ticks=len(raw), matched_planned_input_ticks=n if valid_raw and confirm_ok else 0,
                   independently_matched_target_reads=len(observed_history) if declared_history == observed_history else 0,
                   compared_nonterminal_state_components=matched_components,
                   nonterminal_nonzero_differences=len(diffs),
                   max_nonterminal_abs_error=max((d['abs_error'] for d in diffs), default=0),
                   nonterminal_differences=diffs, terminal_model_differences=terminal_diffs,
                   terminal_velocity_derivation=terminal_velocity,
                   state_float_tolerance=1e-7, discrete_state_tolerance=0,
                   terminal_policy='native_endattack_and_original_single_custom_menu_reset',
                   observer_status=o.get('status'), controller_status=c.get('status'))
    return dict(passed=not errors, scope='saved_native_csv_run', errors=errors, summary=summary)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('record', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    try:
        data = json.loads(args.record.read_text(encoding='utf-8-sig'))
        verdict = verify_record(data)
    except (OSError, ValueError, TypeError, KeyError, IndexError) as error:
        verdict = dict(passed=False, scope='saved_native_csv_run',
                       errors=[dict(code='invalid_evidence', detail=str(error))])
    rendered = json.dumps(verdict, indent=2, ensure_ascii=False, allow_nan=False)
    if args.output:
        args.output.write_text(rendered + '\n', encoding='utf-8')
    print(rendered)
    return 0 if verdict['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())

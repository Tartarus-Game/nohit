"""Independently validate saved continuous jcw Normal-game evidence.

Historical v1/v2 retain their original contracts. Version 3 verifies the full
native clock/input/state trace and each fresh CSV candidate, including its
source phases, Confirm edges and exact EndAttack boundary. Large manifests
must be losslessly reconstructed and hash-checked before verification.
"""
import argparse
import hashlib
import json
import math
import struct
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EXPECTED_ATTACKS = tuple('sans_' + name for name in (
    'intro', 'bonegap1', 'bluebone', 'bonegap2', 'platforms1', 'platforms2',
    'platforms3', 'platforms4', 'platformblaster', 'platforms4hard',
    'bonegap1fast', 'boneslideh', 'bonegap2', 'spare', 'multi1',
    'randomblaster1', 'multi2', 'bonestab1', 'bonestab2', 'randomblaster2',
    'boneslidev', 'multi3', 'bonestab3', 'final',
))
REQUIRED_SOURCES = (
    'c2runtime.js', 'data.js', 'attack_seed.js', 'tas_runner.js',
    'full_game_runner.js', 'full_game_acceptance.js', 'lag_compensation.js',
    'menu_controller.js', 'solver_state.js',
)
TICK_FIELDS = ['tick','HP','KR','HitAttempts','SimulatorMode','keymask','confirm']
CSV_TICK_FIELDS = TICK_FIELDS + ['dt','clock_start_ms','previous_confirm','state']
CSV_REQUIRED_SOURCES = REQUIRED_SOURCES + ('csv_round_controller.js',)


def _integer(value):
    return type(value) is int


def _finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def _sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _vector(value, width):
    return isinstance(value, list) and len(value) == width and all(map(_finite, value))


def _implementation_hashes(root=ROOT):
    names = sorted([p.relative_to(root).as_posix() for p in (root/'nohit/engine').glob('*.py')]
                   + ['nohit/dashboard/csv_api.py', 'nohit/dashboard/csv_visualization.py'])
    return {name: _sha(root/name) for name in names}


def _verify_csv_rounds(data, rounds, entries, raw, events, require, implementation_dir, *, expected_rounds=24):
    """Version 3: independent actual ticks, actual TLPlay sources and CSV plans."""
    summary = dict(csv_evidence_version=3, matched_planned_input_ticks=0,
                   verified_native_clock_ticks=0, compared_nonterminal_state_components=0,
                   nonterminal_differences=[], terminal_model_differences=[],
                   independently_matched_target_reads=0, verified_request_schedules=0,
                   source_trigger_phases=[])
    protocol = data.get('clockProtocol')
    require(isinstance(protocol, dict) and protocol.get('mode') == 'fixed-240hz-realtime-catchup'
            and protocol.get('physicsHz') == 240 and protocol.get('logicalStepMs') == 1000/240,
            'csv_clock_protocol', 'CSV Normal evidence needs the original exact 240 Hz timestamp driver')
    if not (isinstance(raw, list) and raw and all(isinstance(r, list) and len(r) == 11 for r in raw)):
        return summary
    by_tick = {r[0]: r for r in raw if _integer(r[0])}
    entry_snapshot = data.get('entrySnapshot', {})
    entry_snapshot = entry_snapshot if isinstance(entry_snapshot, dict) else {}
    for i, row in enumerate(raw):
        tick, dt, stamp, last_confirm, state = row[0], row[7], row[8], row[9], row[10]
        require(_finite(dt) and 0 < dt <= 1/30 and _finite(stamp), 'csv_native_clock', f'Missing native dt/timestamp at {tick}')
        require(type(row[6]) is int and row[6] in (0, 1) and type(last_confirm) is int and last_confirm in (0, 1),
                'csv_native_confirm', f'Invalid physical Confirm latch at {tick}')
        require(_vector(state, 11) and state[4] == row[5] and state[10] == 0,
                'csv_native_state', f'Invalid native state/mask/damage at {tick}')
        if i == 0:
            require(stamp == entry_snapshot.get('clock_start_ms') and dt == entry_snapshot.get('dt'),
                    'csv_entry_clock', 'Opening StartAttack and its first posttick must share the actual clock')
        elif _finite(raw[i-1][8]):
            following = raw[i-1][8] + 1000/240
            expected_dt = min((following-raw[i-1][8])/1000, 1/30)
            require(stamp == following and dt == expected_dt, 'csv_native_clock',
                    dict(tick=tick, actual=[stamp,dt], expected=[following,expected_dt]))
            require(last_confirm == raw[i-1][6], 'csv_confirm_latch', f'Previous Confirm is discontinuous at {tick}')
        summary['verified_native_clock_ticks'] += 1

    def snapshot_matches(snapshot, label, *, post=True):
        if not require(isinstance(snapshot, dict), 'csv_snapshot_schema', label):
            return False
        tick = snapshot.get('tick')
        row = by_tick.get(tick) if _integer(tick) and post else None
        if not post and _integer(tick):
            # Native AJAX can trigger TLPlay between physical ticks. During a
            # runtime tick tickcount has not incremented yet, but last_tick_time
            # already has the next stamp. Exact strictly increasing stamps
            # uniquely distinguish these phases; no epsilon or guessed offset.
            matches = [(phase,by_tick[target]) for phase,target in
                       (('between_ticks',tick),('in_tick',tick+1)) if target in by_tick
                       and snapshot.get('clock_start_ms')==by_tick[target][8]
                       and snapshot.get('dt')==by_tick[target][7]]
            if require(len(matches)==1, 'csv_source_trigger_phase', label+' must match exactly one native clock phase'):
                phase,row=matches[0]
                require('phase' not in snapshot or snapshot['phase']==phase,
                        'csv_source_trigger_phase',label+' explicit phase differs from native timestamps')
                summary['source_trigger_phases'].append(dict(label=label,trigger_tick=tick,
                                                             observed_posttick=row[0],phase=phase))
        if not require(row is not None, 'csv_snapshot_coverage', label):
            return False
        fields = CSV_TICK_FIELDS if post else ('HP','KR','SimulatorMode','dt','clock_start_ms')
        for field in fields:
            require(snapshot.get(field) == row[CSV_TICK_FIELDS.index(field)],
                    'csv_snapshot_mismatch', f'{label}: {field} differs from independent raw tick')
        return True

    try:
        implementation = _implementation_hashes(implementation_dir)
    except OSError as error:
        require(False, 'csv_implementation_missing', str(error)); implementation = {}
    require(bool(implementation) and data.get('solver_source_sha256') == implementation,
            'csv_solver_source_hash', 'Saved solver source identities differ from the required implementation files')
    seen_ids, last_generation, successful = set(), {}, {}
    previous_round = -1
    for attempt, entry in enumerate(entries):
        p = entry.get('plan') if isinstance(entry.get('plan'), dict) else {}
        request = entry.get('request') if isinstance(entry.get('request'), dict) else {}
        ri, generation = entry.get('round'), entry.get('request_generation')
        valid_round = _integer(ri) and 0 <= ri < len(rounds)
        if not require(valid_round, 'csv_attempt_round', f'Attempt {attempt} has no matching round'):
            continue
        round_record = rounds[ri]
        label = f'Round {ri+1}, attempt {generation}'
        require(ri not in successful, 'csv_attempt_after_success', label+' retries an already executed candidate')
        require(ri >= previous_round, 'csv_attempt_order', label+' is out of chronological round order')
        previous_round = ri
        require(_integer(generation) and generation > last_generation.get(ri, 0),
                'csv_request_generation', label+' generation was reused or reversed')
        if _integer(generation): last_generation[ri] = generation
        require(entry.get('wave') == round_record.get('attack','')+'.csv', 'csv_attempt_wave', label)
        status = p.get('status')
        require(status in ('candidate_found','unknown'), 'csv_attempt_status', label+' has an unsupported result')
        provenance = p.get('provenance') if isinstance(p.get('provenance'), dict) else {}
        request_id = request.get('request_id')
        valid_id = isinstance(request_id, str) and 0 < len(request_id) <= 128
        require(valid_id and request_id not in seen_ids and provenance.get('request_id') == request_id,
                'csv_request_identity', label+' fresh request identity is missing, stale or inconsistent')
        if valid_id: seen_ids.add(request_id)
        require(provenance.get('fresh_computation') is True and provenance.get('route_cache_hit') is False
                and provenance.get('implementation_sha256') == implementation,
                'csv_fresh_provenance', label+' does not attest a fresh computation by the recorded implementation')

        source = round_record.get('source') if isinstance(round_record.get('source'),dict) else {}
        pre = source.get('preSnapshot') if isinstance(source.get('preSnapshot'),dict) else {}
        boundary = round_record.get('boundary') if isinstance(round_record.get('boundary'),dict) else {}
        cap = entry.get('captured') if isinstance(entry.get('captured'),dict) else {}
        text = source.get('text')
        digest = hashlib.sha256(text.encode('utf-8')).hexdigest() if isinstance(text,str) else None
        require(digest is not None and source.get('sha256') == entry.get('source_sha256') == p.get('csv_sha256') == digest
                and entry.get('source_text') == request.get('custom_csv') == text,
                'csv_round_source', label+' candidate/request/observer TLPlay sources differ')
        plays = [e for e in events if e.get('fn') == 'tlplay' and e.get('round') == ri]
        require(len(plays) == 1 and plays[0].get('param') == text and plays[0].get('tick') == pre.get('tick'),
                'csv_native_tlplay', label+' does not have exactly one matching native TLPlay')
        snapshot_matches(pre, label+' pre-source', post=False)
        snapshot_matches(boundary, label+' source boundary')
        require(_integer(cap.get('tick')) and cap.get('tick') == boundary.get('tick')
                and _integer(pre.get('tick')) and pre['tick'] < cap['tick']
                and round_record.get('startTick', math.inf) <= pre['tick'],
                'csv_boundary_phase', label+' pre-TLPlay and committed frame-zero phases differ')
        require(_vector(cap.get('initial'),11) and cap.get('initial') == boundary.get('state') == p.get('initial') == request.get('initial'),
                'csv_boundary_state', label+' complete initial state differs from independent native frame zero')
        for field in ('tick','dt','clock_start_ms','HP','KR','SimulatorMode','line','running','vpad','arena','initial_environment'):
            require(cap.get(field) == boundary.get(field), 'csv_boundary_context', label+': '+field)
        require(cap.get('timeline') == boundary.get('T') and cap.get('HP') == 92 and cap.get('KR') == 0
                and cap.get('SimulatorMode') == 0, 'csv_boundary_context', label+' Timeline/Normal/health differs')
        pad = boundary.get('vpad')
        pad_ok = isinstance(pad,list) and len(pad) >= 14 and all(_finite(v) for v in pad)
        if require(pad_ok, 'csv_boundary_vpad', label+' lacks the complete physical VPad latch'):
            mask = (1 if pad[2] else 0)|(2 if pad[3] else 0)|(4 if pad[0] else 0)|(8 if pad[1] else 0)|(16 if pad[5] else 0)
            require(mask == boundary.get('keymask') and int(bool(pad[4])) == boundary.get('confirm')
                    and int(bool(pad[11])) == boundary.get('previous_confirm'),
                    'csv_boundary_vpad', label+' physical VPad disagrees with independent input fields')
        for capture_field, observed_field in (('initial_confirm','confirm'),('previous_confirm','previous_confirm')):
            value = cap.get(capture_field)
            require(type(value) is bool and value == boundary.get(observed_field)
                    and request.get(capture_field) is value and p.get(capture_field) is value,
                    'csv_boundary_confirm', label+': '+capture_field)
        environment, arena = entry.get('source_environment'), entry.get('source_arena')
        require(_vector(environment,22) and environment == pre.get('initial_environment')
                == request.get('initial_environment') == p.get('initial_environment'),
                'csv_source_environment', label+' pre-source environment was replaced or changed')
        require(isinstance(arena,dict) and _vector(arena.get('target'),4) and _vector(arena.get('size'),2)
                and _finite(arena.get('speed')) and isinstance(arena.get('callback'),str)
                and arena == pre.get('arena') == request.get('initial_arena') == p.get('initial_arena'),
                'csv_source_arena', label+' original arena continuation differs')
        targets = [e for e in events if e.get('fn') == 'getheartpos' and e.get('round') == ri]
        history = []
        for event in targets:
            if require(_integer(event.get('tick')) and _integer(event.get('source_line'))
                       and event['source_line'] > 0 and _vector(event.get('sampled_position'),2)
                       and _integer(cap.get('tick')), 'csv_target_observation', label):
                history.append([event['tick']-(cap['tick']-1),event['source_line'],*event['sampled_position']])
        initial_history = [row for row in history if row[0] == 0]
        require(all(0 <= row[0] <= round_record.get('endTick',-1)-(cap.get('tick',0)-1) for row in history)
                and entry.get('initial_target_history') == initial_history
                == request.get('initial_target_history') == p.get('initial_target_history'),
                'csv_initial_target_history', label+' tick-zero target reads differ')
        schedule = request.get('dt_schedule')
        schedule_ok = isinstance(schedule,list) and bool(schedule) and all(_finite(v) and 0 < v <= 1/30 for v in schedule)
        budget = request.get('max_ticks')
        require(schedule_ok and _integer(budget) and 0 < budget <= len(schedule),
                'csv_request_schedule', label+' full future clock/budget is missing')
        require(request.get('seed') == data.get('seed') == p.get('seed') and p.get('max_ticks') == budget,
                'csv_request_settings', label+' seed/budget identity differs')
        if schedule_ok and _finite(cap.get('clock_start_ms')) and _finite(cap.get('dt')):
            stamp = cap['clock_start_ms']; expected = [cap['dt']]
            for _ in range(1,len(schedule)):
                following = stamp + 1000/240
                expected.append(min((following-stamp)/1000,1/30)); stamp = following
            require(schedule == expected, 'csv_request_clock', label+' full future dt schedule differs from native timestamp arithmetic')
            summary['verified_request_schedules'] += 1
            schedule_hash = hashlib.sha256(b''.join(struct.pack('<d',v) for v in schedule)).hexdigest()
            plan_clock = p.get('clock') if isinstance(p.get('clock'),dict) else {}
            if status == 'candidate_found':
                require(plan_clock.get('protocol') == 'explicit_dt_schedule' and plan_clock.get('decision_ticks') == 1
                        and plan_clock.get('schedule_count') == len(schedule) and plan_clock.get('schedule_sha256') == schedule_hash,
                        'csv_plan_clock_identity', label+' plan does not bind the complete requested binary64 schedule')
        if status != 'candidate_found':
            require(p.get('verified') is False, 'csv_unknown_verified', label+' unknown result claims verification')
            continue
        successful[ri] = successful.get(ri,0)+1
        require(p.get('verified') is True and p.get('planner') == 'bounded-frontier-with-dialogue'
                and p.get('control_ticks') == 1 and p.get('clock_protocol') == 'explicit_dt_schedule',
                'csv_candidate_protocol', label+' is not a verified CSV candidate')
        visualization = p.get('visualization') if isinstance(p.get('visualization'),dict) else {}
        frames = visualization.get('frames')
        frame_env = frames[0].get('env') if isinstance(frames,list) and frames and isinstance(frames[0],dict) else None
        observed_env = boundary.get('initial_environment')
        require(_vector(frame_env,22) and _vector(observed_env,22)
                and all(frame_env[k] == observed_env[k] for k in (0,1,2,3,4,5,7,8)),
                'csv_committed_environment', label+' rebuilt source frame zero differs from independently committed physics')
        require(p.get('target_history') == history, 'csv_target_history', label+' complete target history differs')
        if p.get('target_history') == history: summary['independently_matched_target_reads'] += len(history)
        actions, confirms, trajectory = p.get('actions'), p.get('confirm_sequence'), p.get('trajectory')
        action_ok = isinstance(actions,list) and all(_integer(a) and 0 <= a < 16 for a in actions)
        count = len(actions) if action_ok else -1
        require(action_ok and isinstance(confirms,list) and len(confirms) == count and all(type(v) is bool for v in confirms),
                'csv_candidate_actions', label+' lacks complete arrows and Confirm for every physical tick')
        trace_ok = isinstance(trajectory,list) and len(trajectory) == count+1 and all(_vector(s,11) for s in trajectory)
        require(trace_ok, 'csv_trajectory_schema', label+' requires n+1 complete state vectors')
        dt_prefix_ok = schedule_ok and count >= 0 and count+1 <= len(schedule) and p.get('dt_sequence') == schedule[:count+1]
        require(dt_prefix_ok,
                'csv_candidate_dt', label+' executed dt sequence is not exactly the request prefix')
        end_snapshot = round_record.get('endSnapshot')
        snapshot_matches(end_snapshot, label+' EndAttack posttick')
        end_tick = round_record.get('endTick')
        interval_ok = (_integer(cap.get('tick')) and _integer(end_tick) and count >= 0
                       and cap['tick']+count == end_tick+1)
        require(interval_ok and isinstance(end_snapshot,dict) and end_snapshot.get('tick') == end_tick+1
                and entry.get('actionsApplied') == count,
                'csv_terminal_coverage', label+' must finish on exactly the final input posttick of native EndAttack')
        if not (interval_ok and trace_ok and dt_prefix_ok and isinstance(confirms,list) and len(confirms)==count):
            continue
        controller_rows = entry.get('rows')
        controller_ok = (isinstance(controller_rows,list) and len(controller_rows)==count+1
                         and all(isinstance(r,dict) for r in controller_rows))
        require(controller_ok, 'csv_controller_coverage', label+' controller must retain frame zero and every input tick')
        controller_events = entry.get('events')
        shared = {'tlplay','tlpause','tlresume','endattack','damageplayer'}
        # The controller owns the physical tick through EndAttack's posttick.
        # The observer clears active immediately on the EndAttack trigger, so
        # nested callbacks in that same tick already carry the next round id.
        # Scope by the actual TLPlay event and terminal tick, retaining every
        # shared event in order; later Win/menu callbacks are outside the run.
        source_event_index = events.index(plays[0]) if len(plays)==1 else len(events)
        native_controller_events = [e for e in events[source_event_index:]
                                    if _integer(e.get('tick')) and e['tick'] <= end_tick
                                    and e.get('fn') in shared]
        require(isinstance(controller_events,list) and all(isinstance(e,dict) for e in controller_events)
                and [(e.get('tick'),e.get('fn')) for e in controller_events] ==
                    [(e.get('tick'),e.get('fn')) for e in native_controller_events],
                'csv_controller_events', label+' controller and independent native event chains differ')
        for offset in range(count+1):
            row = by_tick.get(cap['tick']+offset)
            if not require(row is not None, 'csv_action_coverage', label+f' missing frame {offset}'):
                continue
            if offset:
                require(row[5] == actions[offset-1] and row[6] == confirms[offset-1],
                        'csv_candidate_input_mismatch', label+f' arrows/Confirm differ at frame {offset}')
                expected_previous = cap.get('initial_confirm') if offset==1 else confirms[offset-2]
                require(row[9] == expected_previous, 'csv_candidate_confirm_latch', label+f' Confirm edge differs at frame {offset}')
                summary['matched_planned_input_ticks'] += 1
            require(row[3] == ri, 'csv_round_fight_counter', label+f' FIGHT counter changed during frame {offset}')
            require(row[7] == p['dt_sequence'][offset], 'csv_candidate_native_dt', label+f' native dt differs at frame {offset}')
            if controller_ok:
                controlled = controller_rows[offset]
                require(all(controlled.get(field)==row[CSV_TICK_FIELDS.index(field)]
                            for field in ('tick','HP','KR','dt','clock_start_ms','state')),
                        'csv_controller_state', label+f' controller differs from independent native frame {offset}')
                pad = controlled.get('vpad')
                valid_pad = isinstance(pad,list) and len(pad)>=14 and all(_finite(v) for v in pad)
                if require(valid_pad,'csv_controller_vpad',label+f' missing VPad at frame {offset}'):
                    mask=(1 if pad[2] else 0)|(2 if pad[3] else 0)|(4 if pad[0] else 0)|(8 if pad[1] else 0)|(16 if pad[5] else 0)
                    require(mask==row[5] and int(bool(pad[4]))==row[6] and int(bool(pad[11]))==row[9],
                            'csv_controller_vpad',label+f' controller input latches differ at frame {offset}')
                if offset:
                    require(controlled.get('mask')==actions[offset-1] and controlled.get('confirm') is confirms[offset-1],
                            'csv_controller_action',label+f' applied control differs at frame {offset}')
            if not _vector(row[10],11): continue
            for k,(actual,expected) in enumerate(zip(row[10],trajectory[offset])):
                delta = abs(actual-expected)
                difference = dict(round=ri,frame=offset,tick=row[0],component=k,actual=actual,expected=expected,abs_error=delta)
                if offset == count:
                    if delta: summary['terminal_model_differences'].append(difference)
                else:
                    summary['compared_nonterminal_state_components'] += 1
                    if delta: summary['nonterminal_differences'].append(difference)
                    require(delta == 0 if k>=4 else delta <= 1e-7, 'csv_trajectory_mismatch', difference)
        terminal_state = end_snapshot.get('state') if isinstance(end_snapshot,dict) else None
        require(_vector(terminal_state,11) and terminal_state[7:11] == [1,750,0,0],
                'csv_terminal_reset', label+' native ResetVars direction/maxfall/slam/damage differ')
    require(all(successful.get(i) == 1 for i in range(expected_rounds)), 'csv_successful_rounds',
            'Each native round needs exactly one fresh successful CSV candidate')
    for event in events:
        if event.get('fn') == 'damageplayer':
            require(_finite(event.get('param')) and _finite(event.get('kr'))
                    and event['param'] <= 0 and event['kr'] <= 0,
                    'csv_damage_event', 'Positive or missing native DamagePlayer arguments')
    summary['max_nonterminal_abs_error'] = max((d['abs_error'] for d in summary['nonterminal_differences']),default=0)
    summary['terminal_policy'] = 'native_EndAttack_posttick_and_ResetVars; differences_reported_not_trajectory_matches'
    return summary


def diagnose_completed_csv_rounds(data, *, game_dir=ROOT/'c2-sans-fight',
                                  original_dir=ROOT/'jcw87-c2-sans-fight', implementation_dir=ROOT):
    """Diagnose a completed prefix without ever accepting an incomplete game.

    The same strict v3 round verifier is used. Ongoing/unknown attempts beyond
    the completed prefix are counted but cannot become successful rounds.
    Actual health, input and clock evidence remains continuous through the
    saved observation's end, including menus and any ongoing round.
    """
    errors = []
    def require(condition, code, detail):
        if not condition: errors.append(dict(code=code,detail=detail))
        return condition
    result = dict(passed=False,scope='completed_round_diagnostic_not_campaign_acceptance',
                  completed_rounds_valid=False,errors=errors,rounds=[],summary={})
    if not require(isinstance(data,dict) and data.get('evidenceVersion')==3
                   and data.get('suite')=='continuous-normal-game' and 'storage' not in data,
                   'csv_diagnostic_schema','Load a reconstructed version-3 Normal record first'):
        return result
    rounds, entries, events, raw = (data.get(k) for k in ('rounds','computedPlans','events','tickEvidence'))
    if not require(all(isinstance(values,list) and all(isinstance(v,dict) for v in values)
                       for values in (rounds,entries,events)) and isinstance(raw,list) and bool(raw)
                   and all(isinstance(r,list) and len(r)==11 for r in raw)
                   and data.get('tickEvidenceFields')==CSV_TICK_FIELDS,
                   'csv_diagnostic_schema','Complete round/event/attempt/raw-tick arrays are required'):
        return result
    count = len(rounds)
    if count == 0:
        result['completed_rounds_valid'] = None
        result['summary'] = dict(completed_rounds=0,reason='No native EndAttack has completed a round',
                                 unfinished_attempts=len(entries))
        return result
    require(0 < count <= 24 and tuple(r.get('attack') for r in rounds)==EXPECTED_ATTACKS[:count],
            'csv_diagnostic_rounds','Completed rounds must be an ordered original campaign prefix')
    require(data.get('firstDamage') is None and data.get('tickGaps')==[]
            and data.get('clockErrors')==[] and data.get('protocolErrors')==[],
            'csv_diagnostic_observer','Observer reports damage, a gap or a protocol/clock error')
    require(_integer(data.get('seed')) and 0<=data['seed']<2**32,'seed','Expected the original uint32 seed')
    require(data.get('checkedTicks')==len(raw), 'raw_count','Every observed native tick must remain present')
    for i,row in enumerate(raw):
        require(_integer(row[0]) and _integer(raw[0][0]) and row[0]==raw[0][0]+i,
                'raw_tick_gap',f'Discontinuous native tick at {i}')
        require(row[1:3]==[92,0] and row[4]==0,'raw_damage',f'Health/Normal mode differs at {row[0]}')
        require(_integer(row[3]) and 0<=row[3]<=23 and _integer(row[5]) and 0<=row[5]<32,
                'raw_input',f'Invalid native input/FIGHT counter at {row[0]}')
        if i:
            require(_integer(row[3]) and _integer(raw[i-1][3]) and row[3]-raw[i-1][3] in (0,1),
                    'raw_fight_progress',f'Counter skipped or reversed at {row[0]}')
    require(all(_integer(e.get('tick')) and isinstance(e.get('fn'),str) for e in events)
            and all(a.get('tick',math.inf)<=b.get('tick',-math.inf) for a,b in zip(events,events[1:])),
            'event_order','Native event evidence must remain chronological')
    for ri,rnd in enumerate(rounds):
        start,end=rnd.get('startTick'),rnd.get('endTick')
        require(_integer(start) and _integer(end) and start<end
                and (not ri or rounds[ri-1].get('endTick',math.inf)<start),
                'round_bounds',f'Invalid completed round {ri+1} interval')
        for fn,tick in (('startattack',start),('runattack',start),('endattack',end)):
            matching=[e for e in events if e.get('fn')==fn and e.get('round')==ri]
            require(len(matching)==1 and matching[0].get('tick')==tick,
                    'csv_diagnostic_boundary',f'Round {ri+1} lacks its original {fn}')
        result['rounds'].append(dict(round=ri,wave=rnd.get('attack'),start_tick=start,end_trigger_tick=end))
    selected=[entry for entry in entries if _integer(entry.get('round')) and 0<=entry['round']<count]
    result['summary']=_verify_csv_rounds(data,rounds,selected,raw,events,require,Path(implementation_dir),expected_rounds=count)
    result['summary'].update(completed_rounds=count,unfinished_attempts=len(entries)-len(selected))
    for report in result['rounds']:
        successful=[e for e in selected if e.get('round')==report['round']
                    and isinstance(e.get('plan'),dict) and e['plan'].get('status')=='candidate_found']
        if len(successful)==1:
            candidate=successful[0];actions=candidate['plan'].get('actions')
            report['actions']=len(actions) if isinstance(actions,list) else None
            cap=candidate.get('captured') if isinstance(candidate.get('captured'),dict) else {}
            report['boundary_tick']=cap.get('tick')
        differences=[d for d in result['summary']['nonterminal_differences'] if d['round']==report['round']]
        report['nonterminal_nonzero_differences']=len(differences)
        report['max_nonterminal_abs_error']=max((d['abs_error'] for d in differences),default=0)
        report['terminal_model_differences']=[d for d in result['summary']['terminal_model_differences']
                                            if d['round']==report['round']]
    game_dir,original_dir=Path(game_dir),Path(original_dir)
    source_hashes=data.get('source_sha256',{});script_hashes=data.get('script_sha256',{})
    text_hashes=data.get('script_text_sha256',{})
    for name in CSV_REQUIRED_SOURCES:
        path=game_dir/name
        if not require(path.is_file(),'source_missing',str(path)):continue
        require(isinstance(source_hashes,dict) and source_hashes.get(name)==_sha(path),
                'loaded_source_hash',name)
        if name in ('c2runtime.js','data.js'):
            original=original_dir/name
            require(original.is_file() and _sha(path)==_sha(original),'original_runtime_hash',name)
    for rnd in rounds:
        name=rnd.get('attack','')+'.csv';path=game_dir/name;original=original_dir/name
        if not require(path.is_file() and original.is_file(),'original_script_missing',name):continue
        digest=_sha(path)
        text_digest=hashlib.sha256(path.read_bytes().decode('utf-8-sig').replace('\r\n','\n').encode('utf-8')).hexdigest()
        require(digest==_sha(original) and isinstance(script_hashes,dict) and script_hashes.get(name)==digest,
                'original_script_hash',name)
        source=rnd.get('source') if isinstance(rnd.get('source'),dict) else {}
        require(isinstance(text_hashes,dict) and text_hashes.get(name)==source.get('sha256')==text_digest,
                'recorded_script_text_hash',name)
    result['completed_rounds_valid']=not errors
    return result


def verify_record(data, *, game_dir=ROOT/'c2-sans-fight',
                  original_dir=ROOT/'jcw87-c2-sans-fight', implementation_dir=ROOT):
    """Return a fail-closed result without modifying evidence or game files."""
    errors=[]
    def require(condition, code, detail):
        if not condition:
            errors.append({'code':code,'detail':detail})
        return condition

    if not isinstance(data, dict):
        return {'passed':False,'errors':[{'code':'record_type','detail':'Expected a JSON object'}]}
    if 'storage' in data or 'evidenceParts' in data:
        return {'passed':False,'errors':[{'code':'unresolved_manifest',
                'detail':'Load and verify every referenced part with load_record before verifying a manifest'}]}
    game_dir,original_dir=Path(game_dir),Path(original_dir)
    require(data.get('suite')=='continuous-normal-game','suite','Record must be a continuous normal-game run')
    result=data.get('result') if isinstance(data.get('result'),dict) else {}
    require(result.get('passed') is True and result.get('status')=='passed','live_verdict','Live observer did not report a passed run')
    require(data.get('winObserved') is True,'win_observed','Native Win2 was not observed')
    require(data.get('firstDamage') is None,'first_damage','A first damage event was recorded or the field is invalid')
    for key in ('firstDamage','tickGaps','clockErrors','checkedTicks'):
        require(key in data,'missing_field',key)
    require(data.get('tickGaps')==[],'tick_gaps','Native tick gaps were recorded or the field is missing')
    require(data.get('clockErrors')==[],'clock_errors','Clock errors were recorded or the field is missing')
    require(data.get('clock')=='original-runtime-realtime-catchup-240hz','clock_kind','Expected the fixed 240 Hz native driver')
    require(_integer(data.get('seed')) and 0<=data['seed']<2**32,'seed','Seed must be an unsigned 32-bit integer')
    version=data.get('evidenceVersion',1)
    require(type(version) is int and version in (1,2,3),'evidence_version','Unknown continuous evidence format')
    stride=data.get('sampleStride',16)
    require(_integer(stride) and stride==(64 if version in (2,3) else 16),'sample_stride','Unexpected diagnostic sample stride')
    if not _integer(stride) or stride<1:stride=16

    lists={}
    for key in ('rows','events','rounds','computedPlans'):
        value=data.get(key)
        if require(isinstance(value,list) and all(isinstance(v,dict) for v in value),'list_schema',key):
            lists[key]=value
        else:
            lists[key]=[]
    rows,events,rounds,plans=(lists[k] for k in ('rows','events','rounds','computedPlans'))
    valid_rows=bool(rows) and all(_integer(r.get('tick')) for r in rows)
    require(valid_rows,'sample_rows','Nonempty samples with integer native tick indices are required')
    first_tick=last_tick=None
    if valid_rows:
        ticks=[r['tick'] for r in rows]
        first_tick,last_tick=ticks[0],ticks[-1]
        require(first_tick>=0 and all(a<b for a,b in zip(ticks,ticks[1:])),
                'sample_order','Sample ticks must be strictly increasing')
        require(_integer(data.get('checkedTicks')) and data['checkedTicks']==last_tick-first_tick+1,
                'coverage_count','checkedTicks must cover every tick from the first sample through the last')
        expected_samples=sorted({first_tick,last_tick,*range(((first_tick+stride-1)//stride)*stride,last_tick+1,stride)})
        require(ticks==expected_samples,'sample_coverage','The declared sample sequence has missing or extra rows')
    for row in rows:
        tick=row.get('tick')
        require(row.get('HP')==92 and row.get('KR')==0,'sample_damage',f'HP/KR changed or missing at tick {tick}')
        require(_finite(row.get('dt')) and abs(row['dt']-1/240)<=1e-10,
                'sample_dt',f'Invalid 240 Hz delta at tick {tick}')
        # `mode` is the heart color, not SimulatorMode. Do not conflate them.
        for key in ('SimulatorMode','simulatorMode'):
            if key in row:
                require(row[key]==0,'simulator_mode',f'Non-normal simulator mode at tick {tick}')

    raw_verified=False;raw=[];matched_inputs=0
    if version in (2,3):
        require(data.get('protocolErrors')==[],'protocol_errors','The strict observer recorded protocol errors')
        fields = CSV_TICK_FIELDS if version==3 else TICK_FIELDS
        require(data.get('tickEvidenceFields')==fields,'raw_schema','Unexpected compact per-tick column layout')
        raw=data.get('tickEvidence')
        valid_raw=isinstance(raw,list) and bool(raw) and all(isinstance(r,list) and len(r)==len(fields) for r in raw)
        require(valid_raw,'raw_rows','Complete compact per-tick evidence is required')
        if valid_raw:
            raw_errors=len(errors)
            require(len(raw)==data.get('checkedTicks'),'raw_count','Raw row count does not match checkedTicks')
            for index,r in enumerate(raw):
                require(_integer(r[0]) and valid_rows and r[0]==first_tick+index,
                        'raw_tick_gap',f'Invalid consecutive raw tick at index {index}')
                require(r[1:3]==[92,0],'raw_damage',f'Raw HP/KR changed at tick {r[0]}')
                require(_integer(r[3]) and 0<=r[3]<=23,'raw_hit_attempts',f'Invalid HitAttempts at tick {r[0]}')
                require(r[4]==0,'raw_mode',f'Non-normal mode at tick {r[0]}')
                require(_integer(r[5]) and 0<=r[5]<32 and r[6] in (0,1),
                        'raw_input',f'Invalid VPad input at tick {r[0]}')
                if index:
                    require(_integer(r[3]) and _integer(raw[index-1][3]) and r[3]-raw[index-1][3] in (0,1),
                            'raw_fight_progress',f'HitAttempts skipped or reversed at tick {r[0]}')
            require(raw[0][3]==0 and raw[-1][3]==23,'raw_fight_endpoints','Raw counters must begin at 0 and finish at 23')
            if valid_rows:
                require(raw[-1][0]==last_tick,'raw_terminal','Raw trace does not reach the final diagnostic row')
                for row in rows:
                    index=row['tick']-first_tick
                    if 0<=index<len(raw):
                        require([row.get(k) for k in fields]==raw[index],
                                'raw_sample_mismatch',f'Diagnostic row differs from raw evidence at tick {row["tick"]}')
            raw_verified=len(errors)==raw_errors
        else:
            raw=[]

    valid_events=all(_integer(e.get('tick')) and isinstance(e.get('fn'),str) for e in events)
    require(valid_events and bool(events),'event_schema','Native events require tick and function name')
    runs=[e for e in events if e.get('fn')=='runattack']
    starts=[e for e in events if e.get('fn')=='startattack']
    ends=[e for e in events if e.get('fn')=='endattack']
    win1=[e for e in events if e.get('fn')=='win1']
    win2=[e for e in events if e.get('fn')=='win2']
    if valid_events:
        require(all(a['tick']<=b['tick'] for a,b in zip(events,events[1:])),
                'event_order','Native events are not chronological')
    require(len(rounds)==24 and result.get('rounds')==24,'round_count','Exactly 24 original normal rounds must finish')
    require(tuple(r.get('attack') for r in rounds)==EXPECTED_ATTACKS,'round_sequence','Completed rounds differ from the original always-FIGHT normal sequence')
    require(tuple(e.get('param') for e in runs)==EXPECTED_ATTACKS,'run_sequence','Native RunAttack events differ from the 24-round sequence')
    require(len(starts)==24 and len(ends)==24,'boundary_event_count','Expected 24 native StartAttack and EndAttack events')
    valid_rounds=all(_integer(r.get('startTick')) and _integer(r.get('endTick')) for r in rounds)
    require(valid_rounds,'round_schema','Round start/end tick indices are required')
    if valid_rounds:
        for i,r in enumerate(rounds):
            require(r['startTick']<r['endTick'],'round_bounds',f'Round {i+1} has invalid bounds')
            if i:
                require(rounds[i-1]['endTick']<r['startTick'],'round_overlap',f'Round {i+1} overlaps the prior round')
            if i<len(runs):
                require(runs[i].get('tick')==r['startTick'],'run_boundary',f'Round {i+1} does not match native RunAttack')
            if i<len(ends):
                require(ends[i].get('tick')==r['endTick'],'end_boundary',f'Round {i+1} does not match native EndAttack')
            if i<len(starts):
                require(starts[i].get('tick')==r['startTick'],'start_boundary',f'Round {i+1} does not match native StartAttack')
        if rounds and valid_rows:
            require(first_tick<=rounds[0]['startTick']+1,'late_observer','Observer started after the opening attack began')
    require(len(win1)==1 and len(win2)==1,'win_event_count','Exactly one native Win1 and Win2 are required')
    if len(win1)==len(win2)==1 and valid_events and valid_rounds and rounds:
        require(rounds[-1]['endTick']<=win1[0]['tick']<=win2[0]['tick'],
                'win_chain','Victory dialogue must follow the final native EndAttack')
        if valid_rows:
            require(last_tick==win2[0]['tick']+1,'terminal_coverage','Last checked row must be the tick that executed Win2')
    if version in (2,3):
        entry=data.get('entrySnapshot') if isinstance(data.get('entrySnapshot'),dict) else {}
        terminal=data.get('win2Snapshot') if isinstance(data.get('win2Snapshot'),dict) else {}
        require(entry.get('HP')==92 and entry.get('KR')==0 and entry.get('SimulatorMode')==0 and entry.get('HitAttempts')==0,
                'entry_state','Opening native StartAttack snapshot is missing or invalid')
        require(valid_rows and entry.get('tick')==first_tick-1 and bool(runs) and entry.get('tick')==runs[0].get('tick'),
                'entry_coverage','Raw observation did not begin immediately after the opening StartAttack')
        require(terminal.get('HP')==92 and terminal.get('KR')==0 and terminal.get('SimulatorMode')==0 and terminal.get('HitAttempts')==23,
                'win2_state','Native Win2 snapshot is missing or invalid')
        require(len(win2)==1 and terminal.get('tick')==win2[0].get('tick'),'win2_snapshot_tick','Terminal snapshot must belong to Win2')
        for i,event in enumerate(runs):
            require(event.get('HP')==92 and event.get('KR')==0 and event.get('SimulatorMode')==0 and event.get('HitAttempts')==i,
                    'run_snapshot',f'RunAttack {i+1} does not have the original normal progress counter')

    # Retries at a paused boundary are retained as failed attempts. They are
    # neither extra rounds nor successful fresh candidates.
    candidates=([{**p['plan'], 'wave':p.get('wave')} for p in plans
                 if isinstance(p.get('plan'),dict) and p['plan'].get('status')=='candidate_found']
                if version==3 else [p for p in plans if p.get('status')=='candidate_found'])
    require(len(candidates)==24,'candidate_count','Each of the 24 rounds needs one fresh successful candidate')
    require(tuple(p.get('wave') for p in candidates)==tuple(a+'.csv' for a in EXPECTED_ATTACKS),
            'candidate_sequence','Successful candidates do not match campaign rounds in order')
    csv_summary = {}
    if version==3:
        csv_summary = _verify_csv_rounds(data, rounds, plans, raw, events, require, Path(implementation_dir))
        matched_inputs = csv_summary['matched_planned_input_ticks']
    for i,plan in enumerate(candidates if version!=3 else []):
        label=f'Candidate {i+1} ({plan.get("wave")})'
        require(plan.get('route_cache_hit') is False,'cached_route',label+' was not explicitly computed fresh')
        require(plan.get('planner')=='canonical-dag-dp','planner',label+' has an unexpected planner')
        hold=plan.get('control_ticks')
        valid_hold=_integer(hold) and hold in (1,4)
        require(valid_hold,'control_clock',label+' has an unsupported physical control interval')
        actions=plan.get('actions')
        require(isinstance(actions,list) and bool(actions) and all(_integer(a) and 0<=a<32 for a in actions),
                'candidate_actions',label+' has invalid normal-mode physical input masks')
        cap=plan.get('captured') if isinstance(plan.get('captured'),dict) else {}
        require(cap.get('HP')==92 and cap.get('KR')==0,'boundary_damage',label+' was captured after damage')
        require(_finite(cap.get('clock_start_ms')) and cap.get('clock_start_ms')==plan.get('clock_start_ms'),
                'candidate_clock',label+' has inconsistent captured logical time')
        for key,width in (('initial',11),('initial_environment',22)):
            values=cap.get(key)
            require(isinstance(values,list) and len(values)==width and all(_finite(v) for v in values),
                    'captured_state',label+f' lacks a complete finite {key}')
        if i<len(rounds) and valid_rounds:
            require(_integer(cap.get('tick')) and rounds[i]['startTick']<=cap['tick']<rounds[i]['endTick'],
                    'candidate_boundary',label+' was not captured during its matching native attack')
            if raw_verified and valid_hold and _integer(cap.get('tick')) and isinstance(actions,list):
                stop=min(rounds[i]['endTick']+1,cap['tick']+hold*len(actions))
                for t in range(cap['tick']+1,stop+1):
                    offset=t-first_tick
                    if 0<=offset<len(raw):
                        require(raw[offset][5]==actions[(t-cap['tick']-1)//hold],
                                'candidate_input_mismatch',label+f' was not executed at native tick {t}')
                        matched_inputs+=1
        kernel=plan.get('kernel_sha256')
        require(isinstance(kernel,str) and len(kernel)==64 and all(c in '0123456789abcdef' for c in kernel),
                'kernel_hash',label+' lacks its solver implementation hash')

    source_hashes=data.get('source_sha256') if isinstance(data.get('source_sha256'),dict) else {}
    script_hashes=data.get('script_sha256') if isinstance(data.get('script_sha256'),dict) else {}
    verified_sources=[];verified_attacks=[]
    for name in CSV_REQUIRED_SOURCES if version==3 else REQUIRED_SOURCES:
        path=game_dir/name
        if not require(path.is_file(),'source_missing',str(path)):
            continue
        digest=_sha(path)
        require(source_hashes.get(name)==digest,'loaded_source_hash',f'Recorded source hash differs from {path}')
        if name in ('c2runtime.js','data.js'):
            original=original_dir/name
            if require(original.is_file(),'original_missing',str(original)):
                require(digest==_sha(original),'original_runtime_hash',f'{name} differs from the original jcw export')
        verified_sources.append(name)
    for attack in sorted(set(EXPECTED_ATTACKS)):
        name=attack+'.csv';path=game_dir/name;original=original_dir/name
        if not require(path.is_file() and original.is_file(),'original_script_missing',name):
            continue
        digest=_sha(path)
        require(digest==_sha(original),'original_script_hash',name+' differs from the original jcw script')
        require(script_hashes.get(name)==digest,'recorded_script_hash',name+' recorded hash differs from the original')
        candidate_digest = digest
        if version==3:
            candidate_digest = hashlib.sha256(path.read_bytes().decode('utf-8-sig').replace('\r\n','\n').encode('utf-8')).hexdigest()
            text_hashes=data.get('script_text_sha256')
            require(isinstance(text_hashes,dict) and text_hashes.get(name)==candidate_digest,
                    'recorded_script_text_hash',name+' normalized TLPlay source hash differs from the original')
        for plan in candidates:
            if plan.get('wave')==name:
                require(plan.get('csv_sha256')==candidate_digest,'candidate_script_hash',name+' candidate was computed for different source')
        verified_attacks.append(name)

    # Current live rows omit HitAttempts. Only report 23 successful FIGHTs as
    # directly checked when recorded counters include both endpoints.
    attempts=[r[3] for r in raw] if raw_verified else []
    if not attempts:
        for row in rows:
            if 'hitAttempts' in row: attempts.append(row['hitAttempts'])
            elif 'HitAttempts' in row: attempts.append(row['HitAttempts'])
    fight_verified=False
    if attempts:
        valid=all(_integer(v) for v in attempts)
        require(valid and attempts[0]==0 and attempts[-1]==23 and all(a<=b for a,b in zip(attempts,attempts[1:])),
                'fight_count','Recorded HitAttempts do not show monotonic 0 to 23')
        fight_verified=valid and attempts[0]==0 and attempts[-1]==23
    return {'passed':not errors,'errors':errors,'summary':{
        'seed':data.get('seed'),'finished_rounds':len(rounds),'fresh_candidates':len(candidates),
        'failed_search_attempts':len(plans)-len(candidates),'checked_native_ticks':data.get('checkedTicks'),
        'first_tick':first_tick,'last_tick':last_tick,'verified_hp_kr_samples':len(rows),
        'verified_raw_hp_kr_ticks':len(raw) if raw_verified else 0,'matched_planned_input_ticks':matched_inputs,
        'checked_source_files':len(verified_sources),'checked_original_attack_scripts':len(verified_attacks),
        'successful_fights':23 if fight_verified else None,
        'fight_count_evidence':'recorded HitAttempts 0 to 23' if fight_verified else 'HitAttempts not directly recorded',
        **csv_summary,
    },'limits':[
        'Complete per-tick HP/KR, mode and FIGHT counters were recorded and checked.' if raw_verified else
        'Per-tick evidence was supplied but did not pass all checks; see the reported errors.' if version in (2,3) else
        'HP/KR are recorded sparsely; complete per-tick coverage relies on the audited live observer and its counters.',
        'Source hashes attest files recorded at save time, not an independent hash of loaded browser bytecode.',
        'This validates one seeded normal campaign, not every random seed or the optional platformblasterfast attack.',
    ]}


def load_record(path):
    """Resolve a lossless v3 manifest and bind save-time source attestations."""
    path = Path(path)
    data = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(data,dict) or 'storage' not in data:
        return data
    if data.get('storage') != 'json-utf8-parts-v1':
        raise ValueError('Unknown evidence storage protocol')
    from nohit.dashboard.acceptance_evidence import read_evidence_manifest
    restored = read_evidence_manifest(data,path.parent)
    for field in ('source_sha256','script_sha256','script_text_sha256','solver_source_sha256'):
        if not isinstance(data.get(field),dict):
            raise ValueError('Manifest lacks server source attestation: '+field)
        if field in restored and restored[field] != data[field]:
            raise ValueError('Manifest source attestation conflicts with payload: '+field)
        restored[field] = data[field]
    return restored


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('trace',type=Path)
    parser.add_argument('--game-dir',type=Path,default=ROOT/'c2-sans-fight')
    parser.add_argument('--original-dir',type=Path,default=ROOT/'jcw87-c2-sans-fight')
    parser.add_argument('--json-out',type=Path)
    args=parser.parse_args(argv)
    try:
        verdict=verify_record(load_record(args.trace),
                              game_dir=args.game_dir,original_dir=args.original_dir)
    except (OSError,ValueError,TypeError,KeyError,IndexError) as exc:
        verdict={'passed':False,'errors':[{'code':'invalid_record','detail':str(exc)}]}
    verdict['trace']=str(args.trace.resolve())
    output=json.dumps(verdict,ensure_ascii=False,indent=2)
    print(output)
    if args.json_out:
        args.json_out.write_text(output+'\n',encoding='utf-8')
    return 0 if verdict['passed'] else 1


if __name__=='__main__':
    raise SystemExit(main())

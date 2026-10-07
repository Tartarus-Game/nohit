"""Validate the declared execution clock before promoting a TAS witness."""
import math


def validate_compensated_clock(data):
    if data.get('clock') != 'original-runtime-realtime-catchup-240hz':
        return
    stats = data.get('compensation')
    if not isinstance(stats, dict) or stats.get('error') is not None or stats.get('droppedSteps') != 0:
        raise ValueError('Compensation failed or dropped logical steps')
    for run in data['trace']['runs']:
        rows = run['rows']
        for row in rows:
            dt = row.get('dt')
            if not isinstance(dt, (int, float)) or not math.isfinite(dt) or abs(dt - 1 / 240) > 1e-9:
                raise ValueError('Compensated replay changed the logical timestep')
        if any(b['tick'] != a['tick'] + 1 for a, b in zip(rows, rows[1:])):
            raise ValueError('Compensated replay skipped or duplicated observed steps')

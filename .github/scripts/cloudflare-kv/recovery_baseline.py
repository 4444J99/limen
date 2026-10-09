"""Bounded, read-only evidence for the October D1 recovery."""
import datetime as dt
import json
import math

SOURCE = '62469ec5b402460a5610145e67901fcdd0ca00b9'
NOT_BEFORE = 1791590400000  # October 10 00:00 UTC quota reset
CONTROL = "SELECT source_sha,activate_after,enabled FROM ops_control WHERE id='dispatcher'"
QUEUE = """SELECT value AS target,(SELECT scheduled_at FROM ops_runs
 INDEXED BY ops_pending_target_order WHERE target=value AND state='pending'
 ORDER BY scheduled_at,id LIMIT 1) AS oldest_pending_at
 FROM json_each(?) LIMIT 6"""


def read(client, names, now):
    def query(sql, params):
        result = client.request(f'/accounts/{client.aid}/d1/database/{client.db}/query',
            'POST', json.dumps({'sql': sql, 'params': params}).encode())
        if not isinstance(result, list) or len(result) != 1 or result[0].get('success') is not True:
            raise ValueError('recovery_evidence_unavailable')
        return result[0]['results']
    rows = query(CONTROL, [])
    if len(rows) != 1:
        raise ValueError('recovery_control_missing')
    row = rows[0]
    activation = row.get('activate_after')
    if (row.get('source_sha') != SOURCE or row.get('enabled') != 1
        or type(activation) not in (int, float) or not math.isfinite(activation)
        or activation < NOT_BEFORE or activation > now + 16 * 60000):
        raise ValueError('recovery_activation_unverified')
    start = dt.datetime.fromtimestamp(activation / 1000, dt.timezone.utc)
    first = start.date() + dt.timedelta(days=bool(start.time() != dt.time()))
    queues = query(QUEUE, [json.dumps(list(names))])
    if len(queues) != len(names) or {q.get('target') for q in queues} != set(names):
        raise ValueError('recovery_queue_scope_invalid')
    ages = {}
    for q in queues:
        oldest = q.get('oldest_pending_at')
        if oldest is not None and (type(oldest) not in (int, float)
            or not math.isfinite(oldest) or oldest < 0 or oldest > now):
            raise ValueError('recovery_queue_timestamp_invalid')
        ages[q['target']] = round((now - oldest) / 1000) if oldest is not None else None
    return {'source_sha': SOURCE, 'activate_after': activation,
        'first_complete_day': first.isoformat(), 'oldest_pending_age_seconds': ages}

"""Bounded, value-free execution details: distinguish stale verdicts from new attempts."""
import json
import math
import re

TARGETS = ('ucc-staging', 'vulnpulse')
NUMBERS = ('lastInvokedAt', 'lastCompletedAt', 'lastFailureAt', 'lastFailedAt',
           'consecutiveFailures', 'failureCount', 'nextRetryAt', 'backoffUntil',
           'circuitOpenUntil', 'lastDurationMs')
STATUSES = frozenset(('success', 'failure', 'timeout', 'skipped', 'running'))


def numeric(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value >= 0


def project(state, source, acknowledgements):
    rows = state.get('targetStates', {}) if isinstance(state, dict) else {}
    if not isinstance(rows, dict):
        raise ValueError('execution_state_invalid')
    result = {'jobs': {}, 'product_acknowledgements': {}}
    for name in TARGETS:
        row = rows.get(name, {})
        if not isinstance(row, dict):
            raise ValueError('execution_job_invalid')
        result['jobs'][name] = {key: row[key] for key in NUMBERS if numeric(row.get(key))}
        result['jobs'][name]['last_status'] = row.get('lastStatus') if row.get('lastStatus') in STATUSES else 'unknown'
        if isinstance(row.get('inFlight'), bool):
            result['jobs'][name]['in_flight'] = row['inFlight']
    # Only a fixed numeric constant is exposed, never function bodies or config.
    match = re.search(r'\b(?:var|const|let) INVOCATION_TIMEOUT_MS = ([0-9]+);', source)
    result['default_invocation_timeout_ms'] = int(match[1]) if match else None
    result['queue_append_call_present'] = 'await __appendRecoveryTargets(' in source
    result['ucc_extended_timeout_present'] = "target.name === 'ucc-staging' ? 300000 : INVOCATION_TIMEOUT_MS" in source
    for name, row in acknowledgements.items():
        if name not in ('edgarflash', 'vulnpulse') or not isinstance(row, dict):
            continue
        result['product_acknowledgements'][name] = {
            **{key: row[key] for key in ('scheduled_at', 'completed_at') if numeric(row.get(key))},
            'ok': row.get('ok') if isinstance(row.get('ok'), bool) else None,
        }
    return result


def inspect(client, files, settings):
    import release
    bindings = [value for value in settings['bindings']
                if value.get('name') == 'SCHED_DB' and value.get('type') == 'd1']
    if len(bindings) != 1:
        raise ValueError('scheduler_database_unresolved')
    client.db = bindings[0]['database_id']
    state_rows = client.sql(release.STATE, ('scheduler:state',))
    if len(state_rows) != 1:
        raise ValueError('scheduler_state_unobserved')
    state = json.loads(state_rows[0]['payload'])
    acknowledgements = {}
    for name in ('edgarflash', 'vulnpulse'):
        rows = client.sql(release.SELECT, (name, 'last_job'))
        if len(rows) == 1:
            acknowledgements[name] = json.loads(rows[0]['payload'])
    return project(state, files['index.js'].decode(), acknowledgements)

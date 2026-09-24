"""Separate current quota observations from job failures and whole-day acceptance."""
from __future__ import annotations
import datetime as dt
import math

# Cloudflare Workers Free KV/D1 pricing, checked 2026-09-24. These are reporting
# thresholds, never permission to increase spend or bypass a provider limit.
LIMITS = {'kv': {'read': 100000, 'write': 1000, 'list': 1000, 'delete': 1000},
          'd1': {'rowsRead': 5000000, 'rowsWritten': 100000}}
FAILURE_CODES = frozenset(('invocation_request_limit', 'kv_quota', 'authorization',
    'nvd_upstream', 'timeout', 'database', 'ai_upstream', 'binding_missing',
    'unclassified_failure'))
DIAGNOSES = frozenset(('missing_table', 'missing_column', 'missing_function',
    'unknown_insert_column', 'not_null', 'parameter_limit', 'syntax_error',
    'datatype', 'bind_type', 'function_arity', 'foreign_key', 'unique', 'locked',
    'timeout', 'database_unclassified', 'unclassified'))


def safe_failure(value):
    """No raw error text, schema identifiers, tokens or response bodies."""
    if not isinstance(value, dict) or value.get('lastStatus') == 'success':
        return {'failure_code': None, 'failure_category': None}
    code = value.get('lastFailureCode')
    detail = value.get('lastFailureDetail')
    category = detail.get('category') if isinstance(detail, dict) else None
    return {'failure_code': code if isinstance(code, str) and code in FAILURE_CODES else 'unclassified_failure',
            'failure_category': category if isinstance(category, str) and category in DIAGNOSES else 'unclassified'}


def current_quota(days, observed_at):
    """An incomplete day can exceed a budget; it can never certify a full day."""
    stamp = dt.datetime.fromisoformat(observed_at.replace('Z', '+00:00'))
    if stamp.tzinfo is None:
        raise ValueError('observation_timezone_missing')
    stamp = stamp.astimezone(dt.timezone.utc)
    date = stamp.date().isoformat()
    matches = [row for row in days if isinstance(row, dict) and row.get('date') == date]
    result = {'date': date, 'observed_at': observed_at,
              'reset_at': (stamp.date() + dt.timedelta(days=1)).isoformat() + 'T00:00:00Z',
              'state': 'UNOBSERVED', 'metrics': {}, 'unreported_metrics': [],
              'whole_day_verified': False,
              'qualification': 'Adaptive counts through observation time, not exact billing or successful operations. Missing metrics remain unobserved.'}
    if len(matches) != 1:
        return result
    row = matches[0]
    invalid = False
    for store, operations in LIMITS.items():
        observed = row.get(store)
        observed = observed if isinstance(observed, dict) else {}
        for operation, limit in operations.items():
            key = store + '.' + operation
            count = observed.get(operation)
            if count is None:
                result['unreported_metrics'].append(key)
                continue
            if isinstance(count, bool) or not isinstance(count, (float, int)) or not math.isfinite(count) or count < 0:
                invalid = True
                result['unreported_metrics'].append(key)
                continue
            result['metrics'][key] = {'observed': count, 'daily_limit': limit,
                                     'percent_used': round(count / limit * 100, 3)}
    percentages = [value['percent_used'] for value in result['metrics'].values()]
    if any(value >= 100 for value in percentages):
        result['state'] = 'AT_OR_OVER_REPORTED_LIMIT'
    elif any(value >= 80 for value in percentages):
        result['state'] = 'HEADROOM_LOW'
    elif percentages and not invalid:
        result['state'] = 'BELOW_REPORTED_LIMITS_SO_FAR'
    return result


def annotate(report):
    """Keep the existing stricter combined verdict; add explicit failure domains."""
    quota = current_quota(report.get('usage', {}).get('days', []), report['observed_at'])
    jobs = report.get('schedulers', {}).get('ops-scheduler-production', {}).get('jobs', {})
    report['quota_now'] = quota
    report['failed_active_jobs'] = sorted(name for name, item in jobs.items() if not item.get('healthy'))
    report['product_endpoints_ok'] = bool(report.get('products')) and all(
        item.get('liveness_http') == 200 and item.get('status_http') == 200
        and item.get('revision_verified') is True and item.get('snapshot_stale') is False
        for item in report['products'].values())
    # The former classifier considered only completed windows: current-day
    # exhaustion could be hidden behind OBSERVING until the next midnight.
    if quota['state'] in ('AT_OR_OVER_REPORTED_LIMIT', 'HEADROOM_LOW'):
        report['state'] = 'ACTION_REQUIRED'
    return report

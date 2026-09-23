#!/usr/bin/env python3
"""Bounded read-only Cloudflare KV incident preflight. Never emits raw settings."""
from __future__ import annotations
import datetime as dt
import json
import math
import os
import re
import sys
import urllib.error
import urllib.request
from collections import defaultdict

API = 'https://api.cloudflare.com/client/v4'
TARGETS = {
    'edgarflash': '203b71e1e3c88302ca49287c6d8d7cf1f94dd6b0',
    'trendpulse': '3044be554f6d4b1b6e11764b74774054ba18e6e9',
    'vulnpulse': '60248144112ab0d7f54d2cfbc32d89239e825ab8',
}
OPERATIONS = frozenset(('read', 'write', 'delete', 'list'))
QUERY = '''query KvIncident($account: string!, $start: Date!, $end: Date!) {
 viewer { accounts(filter: {accountTag: $account}) {
  kvOperationsAdaptiveGroups(limit: 10000,
   filter: {date_geq: $start, date_leq: $end}) {
   sum {requests} dimensions {date actionType namespaceId}
  }
 } }
}'''

class SafeError(RuntimeError):
    """Messages are fixed codes, never request URLs, settings or vendor bodies."""

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise SafeError('redirect_refused')

OPENER = urllib.request.build_opener(NoRedirect())

def decode_response(response, limit=2_000_000):
    raw = response.read(limit + 1)
    if len(raw) > limit:
        raise SafeError('response_too_large')
    try:
        return json.loads(raw)
    except (ValueError, UnicodeError):
        raise SafeError('invalid_json') from None

class Client:
    def __init__(self, token):
        if not token:
            raise SafeError('credential_missing')
        self.token = token

    def call(self, path, payload=None):
        read_path = (path == '/accounts?per_page=50' or re.fullmatch(
            r'/accounts/[a-f0-9]{32}/workers/(?:subdomain|scripts/(?:edgarflash|trendpulse|vulnpulse)/(?:settings|schedules|deployments))', path))
        if not read_path and not (path == '/graphql' and payload and payload.get('query') == QUERY):
            raise SafeError('endpoint_not_allowlisted')
        if payload is not None and path != '/graphql':
            raise SafeError('mutations_refused')
        req = urllib.request.Request(API + path,
            data=json.dumps(payload).encode() if payload else None,
            headers={'Authorization': 'Bearer ' + self.token,
                     'Content-Type': 'application/json', 'User-Agent': 'organvm-kv-incident/1'})
        try:
            with OPENER.open(req, timeout=20) as response:
                result = decode_response(response)
        except urllib.error.HTTPError as error:
            raise SafeError('provider_http_' + str(error.code)) from None
        except (urllib.error.URLError, TimeoutError):
            raise SafeError('provider_network_error') from None
        if not isinstance(result, dict):
            raise SafeError('provider_shape_invalid')
        if result.get('errors') or result.get('success') is False:
            # Never echo provider messages: they may contain resource IDs.
            raise SafeError('provider_query_rejected')
        return result

    def result(self, path):
        value = self.call(path)
        if 'result' not in value:
            raise SafeError('provider_result_missing')
        return value['result']

    def account(self):
        response = self.call('/accounts?per_page=50')
        accounts = response.get('result')
        if not isinstance(accounts, list) or len(accounts) > 50:
            raise SafeError('accounts_invalid')
        info = response.get('result_info', {})
        if info.get('total_pages', 1) > 1:
            raise SafeError('account_discovery_incomplete')
        candidates = []
        for account in accounts:
            aid = account.get('id', '')
            if not re.fullmatch(r'[a-f0-9]{32}', aid):
                raise SafeError('account_id_invalid')
            try:
                value = self.result(f'/accounts/{aid}/workers/subdomain')
            except SafeError:
                continue
            if isinstance(value, dict) and value.get('subdomain') == 'ivixivi':
                candidates.append(aid)
        if len(candidates) != 1:
            raise SafeError('account_identity_unresolved')
        return candidates[0]


def summarize_operations(rows, owners, today):
    if not isinstance(rows, list) or len(rows) >= 10000:
        raise SafeError('analytics_missing_or_truncated')
    totals = defaultdict(lambda: defaultdict(float))
    products = defaultdict(lambda: defaultdict(lambda: defaultdict(float)))
    for row in rows:
        dims = row.get('dimensions', {})
        operation = dims.get('actionType')
        day = dims.get('date', '')
        count = row.get('sum', {}).get('requests')
        if operation not in OPERATIONS or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', day):
            raise SafeError('analytics_dimension_invalid')
        if isinstance(count, bool) or not isinstance(count, (float, int)) or not math.isfinite(count) or count < 0:
            raise SafeError('analytics_count_invalid')
        owner = owners.get(dims.get('namespaceId'), 'other_namespaces')
        totals[day][operation] += count
        products[day][owner][operation] += count
    return {
        'source': 'kvOperationsAdaptiveGroups',
        'qualification': 'adaptive analytics; not proof of successful operations or an exact billing meter',
        'days': [{'date': day, 'coverage': 'partial_day' if day == today else 'completed_utc_day',
                  'account_operations': dict(totals[day]),
                  'target_namespace_operations': {k: dict(v) for k, v in sorted(products[day].items())}}
                 for day in sorted(totals)],
        'missing_operations': 'not_observed; missing dimensions are not asserted to be zero',
    }


def public_probe(name, path):
    # Fixed public destinations receive NO Cloudflare authentication header.
    req = urllib.request.Request(f'https://{name}.ivixivi.workers.dev{path}',
        headers={'User-Agent': 'organvm-kv-incident/1'})
    try:
        with OPENER.open(req, timeout=15) as response:
            code, data = response.status, decode_response(response, 262144)
    except urllib.error.HTTPError as error:
        code = error.code
        try:
            data = decode_response(error, 262144)
        except SafeError:
            data = {}
    except (SafeError, urllib.error.URLError, TimeoutError):
        return {'state': 'unobserved'}
    if not isinstance(data, dict):
        data = {}
    sample = data.get('_status_snapshot')
    safe_sample = None
    if isinstance(sample, dict):
        observed = sample.get('observed_at')
        safe_sample = {
            'observed_at': observed if isinstance(observed, str) and re.fullmatch(r'[0-9TZ:+.\-]+', observed) else None,
            'stale': sample.get('stale') if isinstance(sample.get('stale'), bool) else None,
        }
    return {'http': code,
            'snapshot_adapter': data.get('revision') == 'kv-list-status-snapshot-v1',
            'snapshot': safe_sample}


def observe(client):
    now = dt.datetime.now(dt.timezone.utc)
    report = {'observed_at': now.isoformat(), 'mode': 'read_only', 'workers': {}, 'mutations': 0}
    account = client.account()
    report['account_identity'] = 'verified_expected_workers_subdomain'
    owners = {}
    for name, sha in TARGETS.items():
        base = f'/accounts/{account}/workers/scripts/{name}'
        worker = {'source_commit': sha}
        try:
            settings = client.result(base + '/settings')
            bindings = settings.get('bindings', [])
            worker['binding_types'] = sorted({b['type'] for b in bindings if isinstance(b, dict) and isinstance(b.get('type'), str)})
            worker['bindings_count'] = len(bindings)
            worker['compatibility_date'] = settings.get('compatibility_date')
            for binding in bindings:
                if binding.get('type') == 'kv_namespace':
                    ns = binding.get('namespace_id')
                    if ns in owners and owners[ns] != name:
                        owners[ns] = 'shared_target_namespace'
                    elif ns:
                        owners[ns] = name
            schedules = client.result(base + '/schedules')
            worker['cron'] = [s['cron'] for s in schedules.get('schedules', [])]
            deployment = client.result(base + '/deployments')
            deployments = deployment.get('deployments', []) if isinstance(deployment, dict) else deployment
            worker['deployment_count_returned'] = len(deployments)
            worker['latest_deployed_at'] = deployments[0].get('created_on') if deployments else None
            worker['liveness'] = public_probe(name, '/healthz')
            worker['status'] = public_probe(name, '/api/status')
        except SafeError as error:
            worker['error'] = str(error)
        report['workers'][name] = worker
    today = now.date().isoformat()
    try:
        result = client.call('/graphql', {'query': QUERY, 'variables': {
            'account': account, 'start': (now.date() - dt.timedelta(days=1)).isoformat(), 'end': today}})
        accounts = result.get('data', {}).get('viewer', {}).get('accounts')
        if not isinstance(accounts, list) or len(accounts) != 1:
            raise SafeError('analytics_account_missing')
        report['usage'] = summarize_operations(accounts[0].get('kvOperationsAdaptiveGroups'), owners, today)
    except SafeError as error:
        report['usage'] = {'state': 'unobserved', 'error': str(error)}
    return report


def main():
    try:
        report = observe(Client(os.environ.get('CLOUDFLARE_API_TOKEN', '').strip()))
    except SafeError as error:
        report = {'mode': 'read_only', 'error': str(error), 'mutations': 0}
    text = json.dumps(report, sort_keys=True, indent=2)
    print(text)
    if os.environ.get('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'], 'a', encoding='utf-8') as handle:
            handle.write('## KV incident preflight\n```json\n' + text + '\n```\n')
    return 1 if 'error' in report or any('error' in v for v in report.get('workers', {}).values()) else 0

if __name__ == '__main__':
    sys.exit(main())

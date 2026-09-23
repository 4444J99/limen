#!/usr/bin/env python3
"""Read-only quota attribution and dispatch topology. No values or source emitted."""
from __future__ import annotations
import concurrent.futures
import datetime as dt
import hashlib
import json
import os
import re
import sys
import urllib.error
import urllib.request
from email import policy
from email.parser import BytesParser
import observe as o

NAME = re.compile(r'[A-Za-z0-9_-]{1,100}')
FEATURES = ('WorkerEntrypoint', 'SchedulerEntrypoint', 'runScheduled', 'runCron',
            'SCHEDULER', 'scheduledTime', 'FleetJob', 'dispatch')

class InventoryClient(o.Client):
    def raw(self, path):
        if not re.fullmatch(r'/accounts/[a-f0-9]{32}/workers/scripts(?:/[A-Za-z0-9_-]{1,100}/(?:settings|schedules|content))?', path):
            raise o.SafeError('inventory_endpoint_refused')
        request = urllib.request.Request(o.API + path, headers={
            'Authorization': 'Bearer ' + self.token, 'User-Agent':'organvm-kv-incident/1'})
        try:
            with o.OPENER.open(request, timeout=20) as response:
                raw = response.read(2_000_001)
                kind = response.headers.get('Content-Type', '')
        except urllib.error.HTTPError as error:
            raise o.SafeError('provider_http_' + str(error.code)) from None
        except (urllib.error.URLError, TimeoutError):
            raise o.SafeError('provider_network_error') from None
        if len(raw) > 2_000_000:
            raise o.SafeError('inventory_response_too_large')
        return kind, raw

    def inventory_result(self, path):
        _, raw = self.raw(path)
        try:
            body = o.object_value(json.loads(raw))
        except (ValueError, UnicodeError):
            raise o.SafeError('inventory_json_invalid') from None
        if body.get('success') is False or body.get('errors'):
            raise o.SafeError('inventory_provider_rejected')
        info = o.object_value(body.get('result_info', {}))
        if info.get('total_pages', 1) != 1:
            raise o.SafeError('inventory_pagination_incomplete')
        return body.get('result')


def source_summary(kind, raw):
    if kind.lower().startswith('multipart/'):
        message = BytesParser(policy=policy.default).parsebytes(
            ('Content-Type: ' + kind + '\r\n\r\n').encode() + raw)
        modules = [part.get_payload(decode=True) or b'' for part in message.iter_parts()]
    else:
        modules = [raw]
    text = '\n'.join(part.decode('utf-8', errors='replace') for part in modules)
    exports = set()
    for block in re.findall(r'\bexport\s*\{([^}]+)\}', text):
        for item in block.split(','):
            name = item.strip().split(' as ')[-1].strip()
            if NAME.fullmatch(name):
                exports.add(name)
    exports.update(re.findall(r'\bexport\s+class\s+([A-Za-z_$][\w$]*)', text))
    return {'module_count':len(modules), 'content_sha256':hashlib.sha256(raw).hexdigest(),
            'exported_symbols':sorted(exports)[:30],
            'feature_presence':{name:name in text for name in FEATURES}}


def collect(client):
    account = client.account()
    root = f'/accounts/{account}/workers/scripts'
    scripts = o.object_rows(client.inventory_result(root))
    if len(scripts) > 80:
        raise o.SafeError('inventory_worker_bound_exceeded')
    names = []
    for script in scripts:
        name = script.get('id')
        if not isinstance(name, str) or not NAME.fullmatch(name):
            raise o.SafeError('inventory_worker_name_invalid')
        names.append(name)

    def worker(name):
        result = {'name':name}
        namespaces = []
        try:
            settings = o.object_value(client.inventory_result(root + '/' + name + '/settings'))
            bindings = o.object_rows(settings.get('bindings'))
            links = []
            for binding in bindings:
                if binding.get('type') == 'kv_namespace':
                    ns = binding.get('namespace_id')
                    if not isinstance(ns, str):
                        raise o.SafeError('inventory_namespace_invalid')
                    namespaces.append(ns)
                if binding.get('type') == 'service':
                    target = binding.get('service')
                    entrypoint = binding.get('entrypoint', 'default')
                    if not isinstance(target,str) or not NAME.fullmatch(target) or not isinstance(entrypoint,str) or not NAME.fullmatch(entrypoint):
                        raise o.SafeError('inventory_service_invalid')
                    links.append({'target':target, 'entrypoint':entrypoint})
            result['service_bindings'] = links
            schedules = o.object_value(client.inventory_result(root + '/' + name + '/schedules'))
            cron = [row.get('cron') for row in o.object_rows(schedules.get('schedules'))]
            if any(not isinstance(c,str) or not re.fullmatch(r'[0-9A-Z*?,/ #\-]{5,100}',c) for c in cron):
                raise o.SafeError('inventory_cron_invalid')
            result['cron'] = cron
            if name in o.TARGETS or cron:
                result['source'] = source_summary(*client.raw(root + '/' + name + '/content'))
        except o.SafeError as error:
            result['error'] = str(error)
        return result, namespaces

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        found = list(pool.map(worker, names))
    owners = {}
    for item, namespaces in found:
        for ns in namespaces:
            owners[ns] = item['name'] if ns not in owners else 'shared_namespace'
    now = dt.datetime.now(dt.timezone.utc)
    payload = {'query':o.QUERY,'variables':{'account':account,
        'start':(now.date()-dt.timedelta(days=1)).isoformat(),'end':now.date().isoformat()}}
    data = o.object_value(client.call('/graphql',payload).get('data'))
    accounts = o.object_rows(o.object_value(data.get('viewer')).get('accounts'))
    if len(accounts) != 1:
        raise o.SafeError('inventory_analytics_account_invalid')
    usage = o.summarize_operations(accounts[0].get('kvOperationsAdaptiveGroups'),owners,now.date().isoformat())
    return {'observed_at':now.isoformat(),'mode':'read_only_inventory','mutations':0,
            'workers':[item for item,_ in found], 'usage':usage}


def main():
    try:
        report = collect(InventoryClient(os.environ.get('CLOUDFLARE_API_TOKEN','').strip()))
    except o.SafeError as error:
        report = {'mode':'read_only_inventory','mutations':0,'error':str(error)}
    except Exception:
        report = {'mode':'read_only_inventory','mutations':0,'error':'inventory_unexpected_failure'}
    text = json.dumps(report,indent=2,sort_keys=True)
    print(text)
    if os.environ.get('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'],'a',encoding='utf-8') as handle:
            handle.write('## KV attribution and dispatch topology\n```json\n'+text+'\n```\n')
    return int('error' in report or any('error' in w for w in report.get('workers',[])))

if __name__ == '__main__':
    sys.exit(main())

"""Read-only, value-free verification of the deployed UCC scheduling contract."""
import hashlib
from email import policy
from email.parser import BytesParser
from pathlib import Path

UCC = 'ucc-mca-edge-staging'
SCHEDULER = 'ops-scheduler-production'
ENTRYPOINT = 'KvIncidentScheduledIngress'
MODULES = frozenset(('index.js', 'finishline.mjs', 'diagnosis.mjs', 'bounded-jobs.mjs'))


def unpack(kind, raw):
    if not kind.lower().startswith('multipart/'):
        return {'index.js': raw}
    message = BytesParser(policy=policy.default).parsebytes(
        ('Content-Type: ' + kind + '\r\n\r\n').encode() + raw)
    result = {}
    for part in message.iter_parts():
        name = part.get_filename() or part.get_param('name', header='content-disposition')
        if name == 'metadata':
            continue
        if name not in MODULES or name in result:
            raise ValueError('unrecognized_runtime_module')
        result[name] = part.get_payload(decode=True) or b''
    if 'index.js' not in result:
        raise ValueError('runtime_main_missing')
    return result


def describe(worker, settings, files, expected_helper):
    bindings = settings.get('bindings')
    if not isinstance(bindings, list) or any(not isinstance(b, dict) for b in bindings):
        raise ValueError('invalid_bindings')
    body = files['index.js'].decode('utf-8')
    helper = 'bounded-jobs.mjs' if worker == UCC else 'finishline.mjs'
    result = {
        'main_module_sha256': hashlib.sha256(files['index.js']).hexdigest(),
        'helper_present': helper in files,
        'helper_matches_accepted_source': files.get(helper) == expected_helper,
        'scheduler_secret_binding_present': any(b.get('name') == 'SCHEDULER_SECRET'
            and b.get('type') in ('secret_text', 'plain_text') for b in bindings),
    }
    if worker == UCC:
        result['named_ingress_declared'] = ENTRYPOINT in body
        result['budget_wrapper_imported'] = './bounded-jobs.mjs' in body
    else:
        matches = [b for b in bindings if b.get('name') == 'UCC_STAGING']
        binding = matches[0] if len(matches) == 1 else {}
        result['ucc_binding_target_correct'] = binding.get('type') == 'service' and binding.get('service') == UCC
        result['ucc_binding_entrypoint_correct'] = binding.get('entrypoint') == ENTRYPOINT
        result['ucc_binding_entrypoint_state'] = ('expected_named' if binding.get('entrypoint') == ENTRYPOINT
            else 'default' if binding and binding.get('entrypoint') in (None, 'default', '') else 'other_or_missing')
    return result


def inspect(client):
    folder = Path(__file__).parent
    result = {}
    for name, helper in ((UCC, 'bounded-jobs.mjs'), (SCHEDULER, 'bounded_finishline.mjs')):
        try:
            files = unpack(*client.raw(client.root + name + '/content/v2'))
            result[name] = describe(name, client.settings(name), files, (folder / helper).read_bytes())
        except Exception:
            # Provider messages and configuration values are never echoed.
            result[name] = {'state': 'runtime_contract_unobserved'}
    return result


def main():
    import json
    import os
    import release
    try:
        report = inspect(release.ReleaseClient(os.environ.get('CLOUDFLARE_API_TOKEN', '')))
    except Exception:
        report = {'state': 'runtime_contract_unobserved'}
    print(json.dumps(report, sort_keys=True, indent=2))
    return int(report.get('state') == 'runtime_contract_unobserved'
               or any(isinstance(v, dict) and v.get('state') for v in report.values()))


if __name__ == '__main__':
    raise SystemExit(main())

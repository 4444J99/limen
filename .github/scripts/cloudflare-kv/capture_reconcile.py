#!/usr/bin/env python3
"""One-shot encrypted readback of the already deployed incident components."""
import base64
import hashlib
import json
import os
from pathlib import Path
import subprocess
import zipfile

TARGETS = ('edgarflash', 'trendpulse', 'vulnpulse', 'ops-scheduler-production',
           'ops-scheduler-staging', 'ucc-mca-edge-staging')
STATE = 'SELECT payload FROM scheduler_state WHERE id=?'


def collect(client):
    records = {}
    for name in TARGETS:
        settings = client.settings(name)
        item = {'modules': {k: base64.b64encode(v).decode() for k, v in client.source(name).items()},
                'settings': settings, 'crons': client.crons(name)}
        if name.startswith('ops-scheduler'):
            database = [b for b in settings['bindings'] if b.get('name') == 'SCHED_DB' and b.get('type') == 'd1']
            if len(database) != 1:
                raise ValueError('expected_scheduler_database_missing')
            client.db = database[0]['database_id']
            item['scheduler_state'] = client.sql(STATE, ('scheduler:state',))
        records[name] = item
    return {'controller_commit': os.environ.get('GITHUB_SHA', ''), 'workers': records}


def encrypt(payload, output, certificate):
    result = subprocess.run(['openssl', 'cms', '-encrypt', '-binary', '-aes-256-cbc',
                             '-outform', 'DER', '-out', str(output), str(certificate)],
                            input=json.dumps(payload).encode(), capture_output=True, timeout=20)
    if result.returncode != 0:
        raise ValueError('readback_encryption_failed')
    return hashlib.sha256(output.read_bytes()).hexdigest()


def main():
    try:
        import release
        folder = Path(os.environ['RUNNER_TEMP'])
        source = Path(__file__).parent
        client = release.ReleaseClient(os.environ.get('CLOUDFLARE_API_TOKEN', ''))
        digest = encrypt(collect(client), folder / 'kv-followthrough.cms', source / 'followthrough-cert.pem')
        # Only already-public controller code; no settings, live source or keys.
        with zipfile.ZipFile(folder / 'kv-public-controller.zip', 'w', zipfile.ZIP_DEFLATED) as archive:
            for item in sorted(source.iterdir()):
                if item.is_file() and item.suffix in ('.py', '.mjs', '.pem'):
                    archive.write(item, item.name)
        report = {'mode': 'encrypted_read_only', 'mutations': 0, 'ciphertext_sha256': digest}
    except Exception:
        report = {'error': 'encrypted_readback_failed', 'mutations': 0}
    print(json.dumps(report, sort_keys=True))
    return int('error' in report)


if __name__ == '__main__':
    raise SystemExit(main())

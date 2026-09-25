#!/usr/bin/env python3
"""Encrypt bounded live-source readback for the incident owner's ephemeral receiver."""
import base64
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import subprocess
import inventory as inv

TARGETS = ('edgarflash', 'trendpulse', 'vulnpulse', 'bountyscope',
           'ops-scheduler', 'ops-scheduler-production', 'ops-scheduler-staging')

def capture(client, output):
    account = client.account()
    records = {}
    for name in TARGETS:
        root = f'/accounts/{account}/workers/scripts/{name}'
        kind, content = client.raw(root + '/content/v2')
        records[name] = {'content_type':kind, 'content':base64.b64encode(content).decode(),
                         'settings':client.inventory_result(root + '/settings')}
    payload = json.dumps({'observed_at':dt.datetime.now(dt.timezone.utc).isoformat(),
                          'workers':records}).encode()
    # Plaintext exists only in runner memory. The archive never includes the
    # API token, and the private decryption key is NOT on GitHub or the runner.
    cert = Path(__file__).with_name('diagnostic-cert.pem')
    result = subprocess.run(['openssl','cms','-encrypt','-binary','-aes-256-cbc',
                             '-outform','DER','-out',str(output),str(cert)],
                            input=payload,capture_output=True,timeout=20)
    if result.returncode:
        raise inv.o.SafeError('source_encryption_failed')
    return {'mode':'encrypted_source_readback','workers':list(TARGETS),'mutations':0,
            'ciphertext_sha256':hashlib.sha256(output.read_bytes()).hexdigest()}

def main():
    try:
        output = Path(os.environ['RUNNER_TEMP']) / 'kv-live-source.cms'
        report = capture(inv.InventoryClient(os.environ.get('CLOUDFLARE_API_TOKEN','')),output)
    except inv.o.SafeError as error:
        report = {'error':str(error)}
    except Exception:
        report = {'error':'source_readback_failed'}
    print(json.dumps(report,sort_keys=True))
    return int('error' in report)

if __name__ == '__main__':
    raise SystemExit(main())

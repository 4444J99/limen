#!/usr/bin/env python3
"""Encrypt existing failure events and the exact failing module for private debugging."""
import base64
import gzip
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
import urllib.request
import telemetry_probe as t


def seal(value, output, cert=None):
    cert=cert or Path(__file__).with_name('diagnosis-receiver.pem')
    packed=gzip.compress(json.dumps(value).encode())
    result=subprocess.run(['openssl','cms','-encrypt','-binary','-aes-256-cbc',
        '-outform','DER','-out',str(output),str(cert)],input=packed,capture_output=True,timeout=20)
    if result.returncode:raise t.s.r.inv.o.SafeError('diagnosis_encryption_failed')
    return {'ciphertext_sha256':hashlib.sha256(output.read_bytes()).hexdigest()}


def collect(client):
    now=int(time.time()*1000)
    query=t.payload('ops-scheduler-production',now)
    query['parameters']['needle']={'value':'drainWebhookDeliveries','isRegex':False}
    request=urllib.request.Request(t.s.r.inv.o.API+f'/accounts/{client.aid}/workers/observability/telemetry/query',
        data=json.dumps(query).encode(),headers={'Authorization':'Bearer '+client.token,'Content-Type':'application/json'})
    with t.s.r.inv.o.OPENER.open(request,timeout=40) as response:body=t.s.r.inv.o.decode_response(response)
    if body.get('success') is False or body.get('errors'):raise t.s.r.inv.o.SafeError('diagnosis_query_rejected')
    events=body.get('result',{}).get('events',{}).get('events')
    if not isinstance(events,list) or len(events)>100:raise t.s.r.inv.o.SafeError('diagnosis_events_invalid')
    kind,raw=client.raw(client.root+'ucc-mca-edge-staging/content/v2')
    return {'events':events,'content_type':kind,'source':base64.b64encode(raw).decode()}


def main():
    try:
        value=collect(t.s.r.ReleaseClient(os.environ.get('CLOUDFLARE_API_TOKEN','')))
        output=Path(os.environ['RUNNER_TEMP'])/'kv-private-diagnosis.cms'
        report={**seal(value,output),'mode':'encrypted_existing_error_readback','mutations':0,
            'events':len(value['events'])}
    except Exception:report={'error':'private_diagnosis_failed','mutations':0}
    print(json.dumps(report));return int('error' in report)

if __name__=='__main__':raise SystemExit(main())

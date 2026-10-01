"""Read-only health of a continuing job: a live lease is not completion."""
import json
import math
import re

STATUSES = frozenset(('success','failure','timeout','skipped','running','uncertain','accepted'))
RUN_ID = re.compile(r'^[a-z][a-z0-9-]*:(?:production|staging):[0-9]{1,16}:(?:scheduled|drain)$')
QUERY = ('SELECT id,target,state,started_at,lease_until,generation FROM ops_runs '
         'WHERE id IN (SELECT value FROM json_each(?)) LIMIT 7')


def timestamp(value):
    return value if type(value) in (int,float) and math.isfinite(value) and 0 < value <= 8640000000000000 else None


def health(name, value, now, freshness_ms, receipt=None):
    status=value.get('lastStatus')
    completed=timestamp(value.get('lastCompletedAt'))
    age=now-completed if completed is not None else None
    recent=age is not None and 0 <= age <= freshness_ms
    running=status=='running'
    started=timestamp(value.get('lastInvokedAt'))
    run_id=value.get('lastRunId')
    valid=False
    if running and isinstance(receipt,dict) and started is not None:
        deadline=timestamp(receipt.get('lease_until'))
        max_lease=330000 if name=='ucc-staging' else 140000
        valid=bool(isinstance(run_id,str) and RUN_ID.fullmatch(run_id)
            and receipt.get('id')==run_id and receipt.get('target')==name
            and receipt.get('state')=='running' and receipt.get('started_at')==started
            and type(value.get('consecutiveFailures')) is int and value['consecutiveFailures']==0
            and value.get('lastFailureCode') in (None,'')
            and type(receipt.get('generation')) is int and receipt['generation']>0
            and deadline is not None and started<=now<=deadline and 0<deadline-started<=max_lease)
    return {'last_status':status if isinstance(status,str) and status in STATUSES else 'unknown',
        'last_completion_age_seconds':round(age/1000) if age is not None else None,
        'in_progress':running,'active_lease_verified':valid,'recent_completion_recorded':recent,
        'healthy':bool(recent and (status=='success' or valid))}


def read_receipts(client, state, names):
    references=[]
    targets=state.get('targetStates',{})
    if not isinstance(targets,dict):raise ValueError('run_state_shape_invalid')
    for name in names:
        value=targets.get(name,{})
        if not isinstance(value,dict):raise ValueError('target_state_shape_invalid')
        if value.get('lastStatus')!='running':continue
        ref=value.get('lastRunId')
        if not isinstance(ref,str) or len(ref)>255 or not RUN_ID.fullmatch(ref) or not ref.startswith(name+':'):
            continue
        references.append(ref)
    if not references:return {}
    if len(references)>6:raise ValueError('run_read_bound_exceeded')
    result=client.request(f'/accounts/{client.aid}/d1/database/{client.db}/query','POST',
        json.dumps({'sql':QUERY,'params':[json.dumps(references)]}).encode())
    if not isinstance(result,list) or len(result)!=1 or result[0].get('success') is not True:
        raise ValueError('run_evidence_query_failed')
    rows=result[0].get('results')
    if not isinstance(rows,list) or len(rows)>6:raise ValueError('run_evidence_incomplete')
    out={}
    for row in rows:
        if not isinstance(row,dict) or row.get('id') not in references or row['id'] in out:
            raise ValueError('run_evidence_scope_invalid')
        out[row['id']]=row
    return out

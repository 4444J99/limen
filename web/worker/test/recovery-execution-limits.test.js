import assert from 'node:assert/strict';
import test from 'node:test';
import { executionAdmission } from '../src/conduct/inventory-admission.js';
const now = new Date('2026-09-16T00:00:00Z');
const policy = {mode:'dispatch', approved_priorities:[{outcome_id:'approved-outcome', enabled:true, work_keys:['approved','renamed']}]};
const packet = {work_key:'approved', execution_hash:'first', retry:{max_attempts:1}, deadline:'2026-09-17T00:00:00Z'};
test('unapproved work and missing production policy fail closed', () => {
  assert.throws(() => executionAdmission({}, {runs:{}}, packet, now), /not_approved/);
  assert.throws(() => executionAdmission(policy, {runs:{}}, {...packet,work_key:'discovery'}, now), /not_approved/);
});
test('restart, replacement, and child share reserved cumulative time', () => {
  const admission = executionAdmission(policy, {runs:{}}, packet, now);
  assert.equal(admission.attempt_deadline, '2026-09-16T00:30:00.000Z');
  const state = {runs:Object.fromEntries([0,1,2,3].map(i => [String(i), {packet,status:'expired',parent_run_id:i ? '0':null,execution_admission:admission}]))};
  const restarted = JSON.parse(JSON.stringify(state));
  assert.throws(() => executionAdmission(policy,restarted,{...packet,parent_run_id:'0'},now), /budget_exhausted/);
  assert.throws(() => executionAdmission(policy,restarted,{...packet,work_key:'renamed',execution_hash:'new'},now), /budget_exhausted/);
});
test('only one changed-input correction and two simultaneous tasks', () => {
  const admission = executionAdmission(policy, {runs:{}}, packet, now);
  const row = {packet,status:'failed',execution_admission:admission};
  assert.throws(() => executionAdmission(policy,{runs:{first:row}},packet,now), /inputs_unchanged/);
  assert.throws(() => executionAdmission(policy,{runs:{first:row,second:row}},{...packet,execution_hash:'new'},now), /retry_exhausted/);
  assert.throws(() => executionAdmission(policy,{runs:{first:{...row,status:'running'},second:{...row,status:'reserved'}}},packet,now), /concurrency_exhausted/);
});

test('operator policy controls execution limits without resetting prior debits', () => {
  const configured = {...policy, execution_limits: {attempt_seconds: 2400, verification_seconds: 900,
    cumulative_seconds: 9600, dispatch_concurrency: 3, recovery_concurrency: 1, max_root_attempts: 3}};
  const admission = executionAdmission(configured, {runs: {}}, packet, now);
  assert.equal(admission.reserved_seconds, 2400);
  assert.equal(admission.verification_seconds, 900);
  assert.equal(admission.attempt_deadline, '2026-09-16T00:40:00.000Z');
  const old = {packet, status: 'failed', parent_run_id: null,
    execution_admission: {...admission, reserved_seconds: 7200}};
  assert.throws(() => executionAdmission({...configured, execution_limits: {
    ...configured.execution_limits, cumulative_seconds: 9500}}, {runs: {old}},
    {...packet, execution_hash: 'changed'}, now), /outcome_budget_exhausted/);
});

test('invalid execution limits cannot silently fall back to defaults', () => {
  for (const limits of [{attempt_seconds: 0}, {attempt_seconds: true}, {attempt_seconds: '2400'},
    {verification_seconds: 1801}, {cumulative_seconds: 1799}, {dispatch_concurrency: 0}, {unknown_limit: 1}]) {
    assert.throws(() => executionAdmission({...policy, execution_limits: limits},
      {runs: {}}, packet, now), /execution_limits_invalid/);
  }
});

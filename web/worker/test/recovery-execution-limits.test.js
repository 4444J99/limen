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

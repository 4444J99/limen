import assert from 'node:assert/strict';
import test from 'node:test';
import { prepareChatPrincipals } from '../provision-chat-principals.mjs';

const registry = JSON.stringify({ schema_version: 'limen.conduct_principal_registry.v1', principals: [
  { principal_id: 'existing', agent: 'codex', surface: 'direct', roles: ['conductor'], bearer: 'existing-test-only-bearer-00000000' },
] });

test('additive dedicated roles and idempotent bearers', () => {
  let count = 0;
  const result = prepareChatPrincipals(registry, () => `test-only-distinct-bearer-0000000${++count}`);
  const rows = JSON.parse(result.serialized).principals;
  assert.deepEqual(rows[0], JSON.parse(registry).principals[0]);
  assert.deepEqual(rows[1].roles, ['observer', 'conductor']);
  assert.deepEqual(rows[2].roles, ['executor']);
  assert.equal(result.executor, rows[2].bearer);
  assert.deepEqual(prepareChatPrincipals(result.serialized, () => { throw Error('must not rotate'); }), result);
});

test('refuses existing broader authority and duplicate credentials', () => {
  let count = 0;
  const result = prepareChatPrincipals(registry, () => `test-only-distinct-bearer-0000000${++count}`);
  const document = JSON.parse(result.serialized);
  document.principals[2].roles.push('compatibility');
  assert.throws(() => prepareChatPrincipals(JSON.stringify(document)));
  assert.throws(() => prepareChatPrincipals(registry, () => 'existing-test-only-bearer-00000000'));
});

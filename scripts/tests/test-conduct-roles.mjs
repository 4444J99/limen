import test from 'node:test';
import assert from 'node:assert/strict';
import { checkRoles } from '../check-conduct-roles.mjs';
import { conductPrincipalRegistryReadback } from '../../web/worker/src/conduct/auth.js';
const principals = [
  { principal_id: 'native', agent: 'codex', surface: 'direct', roles: ['conductor', 'observer'], bearer: 'a'.repeat(32) },
  { principal_id: 'collector', agent: 'codex', surface: 'collector', roles: ['inventory_collector'], bearer: 'b'.repeat(32) },
];
const env = { LIMEN_CONDUCT_URL: 'https://example.invalid', LIMEN_CONDUCT_TOKEN: 'owner',
  LIMEN_CONDUCT_PRINCIPAL_REGISTRY: JSON.stringify({ schema_version: 'limen.conduct_principal_registry.v1', principals }) };
const live = await conductPrincipalRegistryReadback(env);
function fixture(override) {
  return async (url, options) => {
    assert.equal(options.redirect, 'error'); assert.ok(options.signal);
    if (url.pathname.endsWith('principal-registry')) return { ok: true, json: async () => live };
    const collector = options.headers.authorization.endsWith('b'.repeat(32));
    if (options.method === 'POST') assert.equal(options.body, '{}');
    const status = url.pathname.endsWith('capabilities') ? (collector ? 403 : 200)
      : !collector ? 403 : options.method === 'POST' ? 409 : 200;
    return { status: override?.(url, options, status) ?? status };
  };
}
test('probes every installed principal and rejects no inventory', async () => {
  assert.deepEqual(await checkRoles(env, fixture()), { schema: 'limen.conduct-role-acceptance.v1', accepted: true, principals: 2, collectors: 1, probes: 6 });
});
test('unexpected authorization, authentication and availability all fail', async () => {
  for (const status of [200, 401, 500]) {
    await assert.rejects(checkRoles(env, fixture((url, opts, expected) => expected === 403 ? status : expected)), /probe failed/);
  }
});
test('an invalid observation accepted by collector fails', async () => {
  await assert.rejects(checkRoles(env, fixture((url, opts, expected) => expected === 409 ? 200 : expected)), /probe failed/);
});
test('transport failures propagate without a success receipt', async () => {
  await assert.rejects(checkRoles(env, async () => { throw new Error('offline'); }));
});

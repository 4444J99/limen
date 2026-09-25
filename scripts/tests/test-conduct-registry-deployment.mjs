import test from 'node:test';
import assert from 'node:assert/strict';
import { checkAdditiveRegistry } from '../check-conduct-registry-deployment.mjs';
import { conductPrincipalRegistryReadback } from '../../web/worker/src/conduct/auth.js';
const principal = (id, roles = ['conductor']) => ({ principal_id: id, agent: 'codex', surface: 'direct', roles, bearer: id.padEnd(32, 'x') });
const env = principals => ({ LIMEN_CONDUCT_URL: 'https://example.invalid', LIMEN_CONDUCT_TOKEN: 'never-print-me',
  LIMEN_CONDUCT_PRINCIPAL_REGISTRY: JSON.stringify({ schema_version: 'limen.conduct_principal_registry.v1', principals }) });
const source = [principal('owner'), principal('collector', ['inventory_collector'])];
const live = await conductPrincipalRegistryReadback(env(source));
const fetcher = async () => ({ ok: true, json: async () => live });
test('unchanged bindings and additive principal pass', async () => {
  assert.deepEqual(await checkAdditiveRegistry(env(source), fetcher), { preserved: 2, added: 0 });
  assert.deepEqual(await checkAdditiveRegistry(env([...source, principal('new')]), fetcher), { preserved: 2, added: 1 });
});
test('stale cache cannot remove installed collector', async () => {
  await assert.rejects(checkAdditiveRegistry(env([source[0]]), fetcher), /removes/);
});
test('existing bearer rotation or role change is not additive', async () => {
  for (const patch of [{ bearer: 'different'.padEnd(32, 'z') }, { roles: ['observer'] }]) {
    await assert.rejects(checkAdditiveRegistry(env([{ ...source[0], ...patch }, source[1]]), fetcher), /bindings/);
  }
});
test('unavailable and malformed readbacks fail closed', async () => {
  await assert.rejects(checkAdditiveRegistry(env(source), async () => ({ ok: false })), /unavailable/);
  for (const value of [null, {}, { ...live, principals: [live.principals[0], live.principals[0]] }]) {
    await assert.rejects(checkAdditiveRegistry(env(source), async () => ({ ok: true, json: async () => value })), /invalid/);
  }
});
test('credential request forbids redirects and insecure endpoints', async () => {
  await checkAdditiveRegistry(env(source), async (url, options) => {
    assert.equal(url.pathname, '/api/conduct/principal-registry');
    assert.equal(options.redirect, 'error');
    assert.ok(options.signal);
    return fetcher();
  });
  await assert.rejects(checkAdditiveRegistry({ ...env(source), LIMEN_CONDUCT_URL: 'http://example.invalid' }, fetcher));
});

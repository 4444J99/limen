#!/usr/bin/env node
import { pathToFileURL } from 'node:url';
import { configuredConductPrincipals } from '../web/worker/src/conduct/auth.js';
import { checkAdditiveRegistry } from './check-conduct-registry-deployment.mjs';

export async function checkRoles(env, fetcher = fetch) {
  const registry = await checkAdditiveRegistry(env, fetcher);
  if (registry.added !== 0) throw new Error('registry is not fully installed');
  const entries = configuredConductPrincipals(env);
  if (entries.length > 100) throw new Error('principal probe bound exceeded');
  const url = new URL(env.LIMEN_CONDUCT_URL);
  const signal = AbortSignal.timeout(60000);
  let collectors = 0;
  for (const { principal, bearer } of entries) {
    const collector = principal.roles.includes('inventory_collector');
    collectors += Number(collector);
    const probes = [
      ['/api/conduct/capabilities', 'GET', principal.roles.includes('observer') ? 200 : 403],
      ['/api/conduct/inventory/authority', 'GET', collector ? 200 : 403],
      // Missing observation is deliberately invalid: no accepted inventory write.
      ['/api/conduct/inventory/observations', 'POST', collector ? 409 : 403],
    ];
    for (const [path, method, expected] of probes) {
      const response = await fetcher(new URL(path, url), {
        method, headers: { authorization: `Bearer ${bearer}`, 'user-agent': 'limen-conduct-client/1',
          ...(method === 'POST' ? { 'content-type': 'application/json' } : {}) },
        ...(method === 'POST' ? { body: '{}' } : {}),
        redirect: 'error', signal: AbortSignal.any([signal, AbortSignal.timeout(10000)]),
      });
      await response.body?.cancel();
      if (response.status !== expected) throw new Error('principal role probe failed');
    }
  }
  if (!collectors) throw new Error('collector coverage absent');
  return { schema: 'limen.conduct-role-acceptance.v1', accepted: true,
    principals: entries.length, collectors, probes: entries.length * 3 };
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  try { console.log(JSON.stringify(await checkRoles(process.env))); }
  catch { console.error('conduct role acceptance failed; reconcile installed credentials and role boundaries'); process.exitCode = 1; }
}

#!/usr/bin/env node
import { pathToFileURL } from 'node:url';
import { configuredConductPrincipals, conductPrincipalRegistryReadback } from '../web/worker/src/conduct/auth.js';

export async function checkAdditiveRegistry(env, fetcher = fetch) {
  const entries = configuredConductPrincipals(env);
  const url = new URL(env.LIMEN_CONDUCT_URL);
  if (url.protocol !== 'https:' || url.username || url.password || url.search || url.hash ||
      !['', '/'].includes(url.pathname) || !env.LIMEN_CONDUCT_TOKEN) throw new Error('invalid broker configuration');
  const response = await fetcher(new URL('/api/conduct/principal-registry', url), {
    headers: { authorization: `Bearer ${env.LIMEN_CONDUCT_TOKEN}`, 'user-agent': 'limen-conduct-client/1' },
    redirect: 'error', signal: AbortSignal.timeout(10000),
  });
  if (!response.ok) throw new Error('live registry unavailable');
  const live = await response.json();
  if (live?.schema_version !== 'limen.conduct_principal_registry_readback.v1' ||
      !/^[0-9a-f]{64}$/.test(live.configuration_fingerprint || '') ||
      !Array.isArray(live.principals) || !live.principals.length) throw new Error('invalid live registry');
  const ids = live.principals.map(p => p?.principal_id);
  if (ids.some(id => typeof id !== 'string' || !id) || new Set(ids).size !== ids.length) {
    throw new Error('invalid live principal identities');
  }
  const existing = entries.filter(entry => ids.includes(entry.principal.principal_id));
  if (existing.length !== ids.length) throw new Error('candidate removes live principals');
  const principals = existing.map(({ principal, bearer }) => ({ ...principal, bearer }));
  const retained = await conductPrincipalRegistryReadback({
    LIMEN_CONDUCT_PRINCIPAL_REGISTRY: JSON.stringify({ schema_version: 'limen.conduct_principal_registry.v1', principals }),
  });
  if (retained.configuration_fingerprint !== live.configuration_fingerprint) {
    throw new Error('candidate changes live credential or role bindings');
  }
  return { preserved: existing.length, added: entries.length - existing.length };
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  try {
    const result = await checkAdditiveRegistry(process.env);
    console.log(`registry preservation verified: ${result.preserved} existing, ${result.added} additions`);
  } catch {
    // Configuration/provider failures may contain credentials: never echo their exception text.
    console.error('registry deployment refused: reconcile candidate with authenticated live registry');
    process.exitCode = 1;
  }
}

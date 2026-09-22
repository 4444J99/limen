#!/usr/bin/env node
// Authorized local credential preparation only. Deployment retains its live guard.
import { randomBytes } from 'node:crypto';
import { spawnSync } from 'node:child_process';
import { readFileSync } from 'node:fs';
import { homedir } from 'node:os';
import { pathToFileURL } from 'node:url';
import { configuredConductPrincipals } from '../web/worker/src/conduct/auth.js';
import { checkAdditiveRegistry } from './check-conduct-registry-deployment.mjs';

const definitions = [
  { principal_id: 'chatgpt-chat-github', agent: 'chatgpt', surface: 'chat', roles: ['observer', 'conductor'] },
  { principal_id: 'github-actions-chat-executor', agent: 'github_actions', surface: 'workflow', roles: ['executor'] },
];

export function prepareChatPrincipals(raw, generate = () => randomBytes(32).toString('hex')) {
  configuredConductPrincipals({ LIMEN_CONDUCT_PRINCIPAL_REGISTRY: raw });
  const registry = JSON.parse(raw);
  for (const definition of definitions) {
    const existing = registry.principals.find(row => row.principal_id === definition.principal_id);
    if (existing) {
      if (existing.agent !== definition.agent || existing.surface !== definition.surface ||
          JSON.stringify([...existing.roles].sort()) !== JSON.stringify([...definition.roles].sort())) {
        throw new Error('dedicated principal already has incompatible authority');
      }
    } else {
      registry.principals.push({ ...definition, bearer: generate() });
    }
  }
  const serialized = JSON.stringify(registry);
  configuredConductPrincipals({ LIMEN_CONDUCT_PRINCIPAL_REGISTRY: serialized });
  return { serialized, executor: registry.principals.find(row => row.principal_id === definitions[1].principal_id).bearer };
}

function storeCredential(name, value) {
  // set-credential stores shell source: quote the complete value, including JSON.
  const quoted = "'" + value.replaceAll("'", "'\\''") + "'";
  const result = spawnSync('bash', ['scripts/set-credential.sh', name], {
    input: quoted + '\n', encoding: 'utf8', timeout: 10000, stdio: ['pipe', 'pipe', 'pipe'],
  });
  if (result.status !== 0) throw new Error('private credential store failed');
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  try {
    if (process.argv[2] !== '--apply') throw new Error('explicit --apply required');
    const merged = spawnSync('python3', ['scripts/merge-conduct-principal-registry.py'], {
      encoding: 'utf8', timeout: 10000, stdio: ['ignore', 'pipe', 'pipe'],
    });
    if (merged.status !== 0) throw new Error('legacy preservation failed');
    const registry = JSON.parse(merged.stdout);
    // Restore the separately homed collector into the cache, never rotate it.
    if (!registry.principals.some(row => row.principal_id === 'estate-collector')) {
      const serviceToken = process.env.OP_SERVICE_ACCOUNT_TOKEN ||
        readFileSync(`${homedir()}/.config/op/service-account-token`, 'utf8').trim();
      if (!serviceToken) throw new Error('promptless custody unavailable');
      const collector = spawnSync('op', ['read', 'op://Limen-Automation/limen-inventory-collector/password'], {
        env: { ...process.env, OP_SERVICE_ACCOUNT_TOKEN: serviceToken },
        encoding: 'utf8', timeout: 15000, stdio: ['ignore', 'pipe', 'pipe'],
      });
      if (collector.status !== 0) throw new Error('collector custody unavailable');
      registry.principals.push({ principal_id: 'estate-collector', agent: 'codex', surface: 'collector',
        roles: ['inventory_collector'], bearer: collector.stdout.trim() });
    }
    const result = prepareChatPrincipals(JSON.stringify(registry));
    const preservation = await checkAdditiveRegistry({ ...process.env, LIMEN_CONDUCT_PRINCIPAL_REGISTRY: result.serialized });
    storeCredential('LIMEN_CONDUCT_PRINCIPAL_REGISTRY', result.serialized);
    storeCredential('LIMEN_CHAT_EXECUTOR_TOKEN', result.executor);
    console.log(`Private Chat principals prepared; ${preservation.preserved} live principals preserved. No deployment or Chat activation performed.`);
  } catch {
    console.error('Chat principal preparation refused; inspect registry compatibility and authenticated preservation guard. No secret values logged.');
    process.exitCode = 1;
  }
}

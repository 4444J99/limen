# Pain Point Ownership

> Relocated verbatim from `AGENTS.md` (2026-08-06) under the instruction-surface byte budget
> (`institutio/governance/gates.yaml` → `instruction_surfaces`, check S). The binding stub in
> `AGENTS.md` points here; this file is the full doctrine.

Every repeated pain point needs an owner. Missing scopes, stale profile metadata, disk pressure,
credential/token hygiene, contribution imbalance, voice/temp failure, and queue/lane drift are not
chat-only blockers.

- Put each pain point in the repo that owns the fix: issue, task packet, PR, pinned wall, or receipt.
- Credential, token, secret, API-key, login, and env-var problems belong to the credential wall owner;
  never paste values into chat, tasks, commits, or PRs.
- 1Password access is a one-touch owner transaction, never a discovery or retry loop. Consume the
  mode-`600` private cache first. If promptless access cannot read the registered item, record that
  owner gate once and continue independent work; do not fall back to repeated desktop-backed
  `op` item/vault probes. An explicitly authorized rotation may perform one owner-native transaction,
  hydrate the cache, verify the named service predicate, and then stop touching 1Password.
- A blocker is incomplete unless it names the owning repo/surface, the failed predicate, and the next
  command that would clear it.
- If the same pain point appears twice, update the owner receipt instead of explaining it again.
- Default toward productizing the fix: split private adapters from reusable public shells, publish a
  redacted demo or method when safe, and route the outward-facing value surface through the owner repo.

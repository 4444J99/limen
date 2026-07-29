# S0 — Corpus custody: teach the registry where the store actually lives

## Objective

`institutio/governance/corpora.yaml` declares the `conversations-private` store at
`~/Workspace/_conversations-private` with `remote: none`. **That path does not resolve.**

The store was evacuated 2026-07-27 by the laptop-evacuation custody lane (PR #1604,
`cli/src/limen/personal_custody.py`, `docs/storage-evacuation-custody-receipts-20260727.jsonl`) to
`/Volumes/T7Recovery/laptop-evacuation/20260727/objects/repo_conversations-private/35ab2f20…/`.
Contents verified intact on 2026-07-29: `brainstorm-extracts/` (541 `.md`, 4,099 atoms),
`homing.yaml`, `convergence-candidates.yaml`, three `*-local-session-memory/`, `federation/`,
`state/`, `reports/`.

**The evacuation is correct.** `docs/repository-evacuation-inventory-20260727.json` declares
`projection_privacy.contains_private_paths: false` — private roots are deliberately absent from the
public projection and live in a private inventory required for reclaim. Do not fight that design,
and do not copy private paths into a projection that excludes them by contract.

**The defect** is that `corpora.yaml` is a *public* registry naming that root directly, and it was
never taught about custody. `scripts/check-corpora.py` passes checks A–E today because it never
asserted a root **resolves**. A registry that green-lights a store nobody can open is the bug.

Re-measure every claim above before acting on it. This document is a hypothesis until you verify it.

## Mission

Make the store addressable through declared data, and make an unresolvable root RED.

1. **Teach `corpora.yaml` about custody.** A store gains a custody state (`resident | evacuated`)
   and, when evacuated, the declared handle the custody lane already owns — inventory id and object
   digest, *not* a hand-copied volume path if that would contradict the public projection's privacy
   contract. Read `personal_custody.py` and the receipts JSONL first and reuse **its** vocabulary;
   do not invent a second custody schema.
2. **Add check F to `scripts/check-corpora.py`:** every store either resolves at its root or carries
   a valid custody record a reclaim command can act on. It must run **store-free** in CI (no external
   volume there) and degrade to declared data — never to a filesystem probe that is vacuously true on
   a runner.
3. **Give it a reclaim verb** a cold session can execute: one command that takes the custody record
   and makes the store resident again, so S1–S5 are unblocked by a documented verb rather than by
   somebody remembering which drive.

## Authorities and prohibitions

- Proceed without confirmation for in-scope reversible registry and predicate work.
- Retained gates: destructive, credential, paid-spend, public-send, runtime/host mutation.
- **Do not touch atom content.** Do not move, rewrite, re-harvest, or re-atomize a single extract.
  This domain makes the store *findable*; it homes nothing.
- Do not restore the store into the public tree. Atom statement text may never enter
  `organvm/limen`. `corpora.yaml` publishes — keep it PII-clean.

## Fan-out

This umbrella may open at most **4** children, and only via `limen conduct split <parent_run>
--packet` — which reserves the child against this session's lineage before anything launches.
Never open a child by nesting a git worktree inside this one: `worktree_roots.iter_worktree_targets()`
sweeps *roots*, so a nested worktree is invisible to the reclaim organ and leaks. Tier every child
explicitly; no worker inherits this session's model.

## Constraints

Fresh branch `heal/corpora-custody-aware` off updated `origin/main`, one concern. Gate with
`scripts/verify-scoped.sh`. Merge via `scripts/merge-policy.sh` → `scripts/await-pr.sh <PR#> --merge`.
**Include the string `s0-corpus-custody` in the merge commit subject** — the STREAMS registry derives
this domain's settled state from `git log origin/main --grep=s0-corpus-custody`.

## Done

`scripts/check-corpora.py` exits 0 with check F present and passing; a store whose root neither
resolves nor carries a valid custody record makes it exit **nonzero** — prove this by actually
testing the failure mode, not by reading the code; `scripts/check-gates.py` green; re-running mutates
nothing.

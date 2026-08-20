# Omega literal-substrate continuation

## Objective

Converge the live laptop from the legacy Workspace surface to the literal
container hierarchy declared by PORTVS, without moving an active session,
discarding unique repository state, or relocating private payloads before their
two-copy restoration gates pass. The implementation phase is complete: PORTVS
declares and additively creates the tree, Domus classifies the exact Home
surface, and Limen independently audits both physical residency and custody.

## Current evidence

- Limen live court:
  [`live-substrate-report.json`](live-substrate-report.json), owned by
  [organvm/limen#1705](https://github.com/organvm/limen/pull/1705)
- PORTVS additive bootstrap report:
  [organvm/portvs#6](https://github.com/organvm/portvs/pull/6),
  `docs/continuations/omega-substrate-literal/live-bootstrap-report.json`
- Domus exact Home report:
  [organvm/domus-genoma#361](https://github.com/organvm/domus-genoma/pull/361),
  `docs/continuations/omega-substrate-literal/live-home-report.json`
- Protected Claude lineage: private receipt
  `.limen-private/session-corpus/omega-substrate-literal/protected-sessions.json`
- Remaining gates:
  [`migration-blockers.json`](migration-blockers.json)

## Authority and ownership

- PORTVS owns `governance/workspace-manifest.yaml` and `jack.sh`.
- Domus owns `dot_config/domus/home-surface.yaml` and the Home guard.
- Limen owns the recursive convergence court, custody registry, residue caps,
  and final Omega trial receipts.
- TABVLARIVS alone owns task lifecycle transitions. The conduct bridge was not
  configured during this direct session, so no broker state was fabricated.

## Prohibitions

- Do not move or reap a path used by a live Claude, Codex, or other provider
  process.
- Do not move `_life-private`, `_finance-private`, `_health-private`, or
  `_people-private` until both independent copies and a successful restoration
  receipt are present in Limen's custody registry.
- Do not delete legacy roots, unique runtime state, dirty repositories, stashes,
  or unpushed commits.
- Do not edit `tasks.yaml`, manufacture green environment state, or weaken the
  zero-residue caps.
- Do not hydrate archived repositories under `library/underworld`.

## First probes

From the Limen continuation worktree:

```bash
python3 scripts/substrate-convergence.py --manifest "$HOME/Workspace/4444J99/portvs/.worktrees/omega-substrate-literal/governance/workspace-manifest.yaml" --json
python3 scripts/check-substrate-paths.py --json
bash "$HOME/Workspace/4444J99/portvs/.worktrees/omega-substrate-literal/jack.sh" --plan --json
python3 "$HOME/Workspace/domus-genoma/.worktrees/omega-substrate-literal/dot_local/bin/executable_domus-home-guard.tmpl" --check --json
```

Use the explicit PORTVS worktree manifest above until organvm/portvs#6 places
the manifest at its canonical `PORTVS_ROOT`; the command's built-in fallback is
deliberately canonical and must not silently fall back to the legacy checkout.

Re-derive active CWDs, live remotes, dirty/unpushed state, custody receipts,
available storage, and provider headroom before every routing batch. Completed
green shard receipts remain valid until their exact owner tree changes.

## Terminal predicate

Close only when all of the following are true on live state:

1. PORTVS verification reports an exact manifest/tree match and a second
   bootstrap plan has zero actions.
2. Domus reports zero undeclared Home entries, zero pending routes, and `_portal`
   is the only architectural doorway.
3. Limen reports zero violations, zero unmeasured state, zero compatibility
   links, no root-level or undeclared repositories, and verified custody for all
   private roots.
4. Internal storage has two readings of at least 200 GiB, at least 30 minutes
   apart.
5. The existing eight-hour trial succeeds, followed by two unchanged
   convergence passes.

## Session-switch conditions

Emit a successor before the finite runway expires. Switch sessions rather than
crossing a protected-process boundary, an unresolved private restoration gate,
a credential/public-send/paid-spend gate, or host admission pressure. Preserve
the current receipt set; do not rerun unchanged successful shards.

## Launch

```bash
workspace_root="${WORKSPACE_ROOT:-$HOME/Workspace}"
canonical_limen_root="${LIMEN_ROOT:-$workspace_root/library/engine/organvm/limen}"
canonical_capsule="$canonical_limen_root/.worktrees/omega-substrate-literal"
legacy_capsule="$workspace_root/limen/.worktrees/omega-substrate-literal"
if [[ -x "$canonical_capsule/.limen-workstream/kickstart.sh" ]]; then
  capsule_root="$canonical_capsule"
elif [[ -x "$legacy_capsule/.limen-workstream/kickstart.sh" ]]; then
  capsule_root="$legacy_capsule"
else
  printf 'Omega substrate capsule is unavailable at canonical and migration paths\n' >&2
  exit 1
fi
cd "$capsule_root" && bash .limen-workstream/kickstart.sh
```

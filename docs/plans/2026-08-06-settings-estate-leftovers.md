# Settings-estate leftovers: heal the keystone PR, expand the predicates, evolve the sensors

Issue: #1898
PR: (pending)

## Context

The 2026-08-06 settings-estate session closed its ledger with 5 items repaired and 5 leftovers.
This plan takes the leftovers to full heal, then expands each fix to its general form, then
evolves the system so the defect class cannot silently recur. Ground truth was re-derived this
session — three ledger assumptions have already drifted:

- **PR #1896 is BLOCKED, not merely queued.** `merge-policy.sh 1896` → exit 3. The two "failing"
  required-scope checks are CodeQL Analyze jobs whose real conclusion is **cancelled** (41-minute
  runs — infra, not code), and `pr-gate` — the check branch protection actually requires — **never
  ran on this head** (e04ad53c, now 3 behind `origin/main`). The predicate's own BLOCKED text
  names the repair: update the branch to retrigger pr-gate. "Owner: the beat's merge rung" was
  wrong the moment the head went stale — the rung drains green PRs; it does not repair blocked ones.
- **The lever entry itself rides the blocked PR.** `L-CLAUDE-SETTINGS-ESTATE-INSTALL` exists only
  in `his-hand-levers.json` *on the PR branch* — main has no trace. Until #1896 merges, the
  install atom (issue #1897) is homed in an unmerged ref, which `no-tasks-on-me.sh` on main
  cannot see. Item 4's "lever graph 0 dangling" is true only on the branch.
- **The "9 lingering landed branches" have changed class.** `reap-branches.py` dry-run now
  reports **0 reapable, 8 merged-advanced** (PR merged but the branch advanced past the merge
  point). `--apply` would reap nothing — the remedy the ledger recorded no longer exists. Each of
  the 8 needs a disposition (salvage the advanced commits as a fresh PR, or accepted delete),
  which is exactly the shape of `GITVS-UNCAPPED-PR-DEBT-0715` (owner-route the whole PR estate).

**The keystone is PR #1896**: merging it simultaneously heals the lever-graph home (ledger 4/6),
lands `plansDirectory: docs/plans` (ledger 10), and clears the merge item (ledger 8). Everything
else sequences after it.

## Heal (this session + the beat)

1. **Un-block #1896** — `gh pr update-branch 1896` (merge-update; no force-push). Retriggers
   `pr-gate` and a fresh CodeQL run on a current base.
2. **Gate → merge** — `scripts/merge-policy.sh 1896`; on CLEARED run
   `scripts/await-pr.sh 1896 --merge` (single bounded waiter). If the deadline passes, the
   green-but-pending PR is homed with the merge rung (`merge-drain.py` via `drain.sh`) — cite and end.
3. **Post-merge lever verification** — `scripts/no-tasks-on-me.sh` on main must see
   L-CLAUDE-SETTINGS-ESTATE-INSTALL → issue #1897 with zero dangling levers.

## Expand (implementing PR, sequenced after the keystone merge)

4. **plansDirectory parity predicate** — a small check (GATES-registry entry + script, the
   registry pattern: one `gates.yaml` entry, never a hand-wired block) asserting
   `.claude/settings.json → plansDirectory` == the charter's declared plan home (`docs/plans`)
   == where `check-session-phase.py` actually reads. Today that parity is prose; ledger item 10
   ("needs a fresh session to observe") exists precisely because nothing machine-checks it.
5. **Merged-advanced owner-route** — extend `scripts/reap-branches.py` (or a sibling triage
   emitter) to output one disposition packet per merged-advanced branch: `{branch, merged PR,
   advanced-commit count, diffstat}` → each becomes either a salvage PR or an acceptance-ledger
   delete entry. Delete-class execution stays receipt-backed and human-cadenced; the *packets*
   are the expand. Link, don't claim: this feeds `GITVS-UNCAPPED-PR-DEBT-0715` [critical].

## Evolve (make the class impossible)

6. **Install-state beat sensor** — the liveness check's dual-phase behavior (source-path arg
   pre-install; bare invocation against `~/.claude/hooks/…` post-install) becomes one
   `sensors.yaml` entry (`claude-hooks-liveness`): NOT-INSTALLED / ALL PASS / FAIL as a beat
   fact. The lever's pull-state then surfaces on the beat log instead of living in session
   memory — the operator reads owed work on his cadence; the beat reads install state on its own.
7. **Cancelled ≠ failed in merge-policy** — candidate refinement: a required-scope check whose
   conclusion is `cancelled` (vs `failure`) is infra-shaped; `merge-policy.sh` could classify it
   as retriable (HOLD-with-rerun guidance) instead of folding it into `failing=N`. Small,
   fail-toward-caution preserved (still never CLEARED on a cancelled check). Scope-check before
   building: confirm the fallback `scope=all` derivation was the reason CodeQL counted at all.

## Human-gated residue (already homed — no session action)

- **The install itself** (template swap + `chezmoi apply`): lever
  `L-CLAUDE-SETTINGS-ESTATE-INSTALL` / issue #1897. Classifier-gated self-modification boundary.
- **Liturgy line 51's over-broad `*.plist` claim**: nuance recorded in the lever's note; lands
  with the install. Post-install acceptance includes verifying the corrected text renders.
- Neither is recited at the operator; both are read from the registry on his cadence.

## Done predicate

- `scripts/merge-policy.sh 1896` path resolved: PR MERGED (or homed with the merge rung, cited).
- Post-merge `scripts/no-tasks-on-me.sh` exit 0 on main with the lever visible.
- Expand/evolve items 4–7 land as their own topic branches (one concern per branch), each with
  its GATES/SENSORS registry entry where applicable; this plan's `PR:` line stamps the first
  implementing PR via `scripts/session-plan.py close`.

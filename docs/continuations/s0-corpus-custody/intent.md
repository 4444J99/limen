# S0 — Corpus custody: teach the registry where the store actually lives

> ## ⛔ STOP — RE-MEASURED 2026-07-29: ALL THREE MISSION ITEMS ARE ALREADY DELIVERED
>
> This cartridge was written to be loaded **cold**, so a false premise here gets *executed*, not
> caught — and an 8-hour runway would be spent rebuilding shipped work. Re-measured against
> `origin/main`, every command reproducible:
>
> | mission item | status | evidence |
> |---|---|---|
> | 1. teach `corpora.yaml` about custody | **delivered as a dedicated registry** (#1615, the CUSTODY axis) | `institutio/governance/custody.yaml` → `roots.conversations-private`: `class: archive`, `custody_label: repo_conversations-private`, `vault: arca`, and `referenced_by: ["institutio/governance/corpora.yaml::stores.conversations-private"]`. `scripts/reference_state.py` is the resolver that reads it. |
> | 2. add a check that an unresolvable root is RED | **delivered as check B, not a new check F** | `scripts/check-corpora.py:122-131` — `UNACCOUNTED` ⇒ `fail`, `ARCHIVED` ⇒ advisory |
> | 3. give it a reclaim verb a cold session can execute | **delivered** | `scripts/arca.sh restore <store> [dest]` (`:29`, `:164`; cost measured in #1618) |
>
> Reproduce:
>
> ```bash
> ls -d ~/Workspace/_conversations-private        # → No such file (the root still does not resolve)
> python3 scripts/check-corpora.py                # → exit 0, with: B: store 'conversations-private'
>                                                 #   root is archived off-host: 2 receipt(s);
>                                                 #   restoration verified, 2 copies on independent
>                                                 #   devices (1763 files)
> sed -n '98,110p' institutio/governance/custody.yaml   # → the declared archive record
> sed -n '29p;229,235p' scripts/arca.sh                 # → the restore verb and the verb table
> ```
>
> ⚠️ **Never invoke `scripts/arca.sh` with no arguments to "see its usage."** `:46` is
> `CMD="${1:-backup}"` — a bare invocation defaults to **`backup`** and starts one. There is no
> `--help`; read the verb table at `:229-235` instead. Verified 2026-07-29 by doing it wrong.
>
> **Do NOT add a custody field to `corpora.yaml`.** Item 1 below warned against inventing a second
> custody schema, and that warning now cuts against item 1's own wording: `custody.yaml` already
> owns the record *and* points at `corpora.yaml` through `referenced_by`, so the link exists — in the
> right direction. A parallel field in the public corpus registry would be exactly the second source
> of truth `check-corpora.py`'s check D exists to forbid.
>
> **`cli/src/limen/personal_custody.py` is not the reclaim verb.** It is the evacuation lane that
> *produced* the receipts (#1604), and it does expose a `reclaim` subcommand — which is why a first
> pass at this table named it. The verb a cold session should run for this store is `arca.sh restore`.
> Checking that `python3 -m limen.personal_custody --help` succeeds proves only that the module
> exists, not that it is the documented path; that is the same "confirmed it with the one input that
> could not fail" error this cartridge is being corrected for.
>
> **What actually remains: nothing this domain must build.** The store is archived with verified
> restoration on two independent devices and a reclaim verb that acts on it, which is the declared-data
> answer item 2 asked for. This domain's correct disposition is **settlement**, and it should be
> settled by a predicate that proves the above rather than by a commit that merely names it — see
> `docs/plans/2026-07-29-session-streams-alpha-to-omega.md` §Phase 1/1a. Until that lands, do not
> open this domain to redo delivered work; if you open it at all, open it to *prove* the table above.
>
> Everything below is the original 2026-07-29 authoring, retained as provenance. Where it and this
> block differ, **this block wins** — it was measured later.

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
**Claim the settlement with an anchored trailer in the merge commit message** — a line at
column 0 reading `Settles: s0-corpus-custody`. The STREAMS registry derives this domain's settled
state from that claim, and *only* from it: an unanchored mention no longer counts (it once
settled `s10-axis-coverage` off a docs commit that merely named it). The claiming commit must
also change something outside the registry and `docs/{plans,continuations}/` — bookkeeping
records an outcome, it cannot produce one.

## Done

`scripts/check-corpora.py` exits 0 with check F present and passing; a store whose root neither
resolves nor carries a valid custody record makes it exit **nonzero** — prove this by actually
testing the failure mode, not by reading the code; `scripts/check-gates.py` green; re-running mutates
nothing.

# GitHub-universe mission

This document is the mechanism reference for the cross-repo GitHub-universe mission. The principle source is the user-global Copilot doctrine at [`/Users/4jp/.copilot/copilot-instructions.md`](file:///Users/4jp/.copilot/copilot-instructions.md): "we do not close, we work it, we evolve it... closing and deleting is never permitted (logically)—if it was ever asked for it was wanted." In Limen terms, this extends [`AGENTS.md` → `Full Lifecycle Closure`](../AGENTS.md#full-lifecycle-closure) from local prompts / branches / worktrees to GitHub-native Issues, Pull Requests, branches, and repositories across the `organvm` + `4444J99` universe.

## Canonical sources

- Principle source: [`/Users/4jp/.copilot/copilot-instructions.md`](file:///Users/4jp/.copilot/copilot-instructions.md)
- Repo-local pointer: [`.github/copilot-instructions.md`](../.github/copilot-instructions.md)
- Prior art generalized here: [`AGENTS.md` → `Full Lifecycle Closure`](../AGENTS.md#full-lifecycle-closure)
- Instruction-surface convention and citation style: [`docs/agent-instruction-standard.md`](./agent-instruction-standard.md)
- Mechanism implementation: [`scripts/github-universe-sweep.py`](../scripts/github-universe-sweep.py)
- Durable ledger: [`github-universe-ledger.json`](../github-universe-ledger.json)

## No-dismissal rule

Do not re-copy the full doctrine here; treat the global Copilot doctrine as canonical. The operative summary is:

- allowed: advancing an item directly, merging when the work is truly complete, or superseding with explicit lineage;
- forbidden: `wontfix`, `duplicate`, `stale`, `not planned`, silent closeouts, deletion-as-escape, or any other dismissal vocabulary used as forgetting;
- retroactive scope: historically closed or dismissed Issues / PRs are still in scope for slow re-engagement, audit, or successor linkage;
- reference-data distinction: GitHub's `state=closed` may appear in source data, but `closed` / `dismissed` are not valid doctrine dispositions for the engagement ledger.

## Mechanism

### Sweep script

`scripts/github-universe-sweep.py` is the enumerator. It scans the live GitHub estate, records item-granularity rows in `github-universe-ledger.json`, and optionally emits bounded task-upsert signals for already-ranked repos.

Current CLI surface (from the script itself):

```bash
python scripts/github-universe-sweep.py \
  [--tasks PATH] \
  [--ledger PATH] \
  [--max-new N] \
  [--since-repo FULL_NAME] \
  [--repo OWNER/NAME ...] \
  [--include-forks] \
  [--retroactive] \
  [--apply] \
  [--emit-tasks] \
  [--max-task-upserts N]
```

Flag semantics:

- `--repo`: repeatable repo filter; scan only the named repo(s).
- `--since-repo`: inclusive lexical resume seam for deterministic repo order.
- `--max-new`: hard cap on newly added ledger rows in one run; default `200` (or `LIMEN_GITHUB_UNIVERSE_MAX_NEW`).
- `--retroactive`: for previously unseen `state=closed` items, seed ledger rows as `reopen-candidate` instead of ignoring them.
- `--apply`: write `github-universe-ledger.json` atomically; without it, the sweep is read-only.
- `--emit-tasks`: only valid with `--apply`; emits bounded TABVLARIVS task-upserts for newly seen open items in already-ranked repos only.
- `--max-task-upserts`: cap emitted ranked-repo task upserts in one run; default `25`.
- `--include-forks`: include fork repos in enumeration.

Operational properties from the script docstring matter too: stable deterministic repo order, fail-open per repo/API call, read-only default, and resume seams so the beat can continue without flooding.

### Ledger schema

`github-universe-ledger.json` is currently schema version `limen.github_universe_ledger.v1`.

Top-level shape:

- `_doc`: human-readable schema/discipline note; treat it as authoritative commentary for the current file format.
- `schema_version`: currently `limen.github_universe_ledger.v1`.
- `items`: object keyed by `<owner/repo>#<number>`.

Per-item fields written by the sweep today:

| Field | Meaning |
|---|---|
| `repo` | Full repo name (`owner/name`) |
| `number` | Issue or PR number |
| `kind` | `issue` or `pr` |
| `title` | Current GitHub title |
| `url` | HTML URL |
| `state` | Source GitHub state (`open` or `closed`) |
| `created_at` | GitHub creation timestamp |
| `updated_at` | GitHub update timestamp |
| `comments` | GitHub comment count |
| `reaction_count` | GitHub total reaction count |
| `priority` | Current cheap rank signal: age in days + `3*comments` + `2*reaction_count` |
| `disposition` | Doctrine-facing engagement state |
| `first_seen` | First ledger sighting time |
| `last_seen` | Most recent sweep sighting time |

### Dispositions

The current working disposition vocabulary across the doctrine file, repo pointer, and ledger `_doc` is:

- `queued`
- `engaged`
- `evolving`
- `distilled`
- `merged`
- `reopen-candidate`
- `superseded:<durable-receipt>`

Constraints:

- `queued` is the default seed for newly seen open items.
- `reopen-candidate` is the retroactive seed for previously unseen closed items when `--retroactive` is used.
- `closed` and `dismissed` are forbidden as ledger dispositions.
- GitHub state remains reference data; doctrine disposition carries the engagement truth.

### Task emission and the value gate

The sweep does **not** bypass `value-repos.json`.

- Ranked repos: `--emit-tasks --apply` may submit bounded task-upsert signals for newly seen open items.
- Unranked repos: open PRs / Issues still enter `github-universe-ledger.json`, but only as discovery signals for later ranking and intake.
- Therefore an open item on an unranked repo is evidence that the repo is live, not permission to spend budget silently. The fail-closed repo-priority guard remains intact.

## Known coordination conflict

There is an active coordination item with the Claude-hosted stale-PR cloud routine tracked at `4444J99/session-meta#36` / `organvm/session-meta#36` (`stale-pr-sweep`). That routine was found recommending closing or merging stale PRs, which conflicts with the no-dismissal doctrine above. A coordination comment has already been posted there. Treat this as a live unresolved coordination point: do not assume the cloud routine has been brought into compliance yet, and do not silently override the conflict without lineage.

## How a future session picks up work

1. Read the principle source at [`/Users/4jp/.copilot/copilot-instructions.md`](file:///Users/4jp/.copilot/copilot-instructions.md), then this mechanism file.
2. Read [`github-universe-ledger.json`](../github-universe-ledger.json) and sort `items` by `disposition` and `priority`.
3. Prefer the highest-priority reasonable `queued` rows first; use `reopen-candidate` for retroactive audit lanes.
4. Read the full GitHub context for the chosen item, derive the real intent, and take the smallest sound advancing action.
5. Update the ledger durably: preserve `first_seen`, refresh `last_seen`, and move `disposition` forward (`queued` → `engaged` / `evolving` / `distilled` / `merged` / `superseded:<receipt>`) rather than dismissing the row.
6. If the repo is ranked and warrants bounded follow-up, let the normal task pipeline carry it; if unranked, treat the row as discovery/ranking evidence until the repo earns budget.

If/when a recurring schedule is wired around the sweep, that schedule should keep re-running enumeration, refreshing `last_seen`, seeding new rows, and emitting only ranked-repo tasks automatically. Sessions then work from the ledger rather than re-deriving the universe ad hoc.

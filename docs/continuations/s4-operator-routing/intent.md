# S4 — Operator routing: 1,067 atoms without handing him a list

## Precondition

`s1-homing-spine` merged. `institutio/governance/atom-homing.yaml` declares both kinds' contracts —
read the registry first and obey it.

## Objective

`questions-unresolved` = **316 atoms**, `tasks` = **751 atoms**. Both un-homed as of 2026-07-29.

> **RE-MEASURED 2026-07-29 (later same day) — and the metric is not well-defined.** This section
> read *"62 levers, 11 unresolved (6 `open`, 5 `needs_human`)"*, a figure carried from a file dated
> 2026-06-25. Actual:
>
> | | |
> |---|---|
> | levers | **61** |
> | `open` | 6 |
> | `needs_human` | **4** |
> | **no `status` key at all** | **47** |
> | `status` holding free-text prose | **4** — e.g. `"optional-fallback (keyed IMAP path designs the grant out for Gmail)"`, `"awaiting sign-off (tokens authored, dark until approved)"` |
>
> ```bash
> python3 -c "import json,collections; r=json.load(open('his-hand-levers.json')); r=r if isinstance(r,list) else r['levers']; print(len(r)); print(collections.Counter(x.get('status','<NO STATUS KEY>') for x in r))"
> ```
>
> **"11 unresolved" is not merely stale — it is uncomputable.** `status` is absent on 47 of 61 rows
> and is a free-text sentence on 4 more, so no honest count exists over this file today. **Define
> what an absent `status` means, and whether a prose `status` is a state or a note, BEFORE setting
> any baseline.** A baseline set over an undefined field is a number that will read as measured and
> is not.

Re-measure before trusting these numbers.

Home both kinds **without enlarging the operator's burden.** This domain's success metric is
**inverted** from every other one: routing 1,067 atoms at the human is the failure mode, not the
deliverable.

- **questions-unresolved 316 → only the genuinely human-gated ones become levers** in
  `his-hand-levers.json` (each with an int `issue`). Everything else is design work → private IRF.
  The charter is explicit: *a closeout that hands him a list has failed even when every item is
  technically homed.* **If this domain triples the lever registry, it has failed.** Most of these 316
  are questions the system can answer by querying a registry it already owns.
- **tasks 751 → demand-gated `limen conduct submit --packet`. Never bulk-submit.** The board's signal
  *is* the asset; 751 synthetic tasks destroy it. A task is submitted when something demands it now,
  not because it was found in a corpus.

## The test for every atom in this domain

Can the system resolve this by reading a registry it already owns — `his-hand-levers.json`,
`organ-ladder.json`, `pillars.yaml`, `tasks.yaml`, `censor/precedents.jsonl`, `convergence.yaml`,
`gates.yaml`? If yes, it is **not** a lever and **not** a task. It is **answered**, and the answer is
the homing. (Precedent: the "8 vs 10 organs" question was asked at the operator while
`organ-ladder.json` held the count.)

## Authorities and prohibitions

- Proceed without confirmation for in-scope reversible work.
- Retained gates: destructive, credential, paid-spend, public-send, runtime/host mutation.
- `his-hand-levers.json` **publishes** and must stay PII-clean — `scripts/no-tasks-on-me.sh` enforces
  it. Atom statement text may never enter the public tree.
- **Credential / secret / token / login / env atoms do not go here.** They go to the credential organ
  (`scripts/creds-hydrate.py` `DEFAULT_MAP`) and the Wall, `organvm/limen#320`. Never recite a
  credential in chat or encode one in a lever.

## Fan-out

At most **6** children, only via `limen conduct split <parent_run> --packet`. Never nest a git
worktree inside this one — the reclaim organ sweeps roots, so a nested worktree leaks. Tier every
child explicitly; no worker inherits this session's model.

## Constraints

Fresh branch `feat/home-questions-and-tasks` off updated `origin/main`, one concern.
`scripts/verify-scoped.sh`; `merge-policy.sh` → `await-pr.sh --merge`. **Claim the settlement with an anchored trailer in the merge commit message** — a line at
column 0 reading `Settles: s4-operator-routing`. The STREAMS registry derives this domain's settled
state from that claim, and *only* from it: an unanchored mention no longer counts (it once
settled `s10-axis-coverage` off a docs commit that merely named it). The claiming commit must
also change something outside the registry and `docs/{plans,continuations}/` — bookkeeping
records an outcome, it cannot produce one.

## Done

`check-atom-homing.py` check C shows both kinds fully homed or bounded-dispositioned;
`scripts/no-tasks-on-me.sh` exits 0; `scripts/credential-wall.py --check` exits 0; and you report the
unresolved-lever count **before and after** (11 → N) with a one-line justification per addition.

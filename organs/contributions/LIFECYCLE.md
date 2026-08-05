# SPECVLVM — LIFECYCLE (the whole arc of one contribution, git processes included)

> Doctrine: see `KERNEL.md`. The lifecycle below is the durable contract; engines and
> humans are replaceable executors of it. Every transition marked **[HIS HAND]** is an
> outbound or irreversible act — the organ stages the receipt, never fires it.
> The executable audit of this rulebook is `scripts/contributions-organ.py`
> (the Lifecycle section of `MIRROR.md`); if this prose and that audit disagree,
> the audit wins — fix the prose.

## The state machine

```
opportunity ──scout──▶ scouted ──adopt──▶ workspace ──author──▶ PR-open
                                                                  │
                              ┌───────────────┬───────────────────┤
                              ▼               ▼                   ▼
                          protocol-due     merged              closed
                          (stale open)       │                   │
                              │              ▼                   ▼
                              └──bump──▶  backflow ◀──learning──post-close
                                             │
                                             ▼
                                          reaped (workspace archived; estate clean)
```

| Stage | Meaning | Owner of the transition out |
|---|---|---|
| **opportunity** | inward-derived: our own wiring names an upstream worth studying (the autopoietic pool in `MIRROR.md`) | scout/fieldwork vets it (engine B `fieldwork.py`) |
| **scouted** | vetted target: mandate named (*what wiring do we study here?*), their CONTRIBUTING bar read | adoption decision |
| **workspace** | `contrib--*` tracking repo initialized (see git processes below) | authoring the change |
| **PR-open** | PR submitted upstream **[HIS HAND]** — the submission itself is an outbound send | upstream review; our monitor |
| **protocol-due** | open PR with no update for `LIMEN_CONTRIB_STALE_DAYS` — a bump is *owed but staged* | bump **[HIS HAND]**, staggered (never batch-bump; the 2026-04-21 sweep bumped 11 at once = protocol violation, now a rule) |
| **merged** | upstream accepted | backflow extraction |
| **closed** | upstream declined | post-close learning extraction (a closed PR still teaches) |
| **post-close** | learning recorded from a closed PR | backflow routing |
| **backflow** | what it taught routed inward to receiving organs (the manifest in organvm-corpvs-testamentvm) | reap |
| **reaped** | workspace archived, fork settled, estate clean | — terminal |

## Git & repo processes per stage

**Workspace creation** (engine B `orchestrator.py` owns the mechanics):
fork the upstream → init the `contrib--*` tracking repo (seed.yaml, CLAUDE.md,
CONTRIBUTION-PROMPT.md, journal) → remotes wired as `upstream` (theirs), `origin`
(our fork), tracking repo registered in the hub ledger. One workspace per upstream;
never author in a raw clone.

**While open**: keep the fork branch rebased on upstream default before any bump;
force-push only to OUR fork branch, never anything shared; every push to the fork is
reversible and allowed — the PR *submission* and every *comment/bump* are **[HIS HAND]**.

**Staleness protocol**: `pr_updated` older than `LIMEN_CONTRIB_STALE_DAYS` (default 14,
declared in `institutio/governance/parameters.yaml`) ⇒ the mirror derives
**protocol-due**. Bumps are staged one-at-a-time, staggered across days — a batch bump
is spam and a standing violation.

**Terminal hygiene (the step nobody does — now audited)**: once merged/closed *and*
backflow is recorded, the workspace is **reap-owed**: archive the `contrib--*` tracking
repo (archive, don't delete — it is provenance; [[empty-branch-is-a-todo-not-a-delete]]
generalizes: a finished workspace is a RECORD, not residue), settle the fork (delete
only if no other open PR rides it **[HIS HAND]**), and mark the ledger entry closed-out.
The mirror's **Lifecycle debt** section lists every reap-owed workspace as a queued
receipt until the hub ledger reflects the closure.

**Estate rule**: every artifact of the practice (script, protocol, rule, memory, log,
session receipt, plan, workspace) is registered in `ESTATE.yaml`; the beat verifies
local presence and surfaces drift. Nothing about this practice may live only in a
chat or a head.

## Autopoiesis (how the organ makes its own next work)

The loop is closed: the **scout limb** of `contributions-organ.py` looks *inward* —
walks our own workspace dependency manifests — and derives the *outward* pool: the
upstreams we already depend on most that we have never engaged. Inward gaze → outward
opportunity → contribution → backflow → inward improvement → (changed wiring) → new
inward gaze. Each cycle feeds the next; the pool refreshes on the beat with zero human
prompting, and the human hand enters exactly once per contribution: the send.

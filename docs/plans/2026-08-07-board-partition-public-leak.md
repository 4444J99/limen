# board-partition: the public board's partner-lane leak has no buildable owner

Issue: #2069
PR: (pending)

## Context

Ten Notification Center screenshots (~40 GitHub notifications, 13:00–20:55 on 2026-08-07) were
handed over with "tend to all". Triaged against `gh`, the wall collapses to **two** defects; the
rest is resolved, superseded, or informational.

**Read as an event log the wall says "40 failures". Read against `gh` it says "one gate is red and
a daemon is retrying it."** The count was never wrong; the denominator was — the same Data
Grounding trap as summing dollar figures in a chat log and calling it revenue.

### Defect 1 — `check-board-partition` red on PR #2001 (open, unresolved)

PR #2001 (`tabularius: publish board projection`) has been red since ~16:16 UTC on exactly one
gate. The TABVLARIVS keeper republishes `tabularius/board-projection` every beat; each republish
re-runs the gate; the gate has been red throughout. `validate` itself **passes** (30s) on the
current head — the 11 red `validate` runs were superseded heads.

`tasks.yaml` is 5.8 MB, tracked, in a **public** repo. **8 fresh findings**, none baselined:

| Finding | Class | Writer |
|---|---|---|
| `REV-4444j99-mirror-mirror-revenue-{readiness,ship}-{0806,0807}` (×4) | `row` | `scripts/generate-revenue-backlog.py` |
| `VIC-ISSUE-AUDIT-001`, `VIC-REPOSITORY-CANON-001`, `VIC-TIER-001` | `row` | `organs/consulting/constellation/seed-tasks.py` |
| `GH-organvm-limen-1767` names lane `4444j99/victoroff-os` | `content` | GitHub-issue intake |

Rows landed on 0806 **and** 0807 — an ongoing source, not a one-off. Two couplings: `--update` is
shrink-only and **refuses to run at all** while fresh findings exist, so these 8 also block the 15
now-stale baseline entries from being dropped; and growing the baseline needs
`--accept-new-disclosures`, which the code calls "a human decision, not a re-pin."

### Defect 2 — `organvm-i-theoria/.github` scheduled job fails every run — **FIXED**

`staggered-scheduling.yml` pushed straight to protected `main` → `GH006: Changes must be made
through the merge queue` → `[remote rejected]`, on every run, forever. Cross-run state moved to an
unprotected branch written via the Contents API.
→ **[organvm-i-theoria/.github#512](https://github.com/organvm-i-theoria/.github/pull/512)** (open, not merged — that repo's charter grants no merge authority).

## The finding: the scrub the gate promises cannot be built

The gate's docstring names "the broker scrub" as these rows' owner **four times**. It does not
exist, and the reason it does not exist is structural, not neglect:

- `dispatch.py:1846` hard-requires `task.repo` — *"remote lane needs GitHub owner/repo"*.
- `dispatch.py` reads `tasks.yaml` **directly** (lines 644, 654, 701, 754).
- `tasks.yaml` is git-tracked and `organvm/limen` is **PUBLIC** (verified via `gh repo view`).

So one file must simultaneously carry `repo` (or dispatch cannot route) and **not** carry partner
attribution (or it is a public disclosure). **No redaction placed anywhere in that file satisfies
both.** A scrub that redacts partner rows silently starves the work-supply for those lanes — the
failure mode is invisible, because the board still looks full.

This also **invalidates the obvious fix**: teaching `generate-revenue-backlog.py` and
`seed-tasks.py` to redact before submission would break dispatch for exactly the lanes it protects.
That was this plan's first draft; it is wrong and is recorded here so it is not re-proposed.

The 425-line baseline (200 `row`, 195 `slug`, 16 `content`) is therefore not a backlog awaiting a
scrub. It **is** the estate's de-facto answer — accept-and-pin, 200 `row` entries deep. The gate
forces a fresh human decision each time rather than letting that accumulate silently, which is
working as designed.

### What ideal-forms logic actually says

Per the operator's "what does ideal forms logic suggest?" — `docs/IDEAL-FORMS-LEDGER.md`:

- **IF-ATOM-HOMING**: *"Homing is distillation, never transfer: counts, ids and generalizations
  cross into the public tree; a statement never does."*
- **IF-SHARED-SUBSTRATE**: one implementation, imported not copied.
- **IF-PUBLICATION-ESTATE**: declared data + a red predicate, zero hand-maintained lists.

Note `partition_lanes.py` derives lane truth from `organs/consulting/constellation/registry.yaml`,
which is **itself git-tracked in this public repo** — so the partner *names* are already public.
What must not cross is the work **attribution and statements**.

Applied to a single public board, IF-ATOM-HOMING has exactly one satisfiable reading: partner rows
must not live on the public board at all. That means **a private board projection** dispatch unions
locally — the row's existence/id/count crosses; `repo`, `title`, `context` stay in the private
store. That is the ideal form, and it is an architecture build, not a patch.

## Decision required (human-gated)

Two paths, and both are the operator's call because both are disclosure decisions:

- **A — private board projection.** Build the second, unpublished projection; dispatch reads the
  union. Satisfies IF-ATOM-HOMING properly, keeps work-supply intact, and finally gives the "broker
  scrub" a destination. Largest build: a keeper branch, storage, and a read path for every consumer
  of `tasks.yaml`.
- **B — accept the disclosure.** `check-board-partition.py --update --accept-new-disclosures`, one
  command, consistent with the 200 `row` entries already accepted. Unblocks the board immediately
  and lets the 15 stale entries drop. Publishes 8 partner attributions permanently.

**Not done unilaterally.** B is one command but it is explicitly flagged in-code as a human
decision, and A changes the board architecture. Until one is chosen, PR #2001 stays red and the
board projection stays unpublished — which is the gate doing its job, not a new failure.

## Verdicts on the rest of the wall (no work required)

| Class | Verdict |
|---|---|
| CodeRabbit comments (#2061, #2047, #2036, #2029, #2019) | all 5 **MERGED** — historical |
| `CI - main (990bce5)` failed | superseded; main is `65dd0c19`, CI green at `5fb9bc9d` |
| ~20 copilot "PR overview" (#2017–#2064) | informational, on merged PRs |
| PR #2066 | green, `pr-gate` pending — owner is the beat's merge rung |
| 3 Dependabot PRs (sibling repos) | out of scope per operator |
| LIMEN host pressure critical | load-shed by the gate, working as designed |
| 2 Claude permission prompts | stale sessions |

## Verification of what shipped

`organvm-i-theoria/.github#512`, run bare (never piped into `tail` — that reports *tail's* exit
code and reads a `FAIL` as green):

- Patch applied by **asserted anchors**: the patcher exits non-zero if any anchor is missing or
  matches more than once, and asserts no bare `git push` survives. A silent no-op string-replace
  would otherwise ship a "fix" that changes nothing while the job keeps failing.
- `yaml.safe_load` parses; all 4 jobs and the new step resolve in order.
- The target repo's own pre-commit suite passes on both files, including **shellcheck**.
- **Not verified:** a live scheduled run. The next `0 0 * * *` firing is the real proof, and the
  first run creates the state branch. Stated as unproven rather than claimed green.

### Defect 1 re-derived at runtime (this section's original numbers came from a CI log)

The 8 findings above were first read out of the `pr-gate` log. Re-run locally against the extracted
keeper board — the check `.claude/skills/verify` prescribes and this plan skipped:

```
git show origin/tabularius/board-projection:tasks.yaml > /tmp/canonical.yaml
LIMEN_TASKS=/tmp/canonical.yaml python3 scripts/check-board-partition.py --check   # run BARE
```

| board | verdict | exit | findings |
|---|---|---|---|
| local `tasks.yaml` (main's mirror) | `ok no new partner-lane content` | **0** | 411 — {row 200, content 16, slug 195} |
| `origin/tabularius/board-projection` (keeper) | 8 × `FAIL` | **1** | 404 — {row 207, content 17, slug 180} |

All 8 ids reproduce exactly as tabled above, so the finding stands on first-hand evidence rather
than on a CI log. The local run is **green** on the same predicate and the same commit — reading it
as the board's verdict is the `LIMEN_TASKS`-mirror trap, now confirmed a third time.

**Correction: the stale count is 15, not 16** (stated twice in earlier revisions of this plan). The
notes are all `slug`-class, and both derivations agree: 195 baselined − 180 reproducing = 15, and
411 + 8 − 15 = 404. The original 16 was a miscount, not board drift — CI reported the same 404/180
split. Recorded rather than silently patched, because a count is this finding's whole substance.

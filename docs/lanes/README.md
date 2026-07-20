# Limen Workstream Channels

A **workstream** is the *purpose* partition of the board — the durable, single-purpose lane a
worker session draws from, the axis **above** the vendor `target_agent` lane. It is Anthony's
"channel" (the word `channel` is already taken in code by `evocator.py` and `launch-organ.py`, so
the converged term is `workstream`).

Model choice inside a vendor lane is a separate concern. See
[`docs/provider-routing.md`](../provider-routing.md): Limen derives a live capability request and
never keeps a fixed model catalog or closed tier table.

**Why it exists.** Without a purpose axis the backlog was one undifferentiated grab-bag: a session
reserved whatever was in front of it, so a mail task and a code task shared one context and one PR
stream — the 10–20-mixed-PRs sprawl. The cure is one field plus one invariant.

## The field (real, not a label)

`Task.workstream` (`cli/src/limen/models.py`) is a first-class field, normalized to a kebab handle.
It flows through the authenticated TABVLARIVS conduct projection untouched; compatibility packets
validate it before the remote GitHub compare-and-swap. This **promotes** the old label-only
convention into enforced machinery.

- keep `repo` pointed at the real project repo;
- keep `target_agent` in the canonical agent set (the *vendor* lane — orthogonal to the channel);
- set `workstream: <handle>` on the task (a pre-field task with a matching **label** still resolves,
  for back-compat);
- name the allowed files, stop condition, and verification command in the task.

## The roster is derived, not hand-kept

`limen.workstream.derived_channels()` builds the canonical roster at read time:

- **Domain channels** = one per institutional organ in `organ-ladder.json` — add an organ, get a
  channel, with **no code edit** (legal, financial, education, media, governance, consulting,
  artist, social, health, …). Aliases fold Anthony's vocabulary onto the pillar handle
  (`revenue` / `money` → `financial`).
- **Operational channels** = the cross-cutting process lanes (the only hand-listed set, because they
  are not organs): `conductor` (idea intake + Q&A), `contributions` (code/PRs), `correspondence`
  (mail), `prompt-parity` (proves every prompt reached its intended parity).

## The invariant (the actual cure)

**One worker session draws OPEN tasks from ONE workstream only.** Enforced structurally by the scoped
cell conductor:

```bash
cell new contrib-run
LIMEN_AGENT=opencode cell conduct contrib-run --workstream contributions
```

`cell conduct --workstream <handle>` registers that native lane and worktree with the authenticated
conduct broker, carrying the workstream in the registered surface metadata. Cells do not emit or own
`tasks.cell.yaml`; task and lifecycle state stays with the canonical keeper. The human-facing
scaffolder stamps the channel into its kickoff packet:

```bash
limen workstream --workstream contributions --prompt 'drain the code lane' limen contrib-run
```

## The projection (the scoreboard)

```bash
limen channels                       # board grouped by channel, counts per status
limen channels --scope financial     # one channel + its tasks (accepts aliases: --scope revenue)
limen channels --json-output         # machine-readable roster + counts
limen channels --prs                 # OPEN PRs bucketed by the SAME channel taxonomy (via gh)
limen channels --prs --scope legal   # list one channel's open PRs
```

`--prs` reuses the exact channel roster to make session/PR sprawl legible on the purpose axis.
Inference is whole-token only (a PR title/branch matches `financial`/`legal`/`mail`/… but never a
substring), and the structural words `pr`/`prs` are ignored in free text — so a large
`(unassigned)` bucket is the honest signal that most fleet PRs carry no purpose channel yet, not a
matcher failure.

## Receipts

- [`rob-game`](rob-game.md) — Micro Tato, the personal game with Rob and John F. (predates the field;
  resolves by label until its tasks carry `workstream: rob-game`).

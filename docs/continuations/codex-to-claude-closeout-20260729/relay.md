# Codex → Claude closeout relay

Generated: 2026-07-29
Source session: redacted direct Codex closeout
Base: `origin/main@4a86f3825ef3a2acf308e1bbd3a0c8463c42d0e1`

## Objective

Continue only the bounded closeout work that remains useful after this Codex
session stops. Re-derive live state first. Do not treat this snapshot as
permission to interrupt another worker.

## Completed by Codex

- Read the global and repository agent protocols plus the `closeout` skill.
- Attempted protected conduct registration through the documented credential
  bootstrap. The authenticated conduct credential is intentionally not
  installed, so new conduct claims, child fan-out, and lifecycle transitions
  remain fail-closed.
- Inventoried the live Codex, Claude, worktree, branch, task-projection, and
  host-admission surfaces without changing them.
- Confirmed the shared Limen `main` checkout was already dirty and behind its
  remote base. No source file in that checkout was edited or staged.
- Created this isolated, finite Claude capsule from the exact remote `main`.

## Protected live boundaries observed

- A Codex worker in `victoroff-os` was actively implementing on
  `m3-publication-ui`; its tracked changes and process are its own lane.
- A separate Codex Desktop session was actively working around the other
  workers through an isolated remote-owned Domus change.
- Two Claude workers were live; their locked worktrees and processes are not
  takeover targets.
- This relay's predecessor is the remaining Codex session and stops after the
  capsule receipt is pushed.

Do not signal, stop, resume, retune, stash, reset, reap, or edit any of those
lanes. A later absence must be proven from live state before normal repository
custody rules apply.

## Owner-routed observations

- The local task projection contains one Codex-targeted `in_progress` record,
  `GH-organvm-hospes-9`. Its durable owner is
  <https://github.com/organvm/hospes/issues/9>. Do not edit `tasks.yaml`; any
  lifecycle transition must go through TABVLARIVS after
  `limen conduct capabilities` succeeds.
- The current Codex runtime contains historical session records whose apparent
  residue must not be resumed blindly. The existing session census can
  misclassify imported transcripts when a terminal completion has an empty
  payload or falls outside its bounded read window. Treat transcript presence
  as evidence, not authority to restart work.
- Personal or legal session material remains private. Keep raw prompt bodies
  out of commits, issues, PRs, and chat; only redacted route receipts belong in
  tracked surfaces.

## First probes

```bash
ps -axo pid=,ppid=,lstart=,etime=,stat=,comm= | \
  awk 'BEGIN{IGNORECASE=1} /codex|claude/ {print}'
git -C /Users/4jp/Workspace/limen status --short --branch
git -C /Users/4jp/Workspace/victoroff-os status --short --branch
limen host-admission status \
  --cwd /Users/4jp/Workspace/limen/.worktrees/codex-to-claude-closeout-20260729 \
  --json
limen conduct capabilities
```

If the conduct credential is still unavailable, inspection may continue but
new claims, fan-out, and lifecycle transitions remain unavailable. Do not
substitute the local test adapter.

## Completion and switch predicates

The successor is complete when every action it actually takes has a durable
owner receipt, the implicated scoped predicate passes on its unchanged exact
head, and no protected live lane was disturbed. If no further action is
necessary after the first probes, record that fixed point once and stop.

Before pushing any successor change:

```bash
git diff --check
bash scripts/verify-scoped.sh
git status --short --branch
```

If scope, runway, broker authority, or host admission prevents sound work,
produce a successor capsule and stop; do not broaden authority.

## Launch

```bash
bash "/Users/4jp/Workspace/limen/.worktrees/codex-to-claude-closeout-20260729/.limen-workstream/kickstart.sh"
```

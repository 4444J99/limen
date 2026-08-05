# Worktree Reclaim Candidates

Generated: `2026-07-09T22:10:25Z`

This is a candidate packet, not acceptance. It does not write
`docs/worktree-reclaim-acceptance.jsonl` and it does not delete roots.

## Summary

- Scanned roots: `384`
- Debt roots: `91`
- Clean merged idle roots available: `0`
- Pushed but unmerged roots retained: `19`
- Candidate roots in this packet: `0`
- Measured candidate size: `not measured`

## Authority Gate

- Decision: `allowed-candidate-packet-only`
- Repo in value tier: `true`
- Prompt family: `worktree_lifecycle` score `32`
- Candidate lane: `codex-conductor`
- Delete gate: `standing-grant-or-human-acceptance-then-reclaim-worktrees`

Authority sources: `value-repos.json`, `cli/src/limen/census.py`, `cli/src/limen/capacity.py`, `cli/src/limen/model_selection.py`, `scripts/score-dispatch.py`, `scripts/session-attack-paths.py`, `scripts/reclaim-worktrees.py`, `docs/worktree-reclaim-acceptance.md`

## Acceptance Flow

1. Review the roots below.
2. Copy only the explicitly accepted JSON objects into `docs/worktree-reclaim-acceptance.jsonl`.
3. Replace `<ISO-8601-UTC>` with the current UTC timestamp.
4. Run `python3 scripts/reclaim-worktrees.py --apply --force`.

## Candidates

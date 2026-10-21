# Debug PR #2976 — verify and dispose of the six Codex findings

Issue: #2976
PR: #2985

## Context

PR #2976 (`docs/agent-docs-repo-map-fixes`, head `3b346f6`) corrects eight unverified claims in
AGENTS.md. It is `CLEAN`/`MERGEABLE`, `pr-gate` is green, but Codex left six unresolved P2 findings
on that head (Sourcery and CodeRabbit are rate-limited — they produced nothing). The PR's whole
purpose is "every claim checked against disk", so a finding that is true on disk is a defect in the
deliverable, not a style note.

I tested every finding against the repo instead of trusting the reviewer. **All six are real.** One
also exposes a latent bug outside the PR's scope.

## Disposition (evidence-bound)

| # | AGENTS.md line | Finding | Verdict | Evidence |
|---|---|---|---|---|
| 1 | 49 | `-m limen` recipe can resolve a YAML-only interpreter | **Accept** | `scripts/lib/gate-python.sh:56-60` falls back to any interpreter that imports only `yaml`; `-m limen` also needs click/pydantic/etc. |
| 2 | 60, 166 | `scripts/verify.py` / `check-agent-docs.py` run via `#!/usr/bin/env python3` shebang | **Accept** | both shebangs are bare `python3`; doc line 43 itself says bare `python3` has no PyYAML; sourcing the resolver cannot change a shebang |
| 3 | 549 | `scripts/merge-policy.sh` is not executable | **Accept** + split | `git ls-files -s` → `100644`; on-disk `-rw-r--r--`; `core.fileMode=true` |
| 4 | 66-72 | `(cd x && …) && …` recipes | **Accept** | the doc's own line 56 says "Bare command, no && chains"; AGENTS.md § Session Discipline rule 7 forbids it on judged rails |
| 5 | 416 | predicate collapsed to `target_agent == "<you>" OR "any"` | **Accept** | main's AGENTS.md reads `OR target_agent == "any"`; the rewrite dropped the comparison, making `"any"` a truthy literal |
| 6 | 80 | "One JSON object on stdout" for every guard | **Accept** (qualify) | `scripts/hooks/pytest-scope-guard.sh` exits 0 silently on every allow path (l.37, 42, 171) and prints JSON only on deny |

## Root cause behind #3 (bigger than the doc)

`fd712ca15` (#2774) changed `scripts/merge-policy.sh` `100755 → 100644` and no later commit restored
it. Consequently `scripts/ship-docs.sh:94` (`"$root/scripts/merge-policy.sh" …`) and the command in
`CLAUDE.md` § Merge & Branch Protocol **would exit 126** when run directly. (Inference from mode +
call sites; not yet observed — PR B's verification runs the call and records the actual exit.) Fixing
the sentence in AGENTS.md alone would be "fix the output, not the base".

## Plan — two PRs, two concerns

### PR A — superseding doc PR on a NEW branch (`docs/agent-docs-repo-map-fixes-v2`, cut at `3b346f6`)
One new commit on top of `3b346f6` (never amend; Rule 12), edits to `AGENTS.md` only. Normal push,
then open the PR (body: `Supersedes #2976`, carrying the Codex disposition table) and close #2976
with a pointer — the same pattern #2951→#2967 used. Rationale: the owner's worktree holds the old
branch, and two concurrent writers on one branch is what Session Discipline rule 5 forbids.

1. **#1** Replace the `-m limen` snippet with one that states the dependency honestly: it needs an
   interpreter with the CLI deps (`pip install -e 'cli[test]'`), exported as `LIMEN_GATE_PYTHON`;
   the resolver's YAML-only fallback is called out as insufficient for `-m limen`.
2. **#2** `scripts/verify-scoped.sh` hard-wires `--changed` (line 18), so `--explain`/`--list`
   **cannot** pass through it — the "one-command wrapper" does not exist for them. Doc therefore says:
   export `LIMEN_GATE_PYTHON` once (an interpreter with PyYAML), then run the bare single commands
   `"$LIMEN_GATE_PYTHON" scripts/verify.py --explain <path>…` / `--list`. For line 166, document only
   `bash scripts/verify-scoped.sh` (it runs the `agent-docs` gate and resolves its own interpreter).
   Read `cli/tests/test_gate_python_resolver.py` + `check-gates.py` ratchet `verify_scoped_wrapper`
   first to confirm the wording doesn't contradict the thin-wrapper contract.
3. **#3** `bash scripts/merge-policy.sh <PR#>` — matches the doc's existing `bash scripts/verify-scoped.sh`
   convention and works with or without PR B.
4. **#4** Split each compound into hook-admissible single commands. Prefer the gate registry
   (`scripts/verify.py --list` to find the mypy / tsc / worker / moneta gates) since AGENTS.md says the
   registry owns commands; otherwise `npm --prefix <dir> …` and `mypy --config-file cli/pyproject.toml …`.
   **Each replacement is executed from repo root and compared with the old `cd` form before it goes in
   the doc** (mypy path resolution is the likely trap).
5. **#5** Restore `target_agent == "<your_name>" OR target_agent == "any"`.
6. **#6** Reword to "a *denial* is one JSON object on stdout; an allow is silent (exit 0, no output)".
   Confirm the other three guards' allow paths are silent before the sentence says "every".

Then: `bash scripts/verify-scoped.sh` once on the final tree (agent-docs gate checks referenced paths and
task-state vocabulary) → push → `bash scripts/merge-policy.sh 2976` → one `merge-drain` submission.
This is fix-on-review round 1 of at most 2 (CLAUDE.md); residual Codex findings on the new head become
issues, not a pre-merge obligation.

**Branch custody (checked):** the old PR branch is held by the owner's worktree
`/Users/4jp/Workspace/.limen-worktrees/agent-docs-correct-20261017` (clean at `3b346f600`). That
worktree is never touched or pushed from; the `-v2` branch avoids a second writer entirely.

### PR B — restore the exec bit (new branch `fix/merge-policy-exec-bit`, off `origin/main`)
`git update-index --chmod=+x scripts/merge-policy.sh`, commit, PR. Before it, check whether an existing
gate asserts exec bits on `scripts/*.sh`; if one exists, determine why it didn't catch #2774. One
concern, one PR; independent of A. No open issue or PR owns this today (searched).

## Out of scope — file two issues, don't fix here
No open issue or PR owns either (searched). Each changes a contract, so each is its own issue:
- `limen_gate_python` accepts a YAML-only interpreter → probe for CLI deps (`import limen` with
  `PYTHONPATH=cli/src`) or fail with the install hint (`cli/tests/test_gate_python_resolver.py`).
  The `gate-python-resolver-20261016` worktree is the squash-merged #2879 (its two commits show as
  "ahead" only because of squash), so it is not a live owner.
- No wrapper exposes `verify.py --explain`/`--list` with a resolved interpreter
  (`verify-scoped.sh` hard-wires `--changed`) — the root cause of finding #2.

## Preconditions still open
- Re-check `scripts/host-work-admission.py status --no-probe` immediately before creating the
  implementation worktree (was `allowed: true` at planning time, one heavy `verify-scoped` lease held).

## Outcome (2026-10-18)
- **PR B — merged:** #2982, squash `7a28dc56d` on `origin/main`; `git ls-tree origin/main
  scripts/merge-policy.sh` → `100755`. Before the fix, `scripts/merge-policy.sh 1` exited 126
  (observed, so the "would exit 126" inference above is now a fact).
- **PR A — open:** #2985 (supersedes #2976, closed with a pointer). Waiting on `pr-gate`; owner is the
  PR, predicate is `bash scripts/merge-policy.sh 2985` → exit 0.
- **Filed, not fixed:** #2983 (resolver PyYAML-only fallback), #2984 (no wrapper for
  `verify.py --explain/--list`).
- **Surprise worth keeping:** the first doc fix failed `agent-docs` check S2 — AGENTS.md was 6 B under
  its 33,792 B ceiling, so honest corrections had to be paid for with deleted restatements.
- **Issue cited above:** Sourcery guessed #2960 as the linked issue; #2960 is about `LIMEN_ROOT`
  inheritance in verify gates and is unrelated, so the chain cites #2976 → #2985 instead.
- **Not executed:** `npm --prefix web/worker run check` and `npm --prefix moneta test` (no
  `node_modules` in a fresh worktree); only `--prefix` resolution was shown.

## Not touched
Issue #2961's session predicate (needs broker credentials — credential-wall owned) and the Domus
`.serena/project.yml` stash are the owner's; nothing to debug there.

## Verification
- A/B each finding against its own parent: claim true on `3b346f6`, false on the fix commit.
- `bash scripts/verify-scoped.sh` exit 0 (read bare, not through a pipe).
- PR B: `git ls-files -s scripts/merge-policy.sh` → `100755`; `ship-docs.sh` reaches its verdict branch
  instead of exit 126.
- Post-push: `gh pr view 2976 --json mergeStateStatus`; merged = commit on `origin/main`.

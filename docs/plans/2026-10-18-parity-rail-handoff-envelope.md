# Handoff envelope — parity rail closure (4444J99/limen)

Issue: #3046
PR: #3068

**Written:** 2026-10-18T09:11Z · **Author lane:** opencode · **Target:** another agent, no guessing required

Every claim below was verified against live state at the timestamps shown. Facts and assumptions are
separated. Read §6 before assuming you hold authority.

---

## 1. Objective

Close the four remaining gaps on the git-parity rail for `4444J99/limen`. Nothing here is code the
lane has already written; all four are unbuilt.

1. Repair `scripts/no-tasks-on-me.sh` so the session-closeout predicate can actually run.
2. Establish a producer for the `limen.session_closeout.v2` receipt, or record why none can exist.
3. Build the drift gate using the **corrected** containment predicate (§7) — not the defective one.
4. Resolve three closed-unmerged PRs whose content is genuinely unlanded (§5).

## 2. Repo and working directory

| Field | Value |
|---|---|
| Repo | `4444J99/limen` |
| Visibility | **public** — every write is irreversible outbound |
| Working dir | `~/Workspace/limen` |
| Interpreter | never bare `python3`; `bash -c 'source scripts/lib/gate-python.sh; "$(limen_gate_python)" …'` |
| Env | `set -a; . ~/.limen.env; set +a` before any broker call |
| Push gate | `bash scripts/verify-scoped.sh` (bare command, no `&&` chains) |

## 3. Current verified state

| Check | State | Verified |
|---|---|---|
| `main` local | `c98acbd1bae4dc489e293e07ce40b2018036c6d5` | 09:11:14Z |
| `main` remote (true, via `ls-remote`) | `c98acbd1bae4dc489e293e07ce40b2018036c6d5` | 09:11:14Z |
| Working tree | clean | 09:11:14Z |
| PR #3039 | **MERGED**, squash `c98acbd1` is tip of remote `main` | 09:11:03Z |
| 19 restored branches | 19 targets, **0 drifted, 0 missing** | 09:10Z |
| Local branches / worktrees | **117 / 61** | 09:11Z |

`main` moves continuously — it advanced five times during the authoring session alone. Parity is a
**timestamped observation, never a completion claim**. Re-verify before acting on any of it.

## 4. Files to inspect

| Path | What it is |
|---|---|
| `docs/receipts/session-closeout-parity-t2-deletion-correction-20261018/README.md` | The correction. Read first. |
| `…/recovery-ledger.tsv` | 70 rows: full OID, named remote ref, PR state, quarantine epoch |
| `…/restored-branches.tsv` | The 19 boundary crossings, with OIDs |
| `…/evidence-sha256.txt` | Digests of the pre-deletion evidence |
| `scripts/no-tasks-on-me.sh:31` | **Gap 1.** Bare `exec python3`, bypasses `gate-python.sh` |
| `cli/src/limen/session_closeout.py:23` | `SCHEMA_V2`; receipt validation starts ~line 508 |
| `.limen-private/parity-t2/recovery/` | Gitignored scratch. **Local-only — does not satisfy durable homing** |

## 5. What is already done

- 70 ref deletions audited and bound to full 40-char OIDs; all 70 confirmed advertised by a named
  remote ref (`refs/pull/<N>/head`) and all objects present in the local store.
- **19 deletions that crossed a retention boundary restored** — 18 from the pre-D3 quarantined
  population, 1 carrying open PR #2867 — and verified by read-back.
- The false claim of "complete parity / nothing left executable" **withdrawn and published** (#3039,
  merged).
- `main` brought to 1:1 under granted push authority.
- Authoring worktree released.

## 6. Authority — assumptions, not facts

**Confirmed:** push and merge authority was explicitly granted to the *authoring* session, and was
exercised (PR #3039 merged via `--match-head-commit` under the repo's standing charter grant).

**Unconfirmed for you:** whether that grant carries to a new session or agent. **Confirm with the
operator before any push, merge, or ref deletion.** Do not infer it from this document.

Deletion of local refs is the one irreversible-by-reflog action here (`git branch -D` removes the
reflog). Reversibility rests only on remote advertisement and the object store.

## 7. Constraints and correctness rules

The authoring session's audit was rejected for four predicate defects that produced confident false
greens. **Any new gate must avoid them:**

| # | Defect | Rule |
|---|---|---|
| D1 | Existence treated as preservation | Test `git merge-base --is-ancestor <tip> <remote-ref>`. Never `rev-parse` existence. Never a self-referential upstream — 10 branches carry `branch.<name>.remote = .` |
| D2 | Silence treated as equivalence | Check **every** command's exit status. `git cherry … \| grep -c '^+' \|\| true` returns `0` on failure *and* on "no difference"; `git cherry` exits 128 on a missing ref |
| D3 | Truncated identity | Full 40-char OIDs throughout, never prefixes |
| D4 | Snapshot staleness | Re-read ownership and PR state **immediately before each mutation** |

Also: a predicate matching nothing must be distinguishable from a predicate finding nothing to warn
about. Assert row counts and fail loudly on zero.

## 8. What remains open

### Gap 1 — gate rail execs bare `python3` *(repo defect, agent-authorable)*
**Blast radius is wider than one script.** Two confirmed instances:

- `scripts/no-tasks-on-me.sh:31` — hardcodes `exec python3 …/session-closeout.py`. Bare `python3` lacks
  `rfc8785`, so the session-closeout predicate is unrunnable as written.
- `scripts/session-plan.py` — invoked bare it dies with `ModuleNotFoundError: No module named 'yaml'`.
  Its failed run still wrote a stub plan under a **doubled date**
  (`2026-10-18-2026-10-18-parity-rail-handoff-envelope.md`) and retained a ship-docs worktree under
  `/Volumes/Scratch/limen-worktrees/` before dying — so the organ leaves litter when its interpreter
  is wrong. (That stub was removed; the retained worktree/branch remain under the reclaim rails.)

Both dependencies — `rfc8785==0.1.4` and `yaml` — **are** declared `cli` dependencies
(`cli/pyproject.toml:15`) and import fine under the resolver. Route these scripts through
`limen_gate_python` like the rest of the gate rail.

*Verify:* `bash scripts/no-tasks-on-me.sh --session-id … --worktree … --receipt … --json` stops
emitting `ModuleNotFoundError`, and `python3 scripts/session-plan.py --help` stops dying on `yaml`.

### Gap 2 — no `session_closeout.v2` receipt *(NOT agent-authorable)*
`--receipt` requires a **committed** `limen.session_closeout.v2` JSON with matching `session_id`,
`session_root_path_sha256`, `scope_roots`, broker binding, and organ session-audit data. There is **no
producer command** — `limen` has no `closeout` subcommand. Hand-rolling one to satisfy a validator
would fabricate a closeout claim. **Escalate to the session-closeout organ owner.**

### Gap 3 — drift gate *(unbuilt by design)*
Deferred until the correction landed. Now unblocked. Must encode §7.

### Gap 4 — three closed-unmerged PRs, genuinely unlanded
Measured with the corrected predicate, `git cherry rc=0`, containment **not** satisfied:

| PR | Branch | Unlanded patches |
|---|---|---|
| #2682 | `fix/jules-rolling-observation-20260918` | 148 |
| #2576 | `work/recovery-isolation-20260908` | 157 |
| #2756 | `work/spine-closeout-successor-20260926` | 129 |

**#2756 is *not* superseded.** The merged successors (#2759, #2761) came from a separate
`…-v2` branch; neither merge commit contains the #2756 tip. "Retire" is therefore an operator judgment
about intent, not a derived fact — surface it, do not decide it. All three refs are **restored**;
none are at risk of loss.

## 9. Verification steps for return

1. `git status --porcelain=v1 -b` clean, and `git rev-parse HEAD` == `git ls-remote origin refs/heads/main | cut -f1`.
2. `bash scripts/verify-scoped.sh` — read **its own** exit code, not a pipeline's.
3. `bash -c 'source scripts/lib/gate-python.sh; "$(limen_gate_python)" scripts/credential-wall.py --check'`.
4. Any new predicate: a deliberately-broken input must make it **fail loudly**, not pass silently.
5. Re-verify each restored ref against `restored-branches.tsv`; report target count and drift count.
6. Do not touch worktrees owned by other lanes — the estate held **61** at authoring time.

## 10. Suggested target agent

**Codex** (interactive, in-session) for Gaps 1 and 3 — both are in-repo code changes needing
`verify-scoped.sh` iteration. Gap 4 needs an operator judgment, not an implementation lane. Gap 2
needs the session-closeout organ owner. Reserve a broker child run before any native fanout.
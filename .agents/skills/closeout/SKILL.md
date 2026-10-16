---
name: closeout
description: Prove session release through scoped evidence; distinguish completed work from durable handoff and estate health.
---

# Closeout

Authority: `AGENTS.md` → Full Lifecycle Closure. Zero dangling items means zero
unowned obligations on this session. A filed task remains unfinished until its own
acceptance predicate passes. Session release does not authorize checkout retirement.

1. Resolve the exact native session, its worktree, and its existing owner/continuation.
   Preserve the caller worktree separately from the installed protocol root. Inspect
   only the accepted scope; never adopt a sibling checkout to obtain a green result.
2. Finish the authorized work or publish a handoff in its existing owner. Preserve
   private artifacts through their custody owner. Record exact owned paths and explicit
   retained-work owners in the existing continuation's `session-closeout.json` using
   `limen.session_closeout.v1`, or v2 with explicit roots for multi-repository sessions
   (see `docs/session-closeout.md`). Unknown ownership fails
   closed. Commit and publish the receipt and owned artifacts through the normal PR rail.
3. Reuse passing verification for unchanged implementation. Run implicated scoped gates
   once per changed tree, including credential-wall evidence for secrets used by the
   session. Whole-repository verification is required only for a whole-repository claim.
4. Hanging-work inventory, before the session predicate. Merged is not live; enumerate
   every item below for the session's scope and resolve or home each one, so the first
   closeout is the real one:
   - unmerged PRs for session branches: `gh pr list --head BRANCH` (merge through the
     step 8 authority or name the open owner);
   - landed-but-unreaped branches: `python3 scripts/reap-branches.py --check`, then
     `--apply` for the standing-grant classes (`landed-pr-merged`, `landed-ancestor`);
   - live-checkout currency: `python3 scripts/check-live-checkout.py` must print
     `state=coherent`; any other state is owned by `scripts/sync-release.sh`, never a
     hand fast-forward of the daemon-contended tree;
   - installed-runtime lag: `python3 scripts/check-runtime-lag.py` (sensor
     `runtime-lag`); exit 1 is rotated by domus `domus-limen-runtime install --sha HEAD`
     (the predicate prints the exact line), exit 77 is unmeasured, never pass;
   - unfiled follow-ups: file the issue and name its owner.
   The operator-action list must be empty or only homed `BLOCKED: <atom>` items.
5. Status words are evidence-bound; report them separately and never blur them.
   "merged": `git merge-base --is-ancestor SHA origin/main` exits 0 after a fetch.
   "live": `git -C LIVE_ROOT merge-base --is-ancestor SHA HEAD` exits 0 and
   `check-live-checkout.py` prints `state=coherent` (installed runtime: step 4 lag
   predicate). "observed": runtime evidence of the behavior itself (beat log line,
   sensor receipt, probe output). Never write "verified end-to-end" without observed.
   User-visible claims take their live-artifact probe from `.claude/skills/ship/SKILL.md`
   step 5 (merged-but-not-live is not shipped); this skill does not restate it.
6. Run `scripts/no-tasks-on-me.sh --session-id ID --worktree PATH --receipt RECEIPT --json`
   from the resolved protocol root with the authenticated conduct environment. For a
   legacy unregistered Codex session, also supply its exact `--native-transcript PATH`.
   With v2, keep `--worktree` bound to the native caller and supply every declared
   `--scope-root ID=PATH`; never substitute a child repository for the native anchor.
   This read-only predicate checks publication, ownership, custody, scoped verification,
   retained broker obligations and surviving processes. Exit 2 is unmeasured, never pass.
   No-argument `no-tasks-on-me.sh` and `closeout-fast.sh` remain estate diagnostics.
7. Idempotence is two runs: run the session predicate twice and quote both bare exit
   codes (never through a pipe). Both must be 0, and the second creates no files, issues,
   leases, worktrees or provider runs. Do not replay a green full suite. A completed
   session needs no successor capsule. A handoff reuses its existing durable owner;
   successor creation requires separately admitted continuation work and never renews a budget.
8. Honor existing merge/deployment authority. A genuine external gate is stated once
   as `BLOCKED: <atom>` and homed with its owner, predicate and next command. Do not
   weaken custody or relabel unknown ownership to pass. Report the scoped result;
   task completion, session release, estate health and deletion eligibility stay distinct.

Only after the session predicate exits 0 may the terminal statement be emitted:
CLOSEOUT COMPLETE — idempotent fixed point, zero dangling items
Nothing follows that statement. If the predicate fails, preserve the precise owner
receipt and report the actual outcome without claiming a successful closeout.

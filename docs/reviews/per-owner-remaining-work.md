# Per-owner remaining work — live ledger (2026-06-20)

Closes the visibility gap behind "every owner knows of their remaining work?". Derived live via
the GitHub API (read-only). The conductor's task queue tracked *generation* for only 3 owners;
the **real** remaining work is the **merge backlog** below — **837 open PRs across 5 owners**.

## The backlog, per owner

| Owner | Open PRs | Queue tasks | Make-up | Status |
|---|---:|---:|---|---|
| `organvm` | **829** | ~99 (mostly `organvm/limen`) | 331 jules[bot] · 262 dependabot · 235 fleet-as-4444J99 · 1 human | merge backlog — gated |
| `organvm-iii-ergon` | 4 | 0 | 2 limen GEN (ci-green) · 2 dependabot | was a blind spot — now tracked |
| `organvm-i-theoria` | 2 | 0 | 2 limen GEN (test-coverage) | was a blind spot — now tracked |
| `a-organvm` | 2 | 0 | 2 dependabot (hokage-chess) | was a blind spot — now tracked |
| `4444J99` | 0 | 20 | — | queue-only (no open PRs) |
| **total** | **837** | — | | |

### What this says
- **`organvm` is the whole story.** 829 of 837 open PRs. The queue's ~99 organvm tasks are NOT
  the remaining work — they're generation seeds; the work is the 829 unmerged PRs. ~80% are the
  fleet's own output (jules + fleet-authored-as-4444J99) + dependabot — i.e. **merge-pending**,
  not build-pending.
- **The three "blind spots" are real but tiny** (8 PRs total). They had 0 queued tasks; now
  itemised here so each owner's work is known. 6 are mergeable bot PRs (deps/ci-green), 2 are
  limen GEN test-coverage.
- **`4444J99` has 0 open PRs** — its 20 queue tasks are generation, nothing pending merge.

## The 5 ownerless tasks — correctly ownerless (not orphans)
`ASK-2-one-container-cutover`, `ASK-5-open-merge-gate`, `ASK-7-dispatch-drain-open`,
`ASK-20-container-relocate-state`, `ASK-60-needs-human-digest` are **conductor-level governance
asks**, not repo PRs. They have no `repo` by nature (they act ON the fleet / are gated human
decisions). They belong to `organvm/limen` + the human gate — no fix needed, just classified.

## The actual bottleneck (not a gap to code around)
837 open PRs is a **merge** problem, gated on two things, both intentional:
1. **The merge gate** (`Bash(gh pr merge:*)` / explicit "merge them") — release-gate HOLD. The
   229 merge-ready PRs (`ASK-5`) sit here by design until the human opens the gate.
2. **The GitHub App identity** (`scripts/gh-app-token.sh`) — once `limen[bot]` is installed on
   `organvm` (the 829-PR owner, top of the install list), the merge pass runs under a machine
   identity that a personal-account lock can't kill. That is the durable enabler for draining
   this backlog safely.

No new generation needed. When the gate opens, the order is: App install on `organvm` → merge-pass
the bot/deps PRs (low-risk, CI-gated) → then the fleet-authored stack. See
`docs/github-app-architecture.md` and memory `merge-readiness-map`.

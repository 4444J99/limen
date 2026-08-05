# S7 — The smallest real lifts

## Precondition

**`s6-registry-correction` MUST be merged.** Lifting against the uncorrected rows lifts the wrong
seam — specifically, it would "extract a toolkit" that `organvm/payrail` already is, and unify an
`export_all()` that shares no function names. **Verify `convergence.yaml` carries the corrected
`worker-toolkit` and `data-export` rows before writing a line.**

## The de-risking fact

Measured 2026-07-26 — **re-verify**: none of the Worker repos deploys on merge; there is no
`wrangler deploy` in any of their CI. A merged lift is therefore a **reviewable code change** and the
deploy stays a human action. That is what makes these safe to land.

## Objective — execute, one branch each, in this order

1. **`data-export`** — extract **only** the two genuinely duplicated helpers (`write_json_artifact`,
   `load_seed_json`) and fix the `SEED_DIR` path-depth divergence. Convert
   `reading-group-curriculum` first as the proof. **Do not unify `export_all()`** — the diffs are
   130–189 lines with zero shared function names; unifying it is a **false lift**, the precise error
   the corrected row exists to stop.
2. **`worker-toolkit`** — a shared `payrailFetch()`/`hmacHex()` module against `organvm/payrail`;
   convert **one** tenant. Its existing vitest suite is the predicate: **run it, do not assert it.**
3. **`voice-infrastructure`** — point one `sign-signal` synth call at vox's `POST /tts`.
4. **`text-quality-scoring`** — **defer with a ratcheted row.** `editorial-standards` is unavailable
   locally and the four encodings share no data shape. A deferral **with** a shrinking baseline is a
   homed item; a deferral without one is a vacuum wearing a disposition.

**IF-AMALGAMATION holds throughout:** the fleet must amalgamate faster than it spawns. This domain is
the amalgamation side of that ledger, and S8's minting is gated by it.

## Authorities and prohibitions

- Proceed without confirmation for in-scope reversible code changes.
- Retained gates: destructive, credential, paid-spend, public-send, runtime/host mutation.
- **One lift per branch, one concern per branch — never batch two lifts into one PR.**
- **No `wrangler deploy` from this session.** Deploy stays a human action.

## Fan-out

At most **4** children, only via `limen conduct split <parent_run> --packet`. Never nest a git
worktree inside this one — the reclaim organ sweeps roots, so a nested worktree leaks. Tier every
child explicitly; no worker inherits this session's model.

## Constraints

Each branch off updated `origin/main`; `scripts/verify-scoped.sh` per branch; `merge-policy.sh` →
`await-pr.sh --merge`. `web/worker` merges do not auto-deploy, but any website-sensitive diff
requires the **full** green rollup first — merging that *is* the deploy. **Claim the settlement with an anchored trailer in the merge commit message** — a line at
column 0 reading `Settles: s7-smallest-lifts`. The STREAMS registry derives this domain's settled
state from that claim, and *only* from it: an unanchored mention no longer counts (it once settled
`s10-axis-coverage` off a docs commit that merely named it). The claiming commit must also change
something outside the registry and `docs/{plans,continuations}/` — bookkeeping records an outcome,
it cannot produce one. This domain lands as several lifts; put the trailer on the **last** one, so
the claim is made once the domain is actually done rather than after its first PR.

## Done

Per lift: the converted consumer's own test suite passes; `check-convergence.py` green; the
capability's row moved `lifting → converged`, or its ratchet shrank. **All four dispositioned**, none
left silently in `lifting`.

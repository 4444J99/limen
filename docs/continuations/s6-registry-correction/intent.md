# S6 — Registry correction: make convergence.yaml describe the code it names

## Objective

`institutio/governance/convergence.yaml` on `origin/main` holds 12 capabilities — 7 converged,
**5 lifting**, 0 unresolved. **Four of its claims were measured false on 2026-07-26.**

Declared data that misdescribes ground truth is worse than a vacuum: it routes work at the wrong
target. **Re-verify each finding against the code before rewriting a row** — this document is a
hypothesis, and a correction made from a stale hypothesis is the same defect wearing a new hat.

## The four corrections

1. **`worker-toolkit`** — the row names no shared substrate, but **`organvm/payrail` already exists**
   as a deployed shared money-rail Worker, and 4 of 6 tenants call it through a **byte-identical
   copy-pasted** `payrailFetch()` + `hmacHex()` block. The lift is not "extract a toolkit"; it is
   "turn an existing copy-paste into an import." `trendpulse` is the true outlier (Lemon Squeezy, no
   payrail). All six are KV-only, no D1. Add payrail as the real seam.
2. **`data-export`** — the row claims "near-identical copies". **False:** real diffs are 130–189 lines
   with **zero shared function names**; each generates different domain artifacts. Only two helpers
   are genuinely duplicated (`write_json_artifact`, `load_seed_json`), plus a `SEED_DIR` path-depth
   divergence that is a **live regression risk**. Rewrite the row to exactly that, and record the
   regression risk where a predicate can see it.
3. **`text-quality-scoring`** — `essay-pipeline/validator.py` is a **frontmatter schema validator**,
   not a quality scorer. The four "encodings" are structurally disjoint: this is a translation layer,
   not code reuse. Its `editorial-standards` dependency **has no local clone**. The row must say so.
4. **`docs/convergence/learning-engine.md`** claims mirror drift "is currently caught only by a manual
   `verify.sh`". **False:** the actual `verify.sh` is a FERPA/secrets guardrail. **Nothing checks
   mirror drift.** That is a vacuum, not a manual process — and a doc describing a nonexistent
   control is how a vacuum hides.

## Also resolve

`scripts/check-convergence.py`'s B-check emits advisories for prose owners (`agon (plugin only)`,
`~/Workspace/daily-engine`); owner `organvm/adaptive-personal-syllabus` has no local clone — it
exists only as an `edu-organism` mirror. Turn each into a verifiable reference.

**Encode the mirror vacuum as declared data:** `institutio/governance/mirrors.yaml` +
`scripts/check-mirrors.py`, rows shaped `{path, origin_repo, direction, last_synced_sha}` — the same
shape that converged `corpus-resolution`. Register it as **one row** in `gates.yaml`.

## Authorities and prohibitions

- Proceed without confirmation for in-scope reversible registry and predicate work.
- Retained gates: destructive, credential, paid-spend, public-send, runtime/host mutation.
- **This domain corrects DESCRIPTIONS and adds the mirror predicate. It lifts no code** — that is
  S7, and S7 is blocked on this landing.

## Fan-out

At most **4** children, only via `limen conduct split <parent_run> --packet`, which reserves each
child against this session's lineage before launch. Never nest a git worktree inside this one — the
reclaim organ sweeps roots, so a nested worktree leaks. Tier every child explicitly; no worker
inherits this session's model.

## Constraints

Fresh branch `heal/convergence-rows-match-ground-truth` off updated `origin/main`, one concern.
`scripts/verify-scoped.sh`; `merge-policy.sh` → `await-pr.sh --merge`. **Include the string
`s6-registry-correction` in the merge commit subject** — the STREAMS registry derives this domain's
settled state from `git log origin/main --grep=s6-registry-correction`.

## Done

`check-convergence.py` green with **zero** prose-owner advisories; `check-mirrors.py` exists, is
gate-registered, and exits 0; `check-gates.py` green; and every rewritten row cites a measurement a
reader can reproduce from the command named in the row's `note`.

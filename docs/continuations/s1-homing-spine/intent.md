# S1 — The homing spine: declared data before any homing

## SETTLED — do not open this domain

**This work landed as [#1608](https://github.com/organvm/limen/pull/1608) (`9a319395`) on
2026-07-29**, shipped by a parallel session while this registry was being authored. Check C of
`scripts/check-session-streams.py` caught the row still claiming the predicate was to-be-built, which
is how the drift surfaced — the registry refused to describe a world that had moved.

What shipped is this domain's ask, in full: `institutio/governance/atom-homing.yaml` (one row per
kind), the statement-free `atom-census.yaml`, `atom-residue-baseline.txt`, and
`scripts/check-atom-homing.py` with checks A–G — including **D**, the executable form of
`redacted: false ⇒ never leaves its store`.

Two corrections to the planning below, both measured:

- **The precondition was wrong.** This spine did *not* require `s0-corpus-custody`. #1608 authored
  check C **store-free on purpose** — "so it runs in CI where the corpus can never exist." The
  registry now records `requires: []` here, and moves the s0 edge onto s2–s5, which genuinely cannot
  proceed without readable statement text.
- **Declaring a home is not homing.** All **4,099 atoms remain residual** against the committed
  baseline. The distillation is s2–s5; this row only ever owned the spine.

The rest of this file is retained as the authored record of what was asked for, and as the
provenance for the counts s2–s5 still rely on. Do not execute it.

## Objective (as authored, now satisfied)

4,099 atoms in 8 kinds. Exactly **one** kind is homed — `projects-to-start`, as **165 `IRF-BRC` rows**
in the private `organvm-corpvs-testamentvm` (verified present 2026-07-29). **3,658 atoms across 7
kinds have no declared owner** and rest in a store whose `corpora.yaml` entry is `remote: none`,
`redacted: false` — by declared design it can never be published. Rule #1: a vacuum is never a
resting state.

`institutio/governance/atom-homing.yaml` and `scripts/check-atom-homing.py` **do not exist** on
`origin/main`. Re-measure before trusting any number here.

**Atom counts by kind:** decisions 877 · tasks 751 · schema-proposals 676 · functionality-to-repeat
518 · vacuums 466 · projects-to-start 441 · questions-unresolved 316 · client-offerings 54.

## Mission

Author the homing spine. **No atom is homed in this domain** — this makes homing *declared* and
*predicated* so S2–S5 execute against a real contract instead of a convention.

1. **`institutio/governance/atom-homing.yaml`** — one row per kind:
   `{kind, home, home_class: public|private|broker, unit: cluster|stream|atom, admits, verify,
   consumers, residue_baseline, owner_of_record, note}`.
2. **`scripts/check-atom-homing.py`** — lettered checks on the shape of
   `scripts/check-personal-facts.py` (123 lines, `fail(check, msg)`). Read that file first; its own
   rationale is the exact analogue — filling a form needed facts with no store, so the ASK became the
   defect, and the registry made an un-homed fact a RED build.
   - **A** schema — all 8 kinds present, enums valid, no kind without a home.
   - **B** resolution — home resolves: in-repo path, declared private-repo path, or a real broker verb.
   - **C** completeness — per kind, `homed + dispositioned == total`, from the **committed census**
     (must run store-free in CI, where the private store does not exist).
   - **D** leak — no atom statement shingle appears anywhere in the public tree. The executable form
     of `redacted: false ⇒ never leaves its store`.
   - **E** ratchet — residue counts only shrink, via a baseline file (pattern:
     `institutio/governance/corpus-root-literals-baseline.txt`).
   - **F** consumers — `scripts/brainstorm-harvest.py`'s `ATOM_KINDS` list **reads** the registry; a
     second copy anywhere is a red check.
   - **G** anti-fake — a kind whose population is wholly deferred is RED; each disposition class is
     bounded and must cite its owner.
3. **`scripts/brainstorm-harvest.py --census`** — a **statement-free** git-tracked artifact (counts
   per kind and per stream, homing ids, disposition tallies). **Not under `logs/**`** — that path is
   gitignored (`logs/.gitignore` is `*`), which is exactly why the drain's entire product is
   local-only today, a standing Rule #2 breach.
4. **Gate row:** `check-atom-homing` in `institutio/governance/gates.yaml`, `ci_job:
   "pr-gate.yml:pr-gate"`, with a `note:` naming the measured defect. Adding a gate is one entry;
   `check-gates.py` enforces parity.
5. **Rule #5 repair, same branch:** commit the α→ω roadmap as
   `docs/plans/2026-07-26-atom-homing-and-lift-correction.md`. It has been local-only in the
   `constellation-atlas` worktree since 2026-07-26.

## Authorities and prohibitions

- Proceed without confirmation for in-scope reversible registry and predicate work.
- Retained gates: destructive, credential, paid-spend, public-send, runtime/host mutation.
- **Zero atoms move.** If you find yourself distilling content, you are in the wrong domain — that is
  S2–S5.
- Atom statement text may never enter the public tree.

## Fan-out

At most **6** children, only via `limen conduct split <parent_run> --packet`. Never nest a git
worktree inside this one — the reclaim organ sweeps roots, so a nested worktree leaks. Tier every
child explicitly by job; no worker inherits this session's model.

## Constraints

Fresh branch `feat/atom-homing-registry` off updated `origin/main`, one concern.
`scripts/verify-scoped.sh`; `merge-policy.sh` → `await-pr.sh --merge`. **Claim the settlement with an anchored trailer in the merge commit message** — a line at
column 0 reading `Settles: s1-homing-spine`. The STREAMS registry derives this domain's settled
state from that claim, and *only* from it: an unanchored mention no longer counts (it once
settled `s10-axis-coverage` off a docs commit that merely named it). The claiming commit must
also change something outside the registry and `docs/{plans,continuations}/` — bookkeeping
records an outcome, it cannot produce one. When `check-atom-homing.py` lands, flip this stream's
`predicate_status` in `institutio/governance/session-streams.yaml` from `to_be_built` to `existing`;
check C fails **both ways**, so the registry cannot drift from reality in either direction.

## Done

`check-atom-homing.py` exits 0 (every kind homed or bounded-dispositioned, leak clean, baseline
monotonic); `check-gates.py` green; `harvest --census` re-run mutates nothing.

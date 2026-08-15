# venture ladder heal: retire the constant-asserting predicate, derive the frontier

Issue: #2458
PR: (pending)

Supersedes the runway scope of `docs/plans/2026-08-14-dustin-full-build.md` (issue #2390, PR #2395).
That plan is not rewritten — plans are never overwritten. This one carries the correction.

## The lived test case

`scripts/dustin-build-done.sh` reported **`DUSTIN BUILD STATE: COHERENT`** and
`FRONTIER the-consulate: COMPLETE (gated frontier: CONS-P07)` across three repos. Every line
read `OK`. The build was declared done.

Seventeen leaves of ungated, fully-specified, dependency-satisfied work had never been built.

The predicate could not have found them. Its scope is a shell literal:

```bash
runway_for() {
  case "$1" in
    the-consulate)       echo "CONS-P02 CONS-P03 CONS-P04 CONS-P05 CONS-P06" ;;   # :41
  esac
}
gated_for() {
  case "$1" in
    the-consulate)       echo "CONS-P07" ;;                                       # :48
  esac
}
```

`CONS-P08`, `CONS-P09`, `CONS-P10`, `DSP-P11`, and `NAS-P10` appear in neither list. The check
walked a hand-typed array, found every element of it satisfied, and printed COMPLETE. **A check
that encodes its expected answer as a literal can only ever confirm the literal.**

The scope came from a prose claim in the prior plan's runway table:

> `the-consulate | CONS-P02..P06 | ... P08/P09 wait on gated P07 by declared depends_on`

True at the phase level, and irrelevant. `CONS-P08.depends_on: ["CONS-P07"]` is a **semver
ordering declaration**. Underneath it:

```
CONS-P08-E01      depends_on: ["CONS-P01-E01"]   -> done
CONS-P08-E01-L01  depends_on: []   blocked_on: null
CONS-P08-E02      depends_on: ["CONS-P08-E01"]   -> internal
```

Not one epic or leaf in P08 references any P07 node. The work was never blocked. An unverified
sentence set the scope, a hardcoded list enforced it, and a green predicate ratified it.

## Root cause: three faces of one defect

| # | instance | what it asserted | what was true |
|---|---|---|---|
| 1 | `runway_for()` / `gated_for()` literals | "these are the phases" | five phases invisible |
| 2 | D5 contiguity (`dustin-build-done.sh:91`) | "a done phase after a non-done phase is incoherent" | a **lever** is not a **dependency** |
| 3 | prior plan's runway table | "P08/P09 wait on gated P07" | phase-level ordering only |

All three substitute a **declaration** for a **derivation**. The ladder already carries the truth
in machine-readable fields — `phase.gate`, `epic.blocked_on`, `leaf.blocked_on`, and node-level
`depends_on`. Nothing needed to be invented; it needed to be *read*.

D5 is not even a repo invariant. It is a convention this project's own shell script invented.
The validator disagrees with it (`src/roadmap-check.js:464`):

```js
const donePhases = ladder.phases.filter((ph) => ph.status === 'done')
const lastDone = donePhases.reduce((best, ph) => (semverGT(ph.version, best.version) ? ph : best))
if (pkg.version !== lastDone.version) → fail
```

`lastDone` is the **max-version** done phase. No contiguity is required. `checkPhaseProof` (:834)
only fires *when a phase is already done*, and never forbids a gap. The repo has always permitted
a GATED phase sitting mid-sequence with built phases after it.

## Evidence: every non-done phase, declared vs derived

Measured 2026-08-15 by the scratch derivation this plan lands as engine check **K** (T1) — which
ignores `phase.depends_on` by design and classifies from `gate` / `blocked_on` / node-level
`depends_on` alone:

| phase | declared | derived | verdict |
|---|---|---|---|
| DSP-P09 | `GATED` | LEVER-BLOCKED — `L-DSP-TEN-QUESTIONS`, 14 nodes | agree |
| DSP-P10 | `GATED` | LEVER-BLOCKED — `L-DSP-TEN-QUESTIONS`, 15 nodes | agree |
| **DSP-P11** | `gate-dependent` | **BUILDABLE-NOW** — no lever, no unmet dep | **MISMATCH** |
| CONS-P07 | `GATED` | LEVER-BLOCKED — `L-CONS-PRICE`, 17 nodes | agree |
| **CONS-P08** | `buildable` | BUILDABLE-NOW | agree — **and never built** |
| **CONS-P09** | `buildable` | **DEP-BLOCKED** — `CONS-P09-E01 → CONS-P08-E02` | **MISMATCH** |
| CONS-P10 | `gate-dependent` | DEP-BLOCKED — via `CONS-P07-E02`, `CONS-P09-E02` | agree |
| NAS-P08 | `GATED` | LEVER-BLOCKED — `L-NAS-TERMS`, 11 nodes | agree |
| NAS-P09 | `GATED` | LEVER-BLOCKED — `L-NAS-CREDENTIALS`, 10 nodes | agree |
| NAS-P10 | `gate-dependent` | DEP-BLOCKED — via `NAS-P08-E01-L01`, `NAS-P09-E01-L01` | agree |

Two mismatches the original audit missed because it trusted `phase.status`:

**DSP-P11 "Live end-to-end on one real release"** — `gate: null`, and all 9 leaves carry
`blocked_on: null, depends_on: []`. It derives BUILDABLE-NOW. It is not. Its goal is *"one real
release, real money"*; its entry gate reads *"P08 done, and (P09, P10) each done or deferred."*
The human-world block exists only in **prose fields** (`goal`, `entry_gate`, `exit_gate`) and was
never encoded in machine fields. This is a **missing lever**, not available work — the exact
inverse error to CONS-P08, and equally invisible to a status-trusting check.

**CONS-P09** derives DEP-BLOCKED on `CONS-P08-E02`. Its `buildable` label is optimistic. This is
harmless but load-bearing for scheduling: **P08 → P09 is strictly sequential, not two parallel
lanes.**

## Confirmed healthy — do not manufacture work here

Verified, so the heal stays scoped:

- **Harvest chain intact.** 0 orphan sources (39/39 DSP, 60/60 CONS, 34/34 NAS), 0 findings
  without atoms (39/39, 27/27, 18/18), **0 unhomed atoms in all three repos**.
- **All 4 declared contradictions are adjudicated** to terminal states — `DSP-F001/F002` both
  built, `DSP-F004/F005` both built, `DSP-F011/F012` both `rejected` (the fractional-royalty NFT
  mechanisms, rejected on both sides consistently), `CONS-F002/F003` both built. Recorded
  contradiction between source documents is the harvest working, not a defect.
- **The validator engine is byte-identical across all three repos** —
  `sha256 eb524043cad802612ee3bdf45e90f04cfa8f96538bd2347e7c66d785db38e079`. It is vendored, not
  shared. Every engine change must land in all three identically or check H diverges.

## Decisions

- **H1 — `phase.status` becomes a *derived* value, and disagreement is a build failure.** New
  engine check **K** recomputes each phase's class from `gate` / `blocked_on` / node `depends_on`
  and fails on mismatch with the declared label. The label may stay in the file (renderers and
  `--phase-done` read it); it may no longer be *trusted*. Binds: T1.
- **H2 — `phase.depends_on` is ordering-only and is never read as a work dependency.** Work
  dependencies live at epic/leaf `depends_on` plus `blocked_on`. Check K ignores it explicitly;
  the field gains a schema comment saying so. Conflating the two is defect #3 above, and the
  conflation is what cost 17 leaves.
- **H3 — DSP-P11 gains `gate: L-DSP-LIVE-RELEASE`** plus `blocked_on: L-DSP-LIVE-RELEASE` on its
  2 epics and 9 leaves, making the real-release requirement machine-legible. This is the D4
  precedent (NAS-P05's gated corpus-import leaf) applied to the inverse error. **DSP-P11 is not
  built by this plan** — encoding the lever is the fix; the lever is the partner's.
- **H4 — `dustin-build-done.sh` carries zero repo knowledge.** `runway_for()` and `gated_for()`
  are deleted. The script iterates the repo list and calls a new `bin/check-roadmap.js --frontier`
  which emits the derived classification as JSON. Repo topology stops living in a shell literal.
- **H5 — D5 contiguity is retired, replaced by real-dependency satisfaction.** A done phase must
  have every epic/leaf-level `depends_on` target done; a GATED phase may be skipped. This matches
  what `checkE` already enforces, so no validator change is needed to permit it — only the
  predicate's assertion is removed.
- **H6 — the audit organs become repo-owned, not `/tmp`.** The three scratch scripts that found
  all of this (`frontier-derive`, `harvest-coverage-audit`, `harvest-disposition`) land as engine
  checks **K** (derived frontier), **L** (harvest coverage: 0 orphan sources / 0 atom-less
  findings / 0 unhomed atoms), and **M** (every `contradicted` finding pair reaches terminal
  adjudication), wired into `npm test`. Rule #2: on disk in `/tmp` is not done. Letters K/L/M are
  free — the engine currently defines A–J plus R and Omega.
- **H7 — `v0.7.0` stays reserved for the gated CONS-P07. No renumbering.** Tag order will read
  `v0.6.0 → v0.8.0 → v0.9.0`, with `v0.7.0` landing whenever the pricing lever resolves.
- **H8 — CONS-P08 then CONS-P09, strictly sequential.** Derived (H1), not assumed: `CONS-P09-E01`
  depends on `CONS-P08-E02`. Within P08, `E02` depends on `E01`. Lane concurrency is therefore
  bounded by leaves inside one epic, ≤3 at a time on the 16GB host (inherits D8).
- **H9 — the completion pass is unchanged (D1) and the engine change ships before the build.**
  T1 lands and goes green on all three repos *before* any CONS-P08 leaf is written, so the new
  checks govern the work rather than being retrofitted to bless it.

## Execution tree

```
T1  engine heal — the derived frontier                      [blocks everything]
├── K  derived-vs-declared phase class          src/roadmap-check.js
├── L  harvest coverage                          "
├── M  contradiction adjudication                "
├── --frontier JSON emitter                     bin/check-roadmap.js
└── land byte-identical × 3 repos               (check H parity; sha must match across all three)

T2  ladder truth repair                                     [after T1, needs K to prove it]
├── DSP-P11  + gate: L-DSP-LIVE-RELEASE, blocked_on × 11 nodes
├── CONS-P09 label -> the class K derives
└── per-repo atomic pass (D1): regen -> reconcile -> PARITY -> commit

T3  the build — 17 leaves                                   [after T2]
├── CONS-P08  "Engagement ops + client-data boundary"   2 epics /  9 leaves
│   ├── E01 (4 leaves)  depends_on CONS-P01-E01 [done]
│   └── E02 (5 leaves)  depends_on E01
│   └── completion pass -> package.json 0.8.0 -> tag v0.8.0 -> milestone P08
└── CONS-P09  "Full synthetic engagement dry-run"       2 epics /  8 leaves
    ├── E01 (4 leaves)  depends_on CONS-P08-E02
    └── E02 (4 leaves)
    └── completion pass -> package.json 0.9.0 -> tag v0.9.0 -> milestone P09

T4  predicate rewrite + correction stamp                    [after T3]
├── dustin-build-done.sh: delete runway_for/gated_for, consume --frontier
├── delete the D5 contiguity assertion (:91)
└── correction breadcrumb on 2026-08-14-dustin-full-build.md
```

All 21 GitHub issue bodies for P08/P09 already exist (4 epics + 17 leaves) with acceptance
predicates, and `reconcile-issues.js` reports PARITY. T3 authors code, not specifications.

## Acceptance

1. `bin/check-roadmap.js` exits 0 in all three repos with K/L/M active, and the engine SHA is
   identical across all three.
2. Check K reports **zero** declared-vs-derived mismatches — DSP-P11 resolved by lever, CONS-P09
   by label.
3. `--phase-done CONS-P08` and `--phase-done CONS-P09` both true; `package.json` at `0.9.0`;
   tags `v0.8.0`, `v0.9.0` on the remote; milestones P08, P09 closed.
4. `CONS-P07`, `DSP-P09`, `DSP-P10`, `NAS-P08`, `NAS-P09` byte-untouched — check G still proves
   lever-blocked leaves never started. `DSP-P11` gains only its lever encoding.
5. `dustin-build-done.sh` contains no phase identifier as a literal (`grep -c 'P0[0-9]'` → 0) and
   re-runs COHERENT, with its frontier list now naming DSP-P11 and CONS-P10 — phases it could not
   previously see.
6. Run the predicate bare and read `$?` directly; a pipe into `tail` reports tail's status.

## Anti-strawman

**"Just add the missing phases to `runway_for()`."** That is the defect, restated. The list would
be correct until the next ladder edit and would fail silently again — with no signal, exactly as
it failed here. The list must not exist.

**"Renumber CONS-P07 to the end so the done prefix stays contiguous."** Rejected. It churns 21+
issue IDs, bodies, milestones, and the issue-map `ladder_sha` to buy monotonic tag numbers — and
it preserves the false premise that a gap is a problem. The gap is *informative*: it marks exactly
where a human decision is owed. Encode the lever; leave the numbers alone.

**"Build DSP-P11 too — it derives buildable."** No. Deriving BUILDABLE-NOW is what exposed the
missing lever; the derivation is a detector, not a work order. Its acceptance requires real money
moving through a real release. The fix is to encode what was only ever written in prose.

## Security invariants (unchanged, restated because T3 touches client-data boundaries)

The partner is `dustin` / "the partner" only. PERSONAL-class content is pointer-only and never
quoted or paraphrased into any repo. PRODUCT-class content is quotable only into its owning
private venture repo; nothing from private corpora reaches public limen. Denylist tokens are never
printed or committed. No credentials until agreed in writing — NAS enforces this in code and that
enforcement stays. CONS-P08 is *"client-data boundary"* work: it is scaffolding and policy, and
handles no real client data.

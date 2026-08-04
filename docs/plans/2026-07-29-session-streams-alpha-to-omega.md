# Session-stream cartridges: α → ω

## Context

The STREAMS registry (`institutio/governance/session-streams.yaml`, #1612/#1613) replaced a prose
dependency graph with declared data and a **derived** ready-set, so that "which domains do I open?"
becomes a command's output instead of a table somebody maintains.

Asked for the next step across the whole arc, two read-only sweeps measured the machinery against
disk. The registry is real, and its linter has already caught two live errors. But three structural
gaps sit under it — and the stated goal ("fix s9 so the rest can launch on opus") is **not** delivered
by merging s9 alone:

1. **State derivation is unsound.** `settled` is `git log origin/main --grep=<id> --fixed-strings`
   (`scripts/check-session-streams.py:131-138`). Unanchored, so any commit merely *mentioning* an id
   settles it forever. And it has already false-positived: `s1-homing-spine` reads settled **only**
   because the registry's own commit `b5d7909f` says "record s1-homing-spine settled by #1608". The
   real s1 work (`9a319395`) never names the id — verified, `grep -c` → **0**.
   The original plan for this registry specified check F as *"`settled` requires the predicate to
   actually exit 0"*. What shipped instead was "no row may carry a state field" — a weaker property,
   then over-claimed in its own docstring as *"there is no field to lie in."* The lie simply moved
   from a YAML field into a commit message, which is equally writable and far less reviewable.
2. **The emitted command cannot carry a tier.** `--ready`/`--all` emit no `--agent`, and the lane tier
   pin *requires* `--agent`. A lane opened from the registry's own output still inherits the
   interactive default — verbatim the defect s9 exists to close.
3. **Five of ten rows have decayed** in the day since authoring; one names a file that does not exist.
   A cartridge is loaded cold into a fresh session, so a false premise gets *executed*, not caught.

**Intended outcome:** the registry becomes trustworthy end to end — state proven rather than asserted,
rows re-grounded against measurement, and its emitted command launching a correctly-tiered lane — so
the remaining domains can be opened in dependency order and driven to a fixed point where the
ready-set empties.

---

## α — Unblock #1619 (the lane tier pin)

`pr-gate` on [#1619](https://github.com/organvm/limen/pull/1619) has failed **twice on the same bug
class**: argument validation ordered *after* environment probing, so the verdict depends on what
happens to be installed.

The first firing was the pin check (fixed, `25c503cd`). The second is the Codex triple:

```
AssertionError: assert 'Codex sandbox must be one of' in
                ('native CLI not found for canonical lane codex\n' + '')
```

`scripts/start-worktree-session.sh:381-384` probes for the codex binary; only at `:385-391` does it
call `validate-codex-launch`. CI has no codex binary → exit 127 before the sandbox value is examined.
Locally codex exists → exit 2.

**The fix is a split, not a reorder.** `workstream_contract.py:1007-1015` already calls
`_authorization_for_sandbox(args.sandbox)` — a pure static enum check — *before*
`validate_codex_launch(args.binary, …)` touches the binary. The shell never reaches it.

- Add a static-only `validate-codex-sandbox` subcommand in `cli/src/limen/workstream_contract.py`
  (~`:951`), exposing `_authorization_for_sandbox` with no `--binary` requirement.
- Call it in `scripts/start-worktree-session.sh` **before** the binary probe at `:381`.
- Leave `validate-codex-launch` untouched for the binary-dependent model/effort probe.

This **strengthens** Codex validation: an invalid sandbox is now rejected even where codex is not
installed. It does not touch the launch profile's required triple or capsule identity hashing.

**Verify:** re-run the stripped-PATH harness used for the first fix (temp bin of symlinks omitting
`codex`); assert exit 2 with codex absent, jules absent, and codex present.

---

## Phase 1 — ROOT: make settlement provable

*Decided: **trailer gates, predicate proves.*** Target:

```
settled(sid) ⟺ has_anchored_settles_trailer(sid) AND predicate_command_exits_zero(sid)
```

### 1a. PREREQUISITE — the predicates cannot currently be executed

This is the blocking discovery, and it must land before any predicate is run:

| problem | evidence |
|---|---|
| **7 of 10 streams share a predicate with another stream**, so it cannot decide any one of them. `check-convergence.py` → s3, s6, s7. `check-atom-homing.py` → s1, s2. `no-tasks-on-me.sh` → s4, s5. | `session-streams.yaml` predicate fields; none take arguments (`grep argparse` → no hits in `no-tasks-on-me.sh`, `check-convergence.py`) |
| s1 is genuinely settled and shares `check-atom-homing.py` with s2, which is **not** done. Pass ⇒ s2 falsely settles; fail ⇒ s1 regresses. Both wrong. | same |
| **s9's predicate is a pytest file, not an executable** (`exec=False`) | `cli/tests/test_workstream_contract.py` |
| **s8's predicate is an EFFECTOR, not a checker.** `scripts/repo-genesis.py` requires `--name`/`--evidence`/`--why`, and its own header says *"On mint (without `--dry-run`): creates the private repo, pushes the seed material"* (`:28`). Running it as a settlement probe is an irreversible, outward-facing action. | `scripts/repo-genesis.py:28,100-107,123-124` |

Two more, found in design:

| problem | evidence |
|---|---|
| **s0's predicate is host-aware and returns 0 in CI regardless.** `check-corpora.py` degrades disk checks to advisory where no corpus root exists — every runner. So `predicate_exits_zero(s0)` is `True` today *while the store is gone and s0 is not done*. | `check-corpora.py:100-120,129-138` |
| **s4/s5's predicate is non-deterministic and network-coupled** — live `gh api`/`gh repo view`, reads a private denylist under `$HOME`, shells `reap-branches.py --check`. | `scripts/no-tasks-on-me.sh:147-152,201` |

**Therefore:** add a `predicate_command` field — the full argv actually run — distinct from
`predicate` (the file whose existence check C already validates). Constraints:

- **Must be side-effect-free.** s8 ⇒ `… --dry-run`. Enforce with an argv guard: `argv[0]` restricted
  to `{python3, bash, scripts/run-pytest-hermetic.sh}`, and any `--apply`/`--no-dry-run`/`--write`
  token **refused by the checker**, never executed. This is what makes it impossible to ever wire
  the repo minter up with real arguments.
- **Must be stream-distinguishing.** Add a per-stream assertion flag
  (`check-convergence.py --stream s6`) or a narrower check per row. A shared, argument-less command
  may not be accepted as settlement proof.
- s9 ⇒ dispatch test-file predicates through `scripts/run-pytest-hermetic.sh`, already the estate's
  convention for a test-as-gate (`gates.yaml:164,174,270…`); it scrubs `LIMEN_*`/`GIT_CONFIG_*`
  first. Bare `pytest` fails here with `ModuleNotFoundError: No module named 'limen'` — an
  unimportable predicate must be a loud failure with that error attached, never a silent pass.
- Timeout (~180 s); nonzero exit, timeout, refusal and "no runnable form" all resolve identically to
  **not proven**.

### 1a′. Semantics — and why the ordering matters

The decision was `settled ⟺ trailer AND predicate`. **That is sound only once 1a lands**, and is
actively wrong before it: with today's shared predicates, s7 would settle the moment it earned a
line simply because *s6's* checker is green, and s0's conjunct is a no-op in CI. So 1a is not
optional cleanup — it is what makes the chosen semantics mean anything.

Ship the behavior behind one constant so the choice stays reversible:

```python
PREDICATE_DEMOTES = True   # the decided AND: a failing predicate un-settles the row
                           # False -> the row stays settled and check P goes RED instead
```

`False` is worth considering *after* 1a: a settled row whose predicate later regresses is a
**regression to repair**, and `--ready` printing "open s7" as though the work never happened is the
less useful statement. One constant either way — do not fork the derivation.

Keep predicate execution behind `--verify` for the CI path regardless; the default stays git-only
and gets faster.

### 1b. Trailer parsing — an anchored line regex, **not** git's trailer parser

⚠️ **`%(trailers:key=…)` cannot be used here, measured.** `CLAUDE.md` mandates squash-merge, and
GitHub's squash appends its *own* `Co-authored-by:` paragraph. Git's trailer parser reads only the
**last** paragraph, so an author-written trailer is demoted to plain body text. On `origin/main`,
all **9 of 9** commits carrying `Claude-Session:` in the body return **empty** from
`%(trailers:key=Claude-Session,valueonly)`. (An earlier spot-check appeared to succeed only because
it queried `Co-Authored-By` — the line GitHub itself appends last.)

So: match an anchored line over `%B`.

```python
SETTLES_RE = re.compile(r"^Settles:[ \t]*(\S.*?)[ \t]*$", re.MULTILINE)
```

Column-0 anchoring is what closes the substring defect — which is all git's parser was wanted for.
`  Settles: …` (indented) and `> Settles: …` (quoted) correctly do not match. One commit may settle
several comma-separated ids; unknown ids settle nothing.

**Lock this in with a test** asserting both that the regex finds a `Settles:` line followed by a
GitHub squash footer *and* that `%(trailers:…)` returns empty on the same commit — so nobody
"improves" it back into the broken form.

### 1c. Self-reference rejection

A commit proves `sid` only if it changes **at least one path outside** `{session-streams.yaml,
docs/continuations/<sid>/**}`. That is precisely the rule `b5d7909f` fails — it claimed s1 in its
body while editing the registry. Resolve in **one** `git log -E --grep='^Settles:[ \t]' --name-only`
pass over candidates, framed with `%x1e`/`%x1f` so a body containing blank or file-shaped lines
cannot be misread as the `--name-only` tail.

Measured: this is **cheaper than what it replaces** — 1 git call at ~38 ms vs today's 10 calls at
~214 ms.

### 1d. Migration, and the check F interaction

s1 is genuinely done (#1608) but no commit carries the line, so it would regress to unsettled. Add
`settled_by: <40-hex sha>`.

**`settled_by` is not a convenience — rule 1c makes it structurally necessary.** A missing line
cannot be retro-added to a merged commit, and a remedy PR that touches only the registry is killed
by 1c. Without a citation field a forgotten line is an unrecoverable deadlock.

**Why a citation is not a status:** `settled: true` is an assertion nothing can refute.
`settled_by: 9a3193…` is a claim a check can **refute** — the sha must be 40-hex, resolve, be an
ancestor of `origin/main`, and change something outside the registry. The registry gains a field you
can be *wrong* in, not one you can lie in. Cap it: `MAX_SETTLED_BY = 1`, so exactly the one
pre-convention row may use it and everything future earns the line.

⚠️ **Correction to the premise:** check F does **not** currently forbid these fields. `:249-250`
tests exact dict keys, so `settled_by`, `settled_at`, `is_done` all pass silently *today*. So F must
be **tightened** (to stem-matching: `k == stem or k.startswith(stem+"_") or k.endswith("_"+stem)`)
at the same moment the one exception is carved — otherwise the exception arrives as an accident.

### 1e. Docstring truth

Rewrite check F's docstring to describe what the code does. The current one over-claims, and that
over-claim is what let the s1 false positive pass review.

### CI cost — and why the gate is the wrong home

`session-streams-drift` (`gates.yaml:529-535`) carries no `scoped: false`, so it defaults to scoped
and `verify.py --changed` fires it **only when the registry, intents, or checker change** — not on
every PR. So predicate execution is affordable there.

But that same scoping is a hole: **settlement changes when *other* PRs merge**, and those never touch
the streams paths, so the gate does not re-run and the drift is invisible. Keep predicate execution
behind `--verify` for the pr-gate path, and make the beat the real home (see ω).

---

## Phase 2 — ROOT: re-ground the rows against measurement

Every claim below was verified against disk during planning.

| row | drift | correction |
|---|---|---|
| **s0-corpus-custody** | **Mission delivered by #1615** (CUSTODY axis), in a different and better shape. All three items map: (1) store addressable via declared data → `custody.yaml:99-110`, `class: archive`, `vault: arca`; (2) *"make an unresolvable root RED"* → `check-corpora.py:129-138` **fails** on `reference_state.UNACCOUNTED` and degrades to `advise` only when the root is declared `ARCHIVED` — precisely the "degrade to declared data, never a filesystem probe" the intent demanded; (3) reclaim verb → `arca.sh restore <store> [dest]`, cost measured #1618. Residue: the root still does not resolve and `corpora.yaml:42` still names it directly. | **Settle it.** The defect s0 names — a registry green over a store nobody can open — is closed: green now requires a *declared archive with a reclaim path*. Highest leverage in the whole arc: s0 gates s2/s3/s4/s5, four of nine. |
| **s3-governance-case-law** | Note pivots on "convergence.yaml asserting 0 unresolved". Now **1** (`mirror-drift-detection`, added by #1611 *before* the registry shipped). | Rewrite the premise. |
| **s4-operator-routing** | Baseline "62 levers, 11 unresolved (6 open, 5 needs_human)" taken from a file dated `2026-06-25`. Actual: **61** levers; open **6** ✓; needs_human **4**; and **47 rows carry no `status` key at all** — the metric is not well-defined. | Re-measure; define the metric over status-less rows *before* setting a baseline. |
| **s6-registry-correction** | Claim 4 of 4 already corrected by #1611. "Four of twelve capability rows" — there are now **13**. | Drop claim 4, re-count, keep claims 1-3. |
| **s8-mint-by-demand** | `owner_of_record: institutio/governance/estate.yaml` **does not exist**; the real registry is `institutio/github/estate.yaml` — its own predicate proves it (`scripts/repo-genesis.py:51`). | Fix the path. Nothing would ever have caught this — see Phase 3, check H. |
| **s9-lane-tier-pin** | Note describes a defect already repaired on this branch; intent cites `logs/fable-allotment.json`, which does not exist. | Settles on #1619; fix the citation. |

Verified sound: **s1, s2, s5**. All ten intent files exist; all predicates exist; every
`predicate_status: existing` matches disk.

**Carry into s6/s7:** every repo named by the worker-toolkit / data-export / text-quality-scoring rows
is absent from this host. Under CUSTODY these are `remote`-class refs recoverable by clone, but the
2026-07-26 measurements **cannot be re-verified locally** — the intents must say so and the lanes must
re-measure before acting.

**Dangling provenance:** `session-streams.yaml:9` and `:53` cite
`docs/plans/2026-07-29-session-stream-cartridges.md`, which exists **nowhere on main** — only on draft
[#1607](https://github.com/organvm/limen/pull/1607). Either merge #1607 (fixing its own stale S8 claim
first) or close it and rewrite the citation to name the commit SHA.

---

## Phase 3 — TRUNK: wire the four inert fields

*Decided: **all four**.* Today `job_class`, `branch_prefix`, `max_children` and `owner_of_record` are
read by nothing outside the linter.

### 3a. `job_class` → tier in the emitted command *(this is what delivers the Opus goal)*

Emit `--agent claude --model <derived>` so a launched lane stops inheriting the interactive default.

**Extract, don't duplicate.** `_claude_tier_for(task: Task|None)` takes a `Task` (`dispatch.py:5690`)
and importing `dispatch` drags in the whole `limen` package — but the checker imports
`model_selection.py` *by file path* precisely because it is pure-stdlib (`model_selection.py:14-16`),
and that constraint is load-bearing. The class→tier sort inside `_claude_tier_for`
(`dispatch.py:5709-5719`) is built only from `model_selection` primitives. So add
`model_selection.tier_for_classes(classes, *, waste_classes, overrides)` and have `_claude_tier_for`
call it. Pure refactor, zero behavior change — and it makes the no-second-ladder rule literally true
for a third consumer. Guard it with a test asserting
`tier_for_classes({"canon"}) == _claude_tier_for(Task(type="canon"))`.

**Make check G real.** It is a literal no-op today: `opus_classes` is bound at
`check-session-streams.py:177` and never compared; the body at `:256-259` only asserts a non-empty
string. Arm it to reject (a) a class the authority cannot see, and (b) a **reserved-Fable** class —
`docs/fable-allotment.md:5-7` makes Fable PLAN-ONLY and building on it prohibited, so a
`job_class: huge-context` row would derive a Fable pin and *recreate the very defect s9 healed*.

**Correct the rows, do not widen the authority.** `governance` is unknown to the tier authority
(it appears in `cli/src` once, as an unrelated jules workstream handle) and derives to `haiku`.
Widening `_CLAUDE_OPUS_CLASSES_DEFAULT` would promote *every* fleet task labelled `governance`
estate-wide — a global spend change made to green one registry, and a consumer editing its own
authority to fit its rows. A sanctioned per-host seam already exists if ever wanted
(`logs/model-tiers.json` via `dispatch._claude_tier_overrides`).
→ s0 `governance` → **`canon`** (same act as s6, already `canon`); s4 `governance` → **`synthesis`**
(a distilled routing surface whose success metric is inverted). All nine then derive `opus`.

⚠️ **Two consequences to accept explicitly, not silently:**
1. **Adding `--agent` changes what the command *does*.** `start-worktree-session.sh:520-522` execs the
   kickstart only when `--agent` is present. Today the emitted command writes a capsule and stops;
   after this it launches a live session — and with `--conduct` it hard-fails if no broker is
   reachable. That is a real change to the operator's copy-paste path.
2. **It pins the vendor.** Every rendered `workstream.json` declares
   `lane_selection: derive_from_live_capabilities` / `provider_and_model: provider_neutral`, and the
   registry's own FIELDS block cites that to justify omitting `--agent`. The tier ladder is *Claude's*
   — there is no equivalent authority for gemini/agy/opencode, and the launcher would happily pass a
   meaningless `--model opus` to them. So `--agent claude` is the only correct emission: **pinning the
   vendor is the price of pinning the tier.** Ship the doctrine edit (checker docstring + registry
   FIELDS block) in the same PR rather than leaving the contradiction unstated.

### 3b. `branch_prefix` honored by the launcher

`scripts/start-worktree-session.sh:448` hardcodes `branch="work/$slug"`. Add `--branch-prefix`,
default `work`, plumbed through `limen workstream`, and emitted by the registry.

**Blast radius audited: nil.** No consumer keys off the prefix — `reclaim-worktrees.py:739-741`
matches the last path segment, `merge-policy.sh` has no prefix logic, and `work/` appears once
outside the launcher (`conduct/task_execution.py:148`, a different branch minter). Every existing
caller (`cli.py`, `lead-spawn.py:142-158`, the test harnesses, humans) passes no prefix and is
unaffected. **Refuse an unknown prefix (exit 2), never coerce** — and order that check *before the
binary probe*, the lesson α just paid for twice.

One sharp edge to document: `branch` is bound into the capsule identity digest
(`workstream-capsule.sh:1197,1208-1212`), so changing a running stream's prefix makes the re-render
refuse with "branch identity changed". That is the correct failure; note it in the FIELDS entry.

### 3c. `owner_of_record` validated — new check H

Assert the path exists (hard), **and** that it is git-tracked — but split the two: use plain
`git ls-files -- <path>` and treat a `None` (git unavailable) as "cannot tell", not "untracked", so a
broken environment can only under-report. Nine of ten owners are tracked; `organs/consulting` is a
directory and matches fine by pathspec. Only s8 fails — which is the point.

### 3d. `max_children` → a real `FanoutBoundsV1` — *split it; 4b is its own domain*

⚠️ **The premise that `conduct submit` is the on-ramp is wrong.** `submit` mints a lease with
`lease_ttl` defaulting to **15 minutes** (`broker.py:159,364`), and `_expire_leases` then flips the
run to `expired` (`:1528-1533`) while `_validate_lineage` refuses a parent not in
`{reserved, running}` (`:1328`). A root created by `submit` **stops accepting children 15 minutes
into an 8h lane.** The only shape that survives is `submit_graph` with `intent.kind == "fanout-root"`,
which releases the lease and parks the run at `running` (`:505-506,517-527`) — and `submit_graph` is
**not exposed on the conduct CLI** at all.

⚠️ **And re-entry idempotency is closed on both sides.** The kickstart regenerates its session id
every entry (`workstream-capsule.sh:406`), so a second submit trips
`ConductConflict("duplicate work changed its identity…")` (`broker.py:291-302`) — fatal under
`set -euo pipefail`. `adopt` cannot rescue it either: a human-protected session cannot be adopted
(`:1232-1233`), and the umbrella registers `--human-protected`. Fixing this means a **capsule-stable
conduct session id**, which collapses two distinct human sessions into one audit identity — a
domain-sized decision, not a rider.

**So split:**

- **3d-a (ship now, safe).** Construct the real `FanoutBoundsV1(max_children=…, max_depth=1)` at the
  registry so `> 10000` is red, and thread the bound to the lane as
  `LIMEN_FANOUT_MAX_CHILDREN`/`_MAX_DEPTH` beside the existing lineage exports
  (`workstream-capsule.sh:424-425`). The bound becomes typed, transported and identity-bound; the
  broker enforces it the moment a parent exists.
- **3d-b (defer to its own registry row,** `s10-umbrella-fanout-onramp`, `requires: [s9]`**).** The
  stable conductor identity, a root-packet minter, a `conduct submit-root` verb, and a
  `.limen-workstream/conduct-root.json` sidecar with skip-on-re-entry.

⚠️ **Capsule-identity hazard applies to 3d-a.** Any new digest field must be **conditional**, exactly
as `lane_pin_digest_field` is, or every capsule on disk fails `verify-identity` on next render. The
required regression test is a render with `origin/main`'s library followed by a re-render with the new
one, asserting no identity error. Also: the run id must **not** go in `workstream.json` —
`_validate_v2_contract:172` asserts an exact top-level field set — hence the sidecar.

---

## Phase 4 — LEAVES: open the domains in dependency order

Graph (verified from the registry):

```
s0 ──┬─> s2, s3, s4, s5          s6 ──> s7          s9 (independent)
     └─> s5 ──> s8               s1 (settled)
```

Critical path is **s0 → s5 → s8** (depth 3). So Phase 2's s0 correction is worth more than any other
single row: it alone governs four domains.

Order: **α (#1619 → s9)** → **s0 settled/re-scoped** → then `{s2, s3, s4, s5}` and `s6` open in
parallel → `s7` (after s6) and `s8` (after s5). Do not hand-list the ready-set — after each merge,
re-derive it:

```bash
python3 scripts/check-session-streams.py --all
```

Each lane launches from the emitted command, which after Phase 3a carries its own derived tier.

---

## ω — the fixed point

**ω is reached when `--all` prints no openable domain and every settlement is backed by an executed,
side-effect-free, stream-distinguishing predicate.**

To make that self-sustaining, STREAMS must become a **beat sensor** in
`institutio/governance/sensors.yaml` with `omega_eligible`. It is currently a pr-gate row only, and
that is the wrong home: settlement is a function of **whole-repo state**, not of the streams files'
diff, so a path-scoped gate cannot see it change. As a sensor the beat re-derives the ready-set every
cycle and the fixed point becomes observable rather than asserted.

> **CORRECTION 2026-07-29 — this rung is NOT this plan's to execute; it belongs to
> `s10-axis-coverage`.** That domain's `intent.md` already measures the exact gap ("None of the six
> named axis predicates appear in `sensors.yaml`, so `scripts/omega.sh` does not cover them either")
> and its mission is to make the axis SET declared data — of which registering STREAMS is one
> instance, not a standalone errand. Executing it here would preempt a declared owner and fork the
> work, which is the failure this registry exists to prevent: route through the canonical surface,
> and the surface here is the stream that owns the axis set. **The ω condition above stands; the
> mechanism that makes it self-sustaining is s10's deliverable.** s10 is already `ready`.

---

## Verification

1. **α:** stripped-PATH harness → exit 2 for codex-absent, jules-absent, codex-present. Then
   `python -m pytest cli/tests/test_workstream_contract.py cli/tests/test_workstream_command.py -q`.
2. **Phase 1 — test the failure modes, not the happy path.** Prove each closed defect:
   - a commit body *mentioning* an id no longer settles it;
   - a commit that carries `Settles: <sid>` **and** edits the registry does **not** settle it
     (replay `b5d7909f` — the actual false positive);
   - a stream with a valid trailer but a failing `predicate_command` is **not** settled;
   - a `predicate_command` with a side effect (s8 without `--dry-run`) is **rejected by the checker**,
     never executed.
3. **Phase 3:** `--all` output carries `--agent`/`--model`; check G red on `job_class: governance`;
   check H red on the s8 owner path before its correction and green after; existing
   `start-worktree-session.sh` callers still land on `work/<slug>`.
4. `python3 scripts/check-gates.py` and `python3 scripts/check-sensors.py` green (registry↔consumer
   parity) after any gates/sensors row is added.
5. `scripts/verify-scoped.sh` per branch; then `scripts/merge-policy.sh <PR#>` → on exit 0,
   `scripts/await-pr.sh <PR#> --merge`.

## Shipping

One concern per branch. **`cli/**` is a deploy trigger** (`gates.yaml:47-53`), so any PR touching it is
website-sensitive and needs the **full CI rollup** green — keep cli changes in their own PR so the
governance/scripts PRs (not deploy-triggering) merge freely once CLEAN.

**Adoption is load-bearing and easy to forget:** Phase 1 must also add the `Settles: <stream-id>`
convention to `CLAUDE.md` (§ Merge & Branch Protocol) and to the registry header. Without it nobody
writes the line and *every stream stays unsettled forever* — the mechanism would have no authors.
There are currently **zero** tests for `check-session-streams.py`; Phase 1 adds the first.

Chunks, in order (Phases 3a/3b/3c are mutually independent and can land in parallel):

| branch | contents | website-sensitive? |
|---|---|---|
| `heal/lane-tier-pin` | **α — #1619, in flight** | yes (`cli/**`) |
| `heal/streams-settlement` | 1a, 1a′, 1b–1e + first test file + CLAUDE.md convention | no |
| `docs/streams-reground` | Phase 2 rows + intents + #1607 disposition | no |
| `feat/streams-tier` | 3a + the `tier_for_classes` extraction | yes (`cli/**`) |
| `feat/streams-branch-prefix` | 3b | yes (`cli/**` for the CLI flag) |
| `feat/streams-owner-check` | 3c + the s8 path fix | no |
| `feat/streams-fanout-bound` | 3d-a only | yes |
| — | 3d-b becomes **row `s10-umbrella-fanout-onramp`**, not a branch | — |
| `feat/streams-sensor` | ω | no |

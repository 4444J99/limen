# The audience axis becomes law — and the Meeseeks court gets jurisdiction

> **Execution record.** Landed as PR #1694 (the disposition matrix's collab column), #1695 (the
> audience derivation law + `check-audience.py`), #1696 (the residue census + `IF-HOT-CACHE`), and
> the branch carrying this file (`check-plan-decisions.py` +
> `PREC-2026-07-30-plan-decisions-dont-bind`). This document is committed rather than left in the
> agent runtime for the reason ARC C exists: a plan that lives only in a gitignored directory is
> the purest form of the defect it describes.

## Context

The operator said, in another thread:

> "we decided that the partner estate (along with totally solo work) needs to split themselves into
> public/private (me and collab) and private/public (me and the world); also remember if anything we
> only keep a hot flash cache — there shouldn't be sprawling — think of mr meeseeks: each is summoned
> for a purpose then self executes and returns to the source once the task is complete leaving no
> residue behind."

**He is not repeating himself out of drift — he is repeating himself because the decision never
became law.** Both halves are already written down, verbatim, in `docs/plans/2026-07-30-portvs-astra-consolidation.md`
(committed to `main` 2026-07-30, PR #1682):

- **Decision 4 — the audience split** (lines 19–26): every storefront repo, partner estate AND
  totally-solo work, declares `audience: world | collab | self`; the custody doctor enforces GitHub
  parity. *"Never a hand list."*
- **Decision 5 — the Meeseeks law** (lines 27–31): every summoned surface is born for one purpose,
  returns its result to source, and self-erases; residue is a defect caught by predicates, *"never a
  periodic cleanup chore."*

Neither binds anything. A plan document is Tier-2 prose; the registries are law. That gap is the
whole task — and it is the **same defect class this session already fixed twice today** (the
visibility effector that planned nothing; the publish adjudicator wired to no organ — PRs #1689,
#1690). `censor/precedents.jsonl` already names it: `PREC-2026-07-10-declared-but-unwired-is-a-defect`.

### What is actually true today (verified, not recalled)

**The audience tier already exists in the code — unnamed, in exactly one place.**
`scripts/moat-audit.py:66-84` treats a partner-granted repo as exposed *regardless of visibility*
("A partner's eyes make the tree exposed") and applies a **stricter** rule than world-public gets:
`repo_secret_posture()` fails RED on any Actions secret on a granted repo, because a push
collaborator can exfiltrate via a workflow edit. So the system already believes `collab` is a
distinct audience. It just cannot say so anywhere else. Everywhere else the binary swallows it:
`scripts/publication-policy.py:253` maps any value not starting with `"pub"` to `"private"` — a
`collab` string would be silently accepted and mis-dispositioned, with no error.

**The live defect the split names is real and countable.** 11 partner-lane repos (5 private, 6
public, all on `4444J99`), 7 live constellation lanes — but `institutio/github/access.yaml` carries
only **4 grant rows**. Two private partner lanes (`4444J99/micro-tato`, `4444J99/mirror-mirror`)
have no grant at all: the partner cannot see their own lane. Meanwhile
`4444J99/peer-audited--behavioral-blockchain` is public *and* granted — world and collab at once,
which the current model cannot even represent.

**The Meeseeks court exists but has no jurisdiction over the residue.** PR #1681 shipped
`scripts/verify-hot-cache.sh` ("exit 0 ⟺ this machine is disposable", 5 rungs, beat-wired via a
`sensors.yaml` row) — but R5 explicitly **excludes** worktrees and quarantines, and nothing measures
the actual sprawl:

| Residue | Measured now | Reaper | Wired? |
|---|---|---|---|
| `docs/prompt-atom-ledger.json` | **571 MB**, append-only | none exists | — |
| `.agent-runtime/` | **10 GB** (opencode 8.0G, codex 1.9G) | `scripts/agent-state-metabolism.py` | **written, wired to nothing** |
| remote branches | **1,616** (~730 named orphaned in `estate.yaml:128`) | `reap-remote-branches.py` | double-dark, acceptance ledger **0 bytes — never armed once** |
| git worktrees | **39** across 5 roots | `reclaim-worktrees.py` | beat-wired (silent no-op until `3e0d1692`) |
| local branches | **517** | `reap-branches.py` | beat-wired, armed |
| `logs/` | 127 MB, 3,592 files | `disk-capacity.py` | truncates one log file only |

Three of those reapers (`reclaim-worktrees.py`, `reap-branches.py`, `reap-clones.py`) are hand-wired
into shell (`drain.sh`, `clone-maintenance.sh`, `heartbeat-loop.sh`) rather than declared as
`sensors.yaml` rows — which violates this repo's own registry law ("adding a beat sensor = adding
one registry entry"). And `docs/IDEAL-FORMS-LEDGER.md` has **no IF-\* entry** for the law, so there
is no tracked distance-from-ideal.

### Intended outcome

He never has to say either of these again, because both become executable: a declared field with a
doctor rung that detects drift forever, and a court whose jurisdiction actually covers the residue.

### Scope boundary (deliberate)

The consolidation plan's own division of labor assigns **decision 4 to this lane** ("the `audience:`
field PR routed through their machinery") and **ARC 5's local cleanup to the sibling lane**. This
plan takes decision 4 in full, takes only the *jurisdiction* half of decision 5 (registry rows,
caps, ledger entry — all additive governance data), and does **not** delete a byte off his disk.
Remote-branch reaping stays behind its filed double-dark lever, untouched.

---

## ARC A — the audience axis becomes law

A first pass at this design was stress-tested and **substantially refuted**. Three of its claims were
verified firsthand and each changes the shape; they are recorded here because the wrong version is
the tempting one.

- **The enum is not total over the live estate.** Decision 4 says `world` = "public, **solo**."
  `4444J99/peer-audited--behavioral-blockchain` is `portal_public` *and* carries a live push grant
  (`estate.yaml:801` — *"jtenen lane intact"*; `access.yaml:34`). Not solo, so not `world`; not
  private, so not `collab`. **One of the four grant rows falsifies `collab ⟺ private + grant` before
  a line is written.** A rung that enforced the biconditional would demand a public→private flip of a
  traction repo and sit permanently at war with class G, which reads `portal_public` and demands
  public.
- **The two "defect" repos are queued for publication.** `4444J99/micro-tato` and
  `4444J99/mirror-mirror` both carry `publish_candidate: true` (`estate.yaml:783-784`) — they are the
  two that swept green this session and wait only on the arming valve. And `micro-tato-play` is
  described as *"public play surface of micro-tato"* (`estate.yaml:744`) — an operation/form pair
  that was **never registered as a `split:`**. So "the partner cannot see their own lane" is not
  self-evidently the defect: micro-tato may be rob's invited lane (→ `collab`, drop the candidacy,
  register the split) or a solo publish candidate (→ `world`, and the register's row is stale).
  **That is a judgment nobody has made**, and deriving an answer would let people-data silently
  decide a publication question.
- **`audience` is already the name of a shipped axis.** `spec/contracts/surface-manifest.schema.json:5`
  — *"this schema decides AUDIENCE access (persona routing)"* — with `persona: owner | client | public`,
  and `organs/governance/PUBLICATION-POLICY.md:68` names it as convergence row 3. `owner/client/public`
  is isomorphic to `self/collab/world`. A second enum for the same axis is the parallel-substrate
  failure the charter forbids.

### The corrected design

**A1 — declare intent as an override flag, never a third copy.** The observed audience is already a
total function of data the estate holds: `world` if public; else `collab` if ≥1 `access.yaml` grant;
else `self`. It is **computed at read time and materialized nowhere** — no column on the 10 classes,
no row on the 144 overrides. (A class column rots on arrival: `sauce_policy.private_classes` already
lists `conductor`, whose `classes.conductor.visibility` is `public` — proof these axes are distinct.)

But pure derivation has a fatal blind spot: `micro-tato` with no grant derives `self`, and
`self ⟺ private + 0 collaborators` passes **green** — the doctor would certify the live defect as
correct. So intent must be declared. It goes exactly where decision 4 says ("registry data in
`estate.yaml`") and in the shape that registry already uses for intent: **an `audience:` key on the
`repo_overrides` rows where intent differs from the derivation** — the same shape as the
`publish_candidate: true` flag sitting on those very rows. An `audience_policy` block in the
`sauce_policy` house style (`estate.yaml:522-538`) states the derivation and the precedence:
**observed GitHub state > per-repo judgment row > register-suggested intent.**

**A2 — the register suggests; it never writes.** `derive-streams.py` is *not* a transferable
precedent here: it emits regenerable prose, whereas this would emit access posture. The hazard is
concrete — remove a project from the register, the derived `collab` vanishes, the repo derives
`self`, the rung reads an existing human-decided grant as "undeclared exposure," and
`L-PARTNER-GRANTS`' machine-runnable direction is **removal**. An editorial edit to a people file
must never be able to stage revocation of a partner's access. So: `scripts/check-audience.py` reads
the register to **flag candidates for a human judgment row** and nothing else. It commits no file.

**A3 — widen the disposition matrix** (`scripts/publication-policy.py:218-256`). Keep the existing
`public`/`private` keys (renaming them breaks the shipped self-test); add `collab`. Declare the
vocabulary isomorphism once, in convergence row 3: `world ≡ public`, `collab ≡ client`,
`self ≡ owner` — so his words name the axis while the engine keeps the one shipped enum.

- **The one cell that justifies the column:** `internal_strategy`. Private is a safe home
  (`RESTORE_REDACT` — its doc literally says so); a shared tree is not, because premortems,
  positioning and raw session dumps routinely discuss *that collaborator*. New literal
  `KEEP_OFF_SHARED_HEAD` / `auto` — **added beside** `KEEP_OFF_PUBLIC_HEAD`, never a rename.
- `public_safe` stays `PUBLISH` / `his_lever`. Autonomy derives from the reversibility of the action
  the disposition *names*, and `PUBLISH` names the visibility flip — irreversible and outbound
  whether or not a collaborator is already inside.
- `secret` and `product_content` carry their private values unchanged.
- `personal_pii` keeps `REDACT_IDENTIFIERS`'s action but must **say what it does not cover**. The
  redactor is owner-scoped by construction, and the docstring calls the category-wide wildcard
  *"the 2026-07 over-redaction bug this engine exists to prevent."* On a collab surface the
  collaborator's own identifiers are a legitimate resident; a third party's are not, and nothing
  redacts them. Name the cell honestly rather than reporting "handled." **Do not teach the redactor
  third-party identifiers** — the self-test asserts `partner@example.com` and `/Users/someoneelse/…`
  survive, and breaking that resurrects the bug.
- **Fix a latent fail-open while here.** `disposition()` (line 253) maps anything not starting with
  `"pub"` to `"private"`, so `disposition("world", "internal_strategy")` returns `RESTORE_REDACT`
  ("safe home") for something actually public — the most dangerous cell collapses to the *permissive*
  value. Accept the five legacy+new tokens case-insensitively, map the three `visibility: any`
  classes to the **strictest** column, and `SystemExit` on anything else, matching the existing
  unknown-class style.

**A4 — extend class D; add one report-only rung.** `_collaborator_census` already enumerates the
**entire** user-scoped personal inventory unbounded (`gitvs.py:1067-1093`) — 100% coverage, ~14
calls. Reusing `posture_window()` here would *degrade* a security finding to a rotating slice with
days of lag; it is right for static protection drift, wrong for "someone can see this who shouldn't."
So `self`'s half is one predicate inside class D, and the genuinely new rung is a pure
intent-vs-observed join emitting **cites only, never reds, never a flip demand**:

1. register-named lane observed `self` → staged invite → cites `L-PARTNER-GRANTS` *(micro-tato, mirror-mirror)*
2. public + live grant → the fourth state the enum lacks; name it and cite the owed decision *(peer-audited)*
3. register-named lane carrying `publish_candidate: true` → judgment collision *(micro-tato, mirror-mirror)*

Behind `ratchets.audience_parity_armed: false`, per the house observable-before-autonomous pattern.

**A5 — the collisions are held by a red check, not by a list at him.** `check-audience.py --check`
exits 1 on a structural collision (`publish_candidate` ∧ declared `collab`; `never_grant_classes` ∧
declared `collab`). The question lives in a failing predicate with a named owner — which is the
charter's form for a genuine judgment — not in prose handed back across the table.

**Why a third value is not redundant.** The system already enforces this distinction in exactly one
place and cannot say so anywhere else: `scripts/moat-audit.py:65-73` — *"A partner's eyes make the
tree exposed, so these are audited regardless of visibility"* — and `repo_secret_posture()` (77-84)
applies a **zero Actions secrets** policy to granted repos that world-public repos never face,
"because any push collaborator can exfiltrate a repo secret via a workflow edit." `audience` names a
distinction the code already makes, once, unnamed.

**Do not** — each of these was the tempting first answer and each is refuted above: add `audience:`
to the 10 class definitions (a third copy of a fact `visibility` + `access.yaml` already carry);
write a `derive-audience.py` that emits rows into `estate.yaml` (a people-file edit could then stage
revocation of a partner's access); teach the redactor third-party identifiers (breaks the shipped
must-preserve self-test, resurrects the over-redaction bug); use `posture_window()` here (converts
100% coverage into a lagging slice on a security finding); let the rung demand a public→private flip
(puts it permanently at war with class G); or rename `KEEP_OFF_PUBLIC_HEAD` instead of adding a
sibling literal.

## ARC B — the Meeseeks court gets jurisdiction (measure, never reap)

`scripts/verify-hot-cache.sh` is honest about its own blind spot: R5 excludes worktrees and
quarantines "by marker, named here so the exclusion is visible, never silent," because those have
their own reap organs. The completion is therefore **not** to re-check cleanliness — it is to assert
that those organs are *keeping up*. One new artifact serves three existing patterns.

**B1 — `scripts/residue-census.py`.** Measures each residue class against a declared cap and names
the owning reaper for every breach. Read-only; deletes nothing. Classes and their current values:
worktrees (39), local branches (517), `.agent-runtime` bytes (10 GB), `logs/` bytes (127 MB),
`docs/prompt-atom-ledger.json` bytes (571 MB), remote branches (1,616 — **reported only**, owner is
the filed double-dark lever). Caps declared in `institutio/governance/parameters.yaml`
(`LIMEN_RESIDUE_*`), because the parameter panel is where configuration lives.
`--check` exits 1 on any breach; `--json` emits the census.

**B2 — the ideal gets a row.** `institutio/governance/ideal-forms.yaml` gains `IF-HOT-CACHE` whose
`probe` is B1 (`extract: "breaches=([0-9]+)"`, `ideal_value: 0`, `environment: host`), plus the
matching `### IF-HOT-CACHE` heading in `docs/IDEAL-FORMS-LEDGER.md`. `check-ideal-forms.py` then
enforces both directions and **derives** the status — the registry forbids a hand-written distance,
which is exactly why this belongs there rather than in prose. Verified new: `IF-HOST-PRESSURE`
covers memory/CPU/load, not disk residue; no existing ideal covers re-summonability.

**B3 — R6 in the court.** `verify-hot-cache.sh` gains one rung calling B1, so the disposability
predicate finally sees the residue it currently excludes. Same red-collector style as R1–R5.

**B4 — the beat.** One `sensors.yaml` row (`residue-census`, section heartbeat, gate
`LIMEN_RESIDUE_CENSUS`, advisory, daily) — the registry law's "adding a beat sensor = one registry
entry." `check-sensors.py` holds the parity.

**Explicitly NOT in this arc** — and why:

- **No bytes deleted.** ARC 5 of the consolidation plan owns local cleanup; it is the sibling lane's
  and it is destructive.
- **`agent-state-metabolism.py` is not beat-wired.** It is not a one-line sensor row: it requires the
  `/Volumes/Archive4T` vault mounted, dual-restoration verification, private receipts, and carries
  its own `RETIREMENT_AUTHORIZATION_REQUIRED` gate. Retiring 10 GB *is* the human-gated
  archive-then-delete step ARC 5 already describes. B1 measures it and names that owner.
- **Remote reap stays unarmed.** 1,616 remote branches sit behind a filed double-dark lever with a
  0-byte acceptance ledger. Census reports the count and cites the owner; nothing more.
- **The workspace-manifest gate is not reinvented.** Its pattern already exists one level down:
  `institutio/governance/root-manifest.yaml` + `scripts/check-root-manifest.py` hold the *repo* root
  to a declared manifest. ARC 5's promised gate is that same pattern applied to `~/Workspace`. Noted
  for its owner, not built here.

## ARC C — the root cause: a plan decision that binds nothing

Decisions 4 and 5 were correct, written down, and committed — and still had to be restated in chat,
because a plan is prose. Two artifacts close that, both cheap:

**C1 — the precedent.** One line appended to `censor/precedents.jsonl`:
`PREC-2026-07-30-plan-decisions-dont-bind`, type `recurring_friction`. The rule: a decision recorded
in a plan's "Decisions made for the operator" block binds nothing until it lands as registry data
plus a predicate; a plan may record a decision but may never be its only home. `authorised_by` cites
his own words in this thread. This joins the existing lineage
(`PREC-2026-07-10-declared-but-unwired-is-a-defect`, `PREC-2026-07-09-sensor-without-effector`,
`PREC-2026-07-08-ask-already-decided`) rather than starting a new one.

**C2 — the predicate.** `scripts/check-plan-decisions.py`, a member of the existing `check-*.py`
parity family (28 of them; 8 wired into `pr-gate.yml`). It parses every numbered decision in a
`## Decisions` block under `docs/plans/*.md` and requires each to name its binding home — a registry
path, a lever id, a precedent id, or an explicit `owed:` annotation. Exit 0 ⟺ no decision is homeless.
Wired into pr-gate alongside `check-params`/`check-gates`/`check-sensors`.

**One adjacent finding, filed not fixed:** `scripts/ask-gate.py` already implements the DERIVE
verdict that should have stopped me asking him a registry-owned question last turn — but
`_registry_decisions()` (lines 103–144) consults only `his-hand-levers.json`, `censor/precedents.jsonl`,
and `organ-ladder.json`, and the gate audits **board tasks**, never live conversation. `estate.yaml`
— the registry that owns visibility — is not in its token set at all. Adding it is a two-line change
in that function and it belongs to `check-ask-gate-migration.py`'s lane, not this campaign; recorded
in C1's precedent as the enforcement gap rather than silently absorbed here.

### One of the two "judgments" is already decided by his own doctrine

`micro-tato` has a public form twin — `micro-tato-play`, whose own row reads *"public play surface of
micro-tato"* — so under the split doctrine it is the **operation half**: stays private, becomes rob's
`collab` lane, and its `publish_candidate: true` is a leftover from before the twin existed. The pair
should be registered as the `split:` it already is in practice. **No operator input needed** —
derived from decision 4 plus `docs/repo-split-protocol.md`.

`mirror-mirror` has **no twin** (confirmed against `repo_overrides`, the product ledger, and all 8
shelves). Publish it as `world`, or make it charles's `collab` lane — that one is genuinely his, and
it is held by a red `check-audience.py` with a named owner, not recited back at him.

## Sequence

One concern per branch, cut fresh off `origin/main` (this worktree is 4 behind / 6 ahead).

1. **`fix/publication-policy-collab-column`** — the 3-column matrix, `KEEP_OFF_SHARED_HEAD`, the
   `disposition()` fail-open fix, the honest `personal_pii` cell, `PUBLICATION-POLICY.md`'s 2-column
   table + convergence row 3. Self-contained; touches no registry.
2. **`feat/audience-derivation-law`** — `check-audience.py` + the `audience_policy` block. Read-only,
   writes no rows.
3. **`heal/micro-tato-split-registration`** — register the operation/form pair, drop the stale
   candidacy, add rob's grant row. Doctrine-derived, no judgment.
4. **`feat/gitvs-audience-rung`** — the class-D predicate + the report-only rung behind the ratchet.
5. **`feat/residue-census`** (ARC B) and **`docs/plan-decisions-bind`** (ARC C) — independent of 1–4,
   can land in parallel.
6. Arm `ratchets.audience_parity_armed` only after the rung has been quiet for a full cycle.

## Verification

Per PR (`scripts/verify-scoped.sh` maps the diff to only the gates it implicates):

- **ARC A** — `python3 scripts/publication-policy.py --verify` (its shipped self-test) exits 0 with
  the widened matrix; `python3 -m pytest cli/tests/test_publication_policy.py cli/tests/test_gitvs.py -q`
  — note `test_publication_policy.py:171` asserts `disposition_rows == 10` and must become **15**
  (the count is computed at `publication-policy.py:612`). Acceptance test for branch 2 is a number,
  not a vibe: against today's tree `check-audience.py --check` must report exactly **2** collisions
  (`micro-tato`, `mirror-mirror`) and **1** public-plus-guest (`peer-audited--behavioral-blockchain`);
  after branch 3 the collision count drops to **1**. `gitvs.py doctor` shows the new cites with **no
  new fails and no increase in API calls** versus baseline.
- **ARC B** — `python3 scripts/residue-census.py --check` (exit code is the assertion);
  `python3 scripts/check-ideal-forms.py` green (proves the probe shape and derived status);
  `python3 scripts/check-sensors.py` green; `bash scripts/verify-hot-cache.sh` runs R6.
- **ARC C** — `python3 scripts/check-plan-decisions.py` green against the existing
  `docs/plans/*.md`, including the two decisions this campaign lands.
- **Whole-system** — `python3 -m ruff check cli/src cli/tests web/api mcp`, then
  `scripts/verify-whole.sh` before the last merge.
- **Closeout** — `scripts/no-tasks-on-me.sh` + `scripts/credential-wall.py --check` + a zero-change
  re-run of the census and the doctor.

Branch cadence: one concern per branch off `origin/main` (this worktree is 4 behind / 6 ahead — cut
fresh), squash-merged via `merge-policy.sh` → `await-pr.sh --merge`. None of these paths are
deploy-triggers, so merges are free once CLEAN.

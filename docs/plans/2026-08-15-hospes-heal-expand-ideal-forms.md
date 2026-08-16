# HOSPES — full heal, expansion, and evolution toward ideal forms

Issue: #2463
PR: (pending)

## Context

The 2026-08-14 completion campaign merged 12 PRs, closed 16 of the 17 issues in the
`HOSPES 1.0 Complete` registry, and left `done.sh` green on `b787d58`. It also deliberately
deferred **109 code-review findings** into 11 consolidated hardening issues (#70–#73, #76–#78,
#80–#83) rather than chase an advisory reviewer with no fixed point. That was the right call at
merge time. It is not a finished state: zero of the 109 boxes are checked, and `done.sh` cannot
see any of them, so the repo reports "done" while 40 P1s sit open.

This plan closes that gap on three axes the operator named — **heal**, **expansion**, and
**evolution toward ideal forms** — and treats the third as the reason the first two stay closed.

### The root finding

HOSPES has an unusually strong **declaration layer** and a missing **binding layer**. Nearly
everything is declared; almost none of it is bound to enforcement, and the 109 findings cluster
in exactly those unbound seams.

| Declared | Bound to? | Evidence |
|---|---|---|
| `spec/permission-matrix.yaml` — 6 `team_roles` with `reads`/`decides`/`scope` | **Nothing.** Only two tests read it, as text. | Enforcement instead lives in **14 module-local frozensets** (`clearances.py:45`, `sponsors.py:47`, `guest_crm.py:51`, …) reached through **7 divergent `_require_role` functions** with 4 exception types |
| `completion-registry.yaml` `predicate:` per issue | **Nothing executes them.** | It declares `tests/issue_predicates/test_issue_09.py`, which **does not exist**; `done.sh` is green anyway |
| `completion-registry.yaml` `required_surfaces:` (incl. `security`) | Vocabulary-checked, then printed. | No surface→evidence mapping exists |
| 25 `spec/*.schema.json` payload contracts | **No conformance harness.** | Schema drift recurred in **5 of 11** hardening issues (T9) |
| permission-matrix `rules` — append-only audit, 10-min host budget | **Nothing asserts them.** | No instrument in the repo measures review time (`grep` for `review_seconds`/`host_budget` → 0 hits) |

The sharpest single instance: `distribution.py:162` treats `actor_role is None` as the system role
and **permits** the write; `sponsors.py:73` treats the same input as a **refusal**. Identically
named helper, opposite fail-mode. Nothing could have caught that, because there is no single role
model to compare against — which is also why the backlog contains a genuine contradiction (#73.9
wants `host` admitted to guest history; #81.2 wants `host` refused a portal mint).

Two consequences shape every phase below: **fix the binding layer and ~46% of the backlog closes as
a side effect**, and **any per-finding heal that skips it will be re-litigated by the next review.**

### Decisions locked with the operator

- **Expansion = both, heal-gated.** Internal capability expansion proceeds now; the public-face
  split (`public_face_state: pending-split`) is queued as a distinct phase that cannot start until
  the heal predicate is green.
- **Pilots are unscheduled.** `ari_anthony.pilot_1` carries `deadline_at: 2026-08-05`, already
  lapsed. Treat the dates as aspirational, heal first, re-date when a real recording is booked.
- **Full tooling, gated.** ruff + mypy + CodeQL + bandit + pip-audit + Dependabot + CODEOWNERS,
  with the mechanical baseline landed as one isolated PR and every gate armed shrink-only.

---

## Phase 0 — Make the invisible visible (instrument before repairing)

Nothing here fixes a finding. It makes the heal measurable, which is what stops it regressing.

**0.1 — Hardening registry.** New `hospes/resources/spec/hardening-registry.yaml` + loader
`hospes/hardening_registry.py`, built by copying the proven shape of
`hospes/completion_registry.py`: frozen dataclasses, closed vocabularies, referential integrity,
derived `receipt_owner` URIs. One row per finding: `id`, `issue`, `priority`, `theme` (T1–T23),
`files`, `close_condition`, `status`. Reuse `replace_managed_block` / `managed_issue_block`
verbatim for the GitHub projection — they are already idempotent and preserve human prose.

**0.2 — Predicate runner.** `scripts/run_predicates.py` executes the `predicate` strings that
`completion-registry.yaml` has always declared and nobody has ever run. Expect it to fail
immediately on the missing `test_issue_09.py` and on `scripts/verify-storage-substrate.sh`, which
is referenced only as a substrate predicate and is therefore dead. That first red is the point.

**0.3 — Review-debt gate.** A new `done.sh` gate, `review debt`, running
`scripts/check_hardening.py --check`: derives open counts from the registry cross-checked against
live GitHub issue state, and reds when the P1 count exceeds a shrink-only ratchet baseline. Never a
hand-edited number — the count is derived, following limen's `ideal-forms.yaml` rule that *a row
may not carry a distance in the registry; there is no field to lie in.*

**0.4 — Two resolution passes the taxonomy proved are required.**
- **Attribution:** ~30 findings (all of #70–#77) carry no file annotation. Map each to a path
  before any parallel work is scheduled, or sweeps will collide.
- **Severity re-anchoring:** the backlog's priorities are mis-anchored. Path traversal
  (`integration_adapters.py`, #80) and clickjacking on the legally load-bearing consent form
  (`dashboard/guest/index.html`, #81 — `PORTAL_CONTENT_SECURITY_POLICY` omits `frame-ancestors`)
  sit at **P2**, while "register four event types in `config/domain_kernel.yaml`" sits at **P1**.
  Re-rank into the registry; do not inherit the labels.

**0.5 — Resolve the five contradictions before any sweep.** Recorded in the registry with a
decision, not silently picked: do-not-contact vs retry idempotence (#73.2 vs #73.1/#81.11);
`canExport` prescribed as a client-only fix (#71.5 — **needs a code check**, it may be a
mislabeled server hole); opposite-direction gating in one file (#82.8 vs #82.9); the `host`
role-model conflict (#73.9 vs #81.2 — resolved by Phase 1 and *only* by Phase 1); and #70.3
without #70.5, which restores a fail-closed predicate while still passing evidence-less migrated
rows — a false closure if landed alone.

**0.6 — Hygiene.** Remove the two stale campaign worktrees (`.worktrees/dossier`,
`.worktrees/issue-23`) and the tracked `build/lib/` copy that shadows grep results.

---

## Phase 1 — The convergence keystone: one role model

This is the plan's center of gravity. It resolves a contradiction, closes three whole themes, and
makes a recurrence structurally impossible.

**Make `spec/permission-matrix.yaml` the single authority.** Today it is read by no runtime code
while fourteen modules hand-maintain their own answer.

1. **Loader** — `hospes/permissions.py` parses `team_roles` into capability sets
   (`reads`/`decides`/`exports`), validating against `service.HumanRole`. Note the matrix and the
   enum currently disagree: the enum has six members including `editor`; the CLI at
   `hospes/__main__.py:1244` offers five; `demo_guide.py:26` knows four. Reconcile as part of this
   step and let the loader reject the drift thereafter.
2. **One helper, one exception** — `require_capability(actor, capability, action)` replacing the
   seven divergent `_require_role` implementations (`service.py:620`, `sponsors.py:72`,
   `distribution.py:160`, `network_dashboard.py:78`, `pilot_service.py:54`, `artifacts.py:115`,
   `partnership_records.py:26`). Fail-closed on `None` — deliberately choosing `sponsors.py`'s
   semantics over `distribution.py`'s permissive one, which is itself a latent security fix.
3. **Derive the client** — `dashboard/assets/capabilities.mjs` stops re-deriving role sets and
   consumes a capability list served from the matrix. This closes T21 **and** T22 in both
   directions at once, and it is the only shape that stops the whack-a-mole 82.8/82.9 pattern.
   Remember `dashboard/` is byte-mirrored at `hospes/resources/dashboard/` and gate-enforced
   (`tests/test_hospes_1_0_review_fixes.py:609`) — **every dashboard edit is a two-file edit.**
4. **Bidirectional parity predicate** — `scripts/check_permissions.py`, modelled directly on
   `scripts/check_guide_registry.py` (the best pattern in the repo, whose own comment states the
   rule: *"a hand-maintained view list turns 'add a view' into 'edit this gate too'"*). Asserts
   declared ≡ enforced ≡ client-visible, in both directions. Wired into `done.sh`.
5. **Close the three genuinely client-only gates** the audit found: `canSendPortalLink`,
   `canViewAnalytics`, `canExportAnalytics`. The analytics pair is structural, not an oversight —
   **`hospes/analytics.py` has no `actor_role` parameter on any public function**, so this is 7
   signature changes plus 7 `api.py` call sites, not a one-line guard.
6. **Fix the optional-actor hole** — `service.get_opportunity(conn, id, actor=None)` silently
   skips the tenant check when the actor is omitted (`service.py:737`). Make it required and audit
   the call sites.

**Rollout: shadow first, then enforce.** Ship `require_capability` logging refusals without
raising, run the suite and the dashboard-quality job, then flip to enforcing in a second PR. A
live-behavior refactor across 103 routes should not land as a single flag day.

---

## Phase 2 — Shared-fix sweeps (13 sweeps, covering ~39 findings)

Each is one PR with a helper plus its call-site migration and a regression test. Ordered by
severity-after-re-anchoring, not by the backlog's original labels.

| Sweep | Shape | Closes |
|---|---|---|
| **Portal entry point** | `guest_portal.create_app` has **no production mount** — only tests construct it. Serve it from `hospes/__main__.py`/`operator.py`. | Unblocks verification of the other 19 #81 findings; **do this first in the portal track** |
| **Portal intake path** | `POST /guest/intake` branches on the client-supplied key `"session" in payload` (`guest_portal.py:799`), reaching `complete_intake`, which skips consent, the three-date rules, and the field vault. Require a session; move the reference-only API off the guest route. | #81.1, #81.19 |
| **Trusted origins** | A caller-supplied `base_url` overrides `HOSPES_PORTAL_BASE_URL`, returning a valid signed token in a fragment on an attacker-controlled origin (`api.py`). Derive origins only from config. | #81 T20 — the most classically exploitable finding in the backlog |
| **Error envelope** | One FastAPI exception handler on `hospes/api.py`. | 3 checkboxes / **17 CodeQL alerts**; precedent PR #47 cleared this class before |
| **Tenant scoping** | `resolve_policy(tenant_id, show_id)` + a lint sweep for `show_id`-only lookups; thread expected scope through the portal app. | 7 findings across #70/#71/#72/#76/#80/#81 |
| **Do-not-contact** | Apply the existing `guest_crm.is_do_not_contact` guard at every link-mint and outbound path. | #73.1, #81.11, #73.10 |
| **Schema conformance** | One harness validating every emitted payload against `spec/*.schema.json` and every receipt/event against `config/domain_kernel.yaml`. | 6 findings, and prevents the class that recurred in 5 of 11 issues |
| **Canonical identity** | Route all call sites through `guest_crm.guest_identity`; make UUID derivation injective. | 5 findings |
| **Validate-then-commit** | Transaction wrapper for mint-and-write paths. | 4 findings (two are the same bug reported twice) |
| **Path canonicalization** | `resolve_within(root, ref)`. | 2 traversal findings — re-ranked upward |
| **Money** | Currency-grouped aggregation type. | 2 verbatim-duplicate mixed-currency findings |
| **Receipt provenance** | Constructor taking actor from the authenticated principal, `occurred_at` from the event. | 2 findings |
| **Pagination** | `iterate_all()` replacing the silently-capping helper. | 2 findings |

Add the missing portal authorization test — no test anywhere asserts a role refusal on
`POST /v1/opportunities/{id}/portal-link`. Follow the established pattern at
`tests/test_api.py:437` (refuse wrong roles → confirm the right role succeeds); the repo already
has **81** such `403` assertions, so the culture exists.

---

## Phase 3 — Per-site heal (~59 independent findings)

Batched by file and theme into ~10–12 PRs, each with a test. Concentrations:
`hospes/research_agent.py` (9), `hospes/distribution.py` (5), `hospes/network_dashboard.py` (4),
`hospes/migrations.py` (2). Themes with no shared surface: fail-open predicates (T2), ignored
config (T4), readiness probes (T5), races and lease lifetime (T7), idempotence (T8), checksum
verification (T14), migration backfill (T15), dead-end states (T23).

**Migration discipline carries forward from campaign decision D1.** Migrations contend on a single
file: add `_migration_023` before the `MIGRATIONS` tuple at `migrations.py:1773`, append the row,
and **update the hard-coded `assert migrations.LATEST_VERSION == 22` at `tests/test_migrations.py:27`**.
Grep for duplicate `def _migration_` names before every land — Python's last-def-wins shadows a
duplicate silently and git merges it cleanly, which bit PRs #63 and #64 live.

---

## Phase 4 — Tooling floor

The repo has **no linter, type checker, or security scanner of any kind**. That absence is why 109
findings arrived from an LLM reviewer and why 13 CodeQL stack-trace alerts on `api.py` went
unnoticed.

- **PR A (mechanical, isolated):** add `ruff` config to `pyproject.toml` and land the formatting
  baseline alone, touching nothing else, so it stays reviewable.
- **PR B:** `mypy` in non-strict mode with a shrink-only error baseline.
- **PR C:** `.github/workflows/codeql.yml`, `bandit`, `pip-audit`, `npm audit`,
  `.github/dependabot.yml`, `CODEOWNERS`. Add each as a new job under the existing `hospes-done`
  aggregator — note its `needs:` array and `env:` block are hand-maintained **in two places**.
- Repo-level GitHub security settings are externally gated; file as a lever rather than a chore.

---

## Phase 5 — Expansion (internal capability)

**5.1 — Promote the post-1.0 backlog to a typed registry.** ROADMAP rows 1–10 are today held only
by *substring existence in prose*, via a hand-maintained Python list literal
(`CONTENT_CHECKS`, `scripts/check_asks.py:26`), while the shipped 17 get a validated YAML registry.
That asymmetry is the clearest structural defect in the estate. Give the deferred partials the
same treatment `completion-registry.yaml` gave the issues.

**5.2 — Record the ten open questions.** `docs/brainstorm-dossier.md` §5 already names where each
answer belongs; give each a registry row so an answer has somewhere to land.

**5.3 — The host-budget instrument.** The product's north star — ~10 operational minutes per week,
asserted in permission-matrix rule 6 and in `productization.md` — is measured by nothing. The
dossier names this itself: *"the first honest thing the pilot can produce is a number."* Instrument
review duration on the operator surface and emit it as a receipt. This is the single highest-value
expansion item, because every roadmap decision is subordinate to a budget nobody has ever measured.

**5.4 — Pilot policy schema.** Answer open question 1 (per-pilot vs per-partnership) and re-date
the lapsed `ari_anthony.pilot_1` deadline. Do not fabricate new dates — leave the field honest
until a recording is booked.

---

## Phase 6 — Ideal-forms ledger for HOSPES

Mirror limen's proven three-part shape: prose ledger (`docs/IDEAL-FORMS.md`), machine registry
(`hospes/resources/spec/ideal-forms.yaml`), parity predicate (`scripts/check_ideal_forms.py`). Two
rules carried over verbatim, both load-bearing: **the distance is derived, never a field** (there
is no place to lie), and **a `Status:` line contradicting its own probe is drift, not a stale note**.
A row without a probe must carry a `probe_absent_reason` — the executable form of "N/A is a vacuum."

| Row | Ideal form | Probe |
|---|---|---|
| `IF-ONE-ROLE-MODEL` | The matrix is the sole authority; every enforcement point derives from it | `check_permissions.py` |
| `IF-PREDICATE-EXECUTED` | Every declared predicate runs; declared-but-missing is red | `run_predicates.py` |
| `IF-REVIEW-DEBT-VISIBLE` | `done.sh` sees review debt; the count is derived and ratchets down | `check_hardening.py` |
| `IF-SCHEMA-CONFORMANT` | Every emitted payload validates against its schema | conformance harness |
| `IF-TENANT-ISOLATED` | No `show_id`-only lookup survives; scope is a type, not a convention | scoping lint |
| `IF-HOST-BUDGET-MEASURED` | The 10-minute north star is instrumented | receipt query |
| `IF-NO-SEND-ROUTE` | **Already at ideal** — structurally absent in four independent places | assert all four still hold |
| `IF-PILOT-RECEIPTED` | Pilot 1 closed by a real recording receipt | human-gated; `probe_absent_reason` |

`IF-NO-SEND-ROUTE` matters disproportionately: it starts green and its probe exists to keep it
green. A ledger where every row is red teaches nothing about which direction is home.

---

## Phase 7 — Public-face split (heal-gated, does not start early)

`organvm/hospes` is `sell-ready` in limen's product ledger and `public_face_state: pending-split`
in the constellation register. The estate's standing rule is that transcripts are vault-class and
**the public face is a split, never a flip.** Extract a public shell — docs, product narrative,
synthetic demo — leaving the private repo intact. Gate: the Phase 0 review-debt predicate must be
green first. Building a public surface on 40 unfixed P1s is the wrong order, which is why this
phase is last rather than parallel.

---

## Sequencing

```
Phase 0 (instrument) ──┬─► Phase 1 (role model) ──┬─► Phase 2 (sweeps) ──► Phase 3 (per-site)
                       │                          │
                       └─► Phase 4 (tooling) ─────┘
                                                   └─► Phase 5 (expansion) ──► Phase 7 (public face)
                                                   └─► Phase 6 (ideal forms, continuous)
```

Phase 1 gates Phase 2's capability sweeps — landing capability parity before the role model would
re-encode a client-only gate, which is precisely the mistake #81.2 names. Phase 4 is independent
and can run alongside. Phase 6 rows land as their probes become real, not in a batch at the end.

---

## Verification

Each PR: `bash done.sh` bare (exit code read directly, never through a pipe) plus full CI
(`python` × 3.11/3.14, `dashboard-quality`, `postgresql-16`, aggregated by `hospes-done`).
Merge only on `scripts/merge-policy.sh <PR#>` exit 0.

New gates must each demonstrate a **real red before their first green** — a gate never observed
failing is not known to work. Concretely: `run_predicates.py` should fail on the missing
`test_issue_09.py`; `check_permissions.py` should fail while any of the three client-only gates is
still unbound; `check_hardening.py` should report 40 P1s open on day one.

Whole-campaign fixed point, all of which must hold simultaneously:

```bash
bash done.sh                                   # all gates, incl. review debt
python3 scripts/run_predicates.py              # every declared predicate executes
python3 scripts/check_permissions.py           # declared ≡ enforced ≡ client
python3 scripts/check_hardening.py --check     # P1 count 0, derived from live issues
python3 scripts/check_ideal_forms.py --measure # every distance derived, no drift
```

Runtime verification, not just predicates: drive the guest portal end-to-end through its **new
production mount** (mint → exchange → submit), confirm a role refusal on the portal-link route with
a `host` bearer, and confirm the `complete_intake` bypass returns 4xx. Green gates never prove the
running surface behaves.

---

## Anti-goals

- **Do not chase the reviewer.** Residual findings become registry rows, never pre-merge
  obligations; bound any fix-on-review cycle at two rounds
  (`PREC-2026-08-12-advisory-review-loop-has-no-fixed-point`).
- **Do not re-propose roads already refused** — `docs/brainstorm-dossier.md` §4 records the
  autonomous mailer, in-repo transcripts, and live-provider defaults with their reasons. The send
  refusal is enforced in four independent places and every one of them stays.
- **Do not fabricate pilot dates** to make a lapsed policy look current.
- **Do not fix a Class-C-style finding by relocating it** out of a scanner's view.

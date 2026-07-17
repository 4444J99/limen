# IDEAL-FORMS LEDGER — limen fleet

Claude's own ideal-form ideas for the organism, tracked as **named params** — the same
weight as one of Anthony's asks (doctrine: *track my ideas like asks*; *distillation, not
reduction*). Precedent: `sovereign-systems--elevate-align/docs/IDEAL-FORMS-LEDGER.md` tracked
the Maddie project only; the limen fleet had **no** such registry — the "portals each
attempting their own ideal" were tracked nowhere. This is that registry.

Each entry is liquid, not a checkbox (per the AVTOPOIESIS gate): it names the **ideal form**,
measures the **distance from ideal** at a moment in time, and carries a **status** and an
**owner**. The ledger includes *itself* (self-reference is required, not optional).

| Field | Meaning |
|-------|---------|
| **Ideal form** | the condition when this is fully alive |
| **Distance** | how far from it we are *right now*, with evidence |
| **Status** | OPEN · PARTIAL · BLOCKED(human) · SEEDED · CLOSED |
| **Owner** | who closes the remaining distance |

---

### IF-FIRST-DOLLAR — the revenue close
- **Ideal form:** an executable first-dollar predicate that is green only when a *real payment
  has cleared*; the Exporter faucet open.
- **Distance:** every revenue product is code-complete; **tx-hash = 0**. The Exporter
  (`a-i-chat--exporter/`) still carries a literal `TODO_KO_FI_SLUG` and a build-time placeholder
  store ID.
- **Status:** BLOCKED(human) — `L-REVENUE-ACCT` requires account creation/KYC Claude cannot do.
- **Owner:** Anthony (create Ko-fi + Lemon Squeezy, paste `LEMONSQUEEZY_STORE_ID`) → Claude (wire).

### IF-AMALGAMATION — the future tense closes
- **Ideal form:** the fleet amalgamates portals faster than it spawns them; a predicate measures
  open-PR + unmerged-branch debt and the merge daemon drives it *monotonically* down.
- **Distance:** 75 open PRs, 157 unmerged branches (2026-06-25); the daemon rebases stale-base
  PRs but `gen-*`/`FORCE-route` duplicates accrete faster than they merge. No debt-trend predicate.
- **Status:** PARTIAL — merge daemon live (`merge-policy.sh`); no monotonic-debt predicate yet.
- **Owner:** Claude (predicate) + merge daemon.

### IF-LIVE-TREE-COHERENCE — the live checkout never drifts
- **Ideal form:** the live daemon checkout is always `≡ origin/main`; capture/sync keeps it
  fast-forwarded; no ahead/behind divergence, no stranded local commits.
- **Distance:** live `main` is **ahead 6 / behind 24** with uncommitted daemon state
  (`tasks.yaml`, `state/`, `obligations-ledger.json`); 6 local commits novel by patch-id
  (one is `health-office` — needs a PHI scan before any push). Residue of the
  capture↔sync deadly-embrace.
- **Status:** OPEN.
- **Owner:** Claude + the sync organ.

### IF-SESSION-NON-CONTENTION — sessions don't sit in contended worktrees
- **Ideal form:** an interactive session's cwd is an isolated, non-recycled worktree; the fleet
  never rebases or `clean`s the tree a live session is working in.
- **Distance:** this session's cwd (`.claude/worktrees/stateful-dazzling-rainbow`) was checked
  out to a fleet PR branch (`fix/creds-hydrate-noninteractive-guard`, #276), rebased, and amended
  **by the daemon mid-session.**
- **Status:** OPEN.
- **Owner:** Claude (worktree allocation / harness convention).

### IF-SENSOR-REGISTRY — the beat sensors are declared data, all consumers derive
- **Ideal form:** the beat's continuous-runtime sensors live in one registry
  (`institutio/governance/sensors.yaml`, VIGILIA's third axis beside GATES + PARAMETERS); the beat loop
  and every consumer that reads a sensor gate **derive** from it; `check-sensors.py` holds it in parity.
  Adding a sensor is one registry entry, never a hand-wired shell block in three places.
- **Distance:** DONE for the beat. Phase 1 (#884) shipped the registry (now 20 sensors), `beat-sensors.py`
  (`--list`/`--run`), and `check-sensors.py` (pr-gate). Phase 2 landed the consumer flips: `metabolize.sh`
  **derives** its whole sensor loop from the registry — dark-first behind `LIMEN_BEAT_DERIVE` (#914,
  proven byte-equivalent by a 23-script test + an observed real-sensor run), then default-on with the 20
  hand-wired `── 0x ──` blocks deleted (#935, −227 lines). Two consumers that read sensor gates from the
  old shell location were repointed to the registry so they didn't go blind: `check-params.py`
  (`registry_referenced_tokens`, #935) and `armed-valve-audit.py` (`discover_sensor_valves`, which reads
  each sensor's gate + `armed_valve_type` from the registry — a fleet lane landed this, healing the
  ARMED 45→26 coverage regression #935 introduced; a thinner in-flight fix, #938, was closed as
  superseded). `check-sensors.py` D-parity now passes with **zero gate literals in the shell**, purely
  via derive-runner detection.
- **`omega.sh` derives too.** A fleet lane took the convergence past the metabolize loop: sensors carry
  an `omega_eligible` capability (registry-declared fixed-point checks, each with a label/tier/command),
  and `omega.sh` derives those rungs via `beat-sensors.py --list-omega` / `--run-omega` rather than
  hardcoding them. Same capability shape extends the registry to `schema_version 0.2`: `armed_valve_type`
  (behavior-valve classification, read by `armed-valve-audit.py`'s `discover_sensor_valves`), `args_when`
  (conditional argv like `--apply`), and scheduled `cadence`/`timeout`. So every consumer that reads a
  sensor fact now derives it from the registry — the ideal form is fully realized, not partially.
- **Status:** DONE (2026-07-11). The beat sensor estate is registry-owned across all consumers
  (metabolize loop, `check-params`, `armed-valve-audit`, `omega.sh`); adding a sensor — or a fixed-point
  rung, or a conditional valve — is one registry entry, and consumers work unchanged if an id is renamed.
- **Follow-up (tracked, not blocking):** promote the three *domain-agnostic* predicates
  (`check-fork-safety.py`, `check-test-hygiene.py`, `check-main-green.py`) to the ecosystem layer
  (`organvm-engine`, per `docs/agent-instruction-standard.md`) so the pattern becomes cross-repo law —
  dark-first, once proven in limen. The registry itself is limen-intrinsic and stays here.
- **Owner:** Claude + tabularius.

### IF-MAIL — the correspondence organ answers, tiered and fail-closed
- **Ideal form:** every reply-owed email is driven to *answered* autonomically — drafted, tiered,
  and (for the narrow SAFE tier, when armed) sent — with the tier decision as **declared data**
  (`mail-tiers.yaml`, the 4th VIGILIA panel) and a paired sensor red until the loop closes. Legal /
  money / personal mail **never** auto-sends; the operator is never the default send button.
- **Distance:** nearly closed. Effector (`scripts/mail-beat.sh`), done-predicate
  (`scripts/check-mail-answered.py`, now the `mail-answered` beat sensor), the tier **registry**
  (`institutio/governance/mail-tiers.yaml` + `check-mail-tiers.py`, PR #1010), the fail-closed
  **sender** (UMA `send_drafts.py`, PR #166, ships DISARMED), and now the **keyed headless path**
  (UMA `IMAPProvider.append`/`create_draft` + `draft_writer._select_saver`, PR #168; the
  `creds-hydrate.py` gmail lanes routing `GMAIL_APP_PASSWORD` + `GMAIL_USER` into `~/.limen.env`,
  2026-07-14) all exist and are wired into the beat. The keyed path **designs out the macOS TCC
  Automation grant** for Gmail drafts — lever `L-MAIL-AUTOMATION-GRANT` #960 is downgraded from
  required to *optional fallback* (non-Gmail accounts only). Remaining distance: the SAFE tier is
  opt-in and currently empty (grows on trust); actual sending stays DISARMED (`LIMEN_MAIL_SEND=0`) —
  arming is the operator's valve.
- **Status:** PARTIAL (2026-07-14) — registry + sender + sensor + keyed headless path shipped and
  wired; the only open distance is opt-in SAFE-send arming, which is deliberately the operator's valve.
- **Owner:** Claude + mail.

### IF-CONFIG-OWNERSHIP — every host config path has one declared owner
- **Ideal form:** a config-ownership constitution at the OWNER (`domus-genoma`
  `.chezmoidata/config-ownership.json`) declares app / cartridge / SPLIT / operator per host
  config path; SPLIT files get a `modify_` (owner atoms asserted, app blocks preserved
  verbatim); every `.chezmoiignore` abdication carries a declared owner (deliberate
  record-only sources via `source_is_record`); `check-config-ownership.py` (predicates A–F +
  `--prove-diff`) holds it in CI. An app can never silently destroy an owner atom again
  (~/.codex/config.toml clobber, 2026-07-14), and a dead template can never hide behind its
  own ignore line again (predicates C/F — the founding defect lived 2026-06-03 → 2026-07-15).
- **Distance:** constitution (15 declarations) + codex `modify_` + parity check landed via
  domus-genoma PR #302 (30 tests; `--prove-diff` GREEN on the live file with 0 changed paths,
  so activation is a no-op diff). limen side: `chezmoi-drift.py` default scope broadened to
  `.claude,.local/share/codex` so an owner-atom clobber is fatal in the beat. LOCAL activation
  (`chezmoi apply`) waits on the live-source unpark (`L-CARTRIDGE-REPOINT` #563). Narrowing
  finding recorded on the lever: master's nil-safe `allowed_signers` (`aeea31ef`) means unpark
  alone un-wedges — identity-data population is NOT a precondition for the un-wedge (still
  needed for a faithful full apply). Successors tracked in the registry itself: gemini
  `settings.json` split→modify promotion; codex `hooks.json` reconcile→template.
- **Status:** PARTIAL — landed-not-activated.
- **Owner:** domus-genoma CI (parity) + lever `L-CARTRIDGE-REPOINT` (activation) + Claude (proof run).

### IF-HOST-PRESSURE — exogenous load never stacks unseen
- **Ideal form:** every host-pressure axis — memory, CPU load, the backup crawler, test fan-out —
  has an executable gauge and a mechanical valve; no stack of individually-legitimate loads can
  thrash the host because each is gated where it starts, and the gauges themselves are watched.
- **Distance:** incident 2026-07-15 (16 GB host: swap 6.4/7.2 GiB, load 5.7, 24 min after reboot)
  had three stacked loads, all invisible to the armed VITALS memory gate: (a) Backblaze
  `bztransmit` re-crawling ~748 worktree roots / 61 GiB of regenerable state at 95 % CPU,
  (b) one session running FULL `pytest tests/` twice concurrently — the scoped-verification law
  was prose-only, and (c) ~10 claude bg-spare processes tipping RAM into the swap spiral.
  Three forms close it: **(1)** `scripts/hooks/pytest-scope-guard.sh` + the `pytest-scope` audit
  in `claude-workflow-guard.py` (this branch) make the scoped-verification law mechanical;
  **(2)** a VITALS load-average axis + `host-pressure-stale` sensor rung (branch
  `feat/vitals-load-axis`) gives the throttle/shed valve a CPU gauge and watches the gauge;
  **(3)** the Backblaze exclusion estate — sensor `backblaze-exclusions` + the `--apply`
  effector — retires the crawl storm. 2026-07-16 recurrence (a `bztransmit -updatebackupstats`
  pass held 8.6 GiB → swap 17.3/18 GiB) proved bzinfo.xml is USER-owned, falsifying the 7/15
  "pane click is his hand by construction" premise: the estate is organ-owned
  (`LIMEN_BACKBLAZE_APPLY`, armed by default per operator directive 2026-07-16), lever
  `L-BACKBLAZE-EXCLUDE` retired, and the missed Workspace worktree pools joined
  REQUIRED_EXCLUDES.
- **Status:** SHIPPED — all three forms mechanical; the pane returns only as a fallback if
  Backblaze ever re-roots bzinfo.xml (the sensor's escalation names it).
- **Owner:** Claude (all three forms).

### IF-LEDGER-OF-IDEALS — this ledger (self)
- **Ideal form:** every Claude-originated ideal is a tracked named param here; the ledger is
  linked from memory and the autopoiesis heartbeat references it (closing the self-loop).
- **Distance:** created 2026-06-25; not yet wired into a verification/heartbeat lane.
- **Status:** SEEDED (this commit).
- **Owner:** Claude.

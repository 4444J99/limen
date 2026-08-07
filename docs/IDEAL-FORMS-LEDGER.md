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
| **Status** | OPEN · PARTIAL · SEEDED · BLOCKED(human) · SHIPPED · DONE · CLOSED |
| **Owner** | who closes the remaining distance |

**This prose is the narrative; `institutio/governance/ideal-forms.yaml` is the machine form.**
Every heading below has a row there naming the **command** that measures its distance, and
`scripts/check-ideal-forms.py` (VIGILIA's seventh axis) holds the two in parity — including
the rule that a **Status:** line contradicting its own probe is *drift*, not a stale note.
Update a distance with `python3 scripts/check-ideal-forms.py --measure`, never from memory:
this ledger sat for 34 days with its own self-entry recording that nothing verified it, during
which `IF-LIVE-TREE-COHERENCE` drifted 5× and `IF-SHARED-SUBSTRATE`'s counts went stale. A row
may not carry a distance *in the registry* — there is no field to lie in; the number is derived.

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
- **Distance:** DERIVED — `python3 scripts/pr-debt-trend.py --series` prints every observation,
  `--check` is the probe. Do not hand-write a number here; the line above it stood at
  "75 open PRs (2026-06-25)" for 38 days while the real figure passed 1,100.
- **Evidence (2026-08-02):** the series was already committed and nobody was reading it —
  `gitvs.py` writes `open_pr_count` into `docs/github-pr-debt-ledger.json` and every write is a
  commit, so five observations sat in `git log`: 1059 → 1111 → 1115 → 1117 → **1164** across
  2026-07-22…07-25. The ideal's word is "monotonically **down**"; the measured trend is **+105 in
  three days**. Then recording stopped: the producer, `gitvs.py pr-debt`, is wired to nothing —
  no sensor, no gate, no beat rung — so the newest observation is eight days old. Its owner of
  record is `GITVS-UNCAPPED-PR-DEBT-0715`, which the diurnal morning page names as the board's
  critical next action, and which asks for a predicate that already exists.
- **Evidence (2026-08-05):** the producer is wired. The reason the series stopped was not neglect —
  **there was never a recorder.** Every observation in it is a side effect of an unrelated feature
  PR that happened to regenerate the ledger (#1337, #1503, #1508, #1495, #1541), so it ended when
  that work did. `pr-debt-trend.py --record` is the writer, running as the `github-pr-debt`
  heartbeat sensor: a cheap due-check every cadence, a full census only on its own wall-clock
  interval (`LIMEN_PR_DEBT_RECORD_INTERVAL_HOURS`, 20h — inside the probe's 3-day tolerance with two
  missed runs of margin), and a `ship-docs.sh` PR **only when `content_sha256` moves**, so a
  PR-debt recorder cannot add to the debt it measures.
- **Evidence (2026-08-06):** a recorder fixed the *supply* of observations; it did not make the
  document uncarryable by anything else, and the passenger commits named above stayed possible.
  `tasks.yaml` had never had that exposure — it has a keeper, SHA compare-and-swap, and
  `task-writer-audit.py` to catch a bypass writer *before* it can race. The debt ledger had a
  convention and nothing enforcing it. `scripts/check-ledger-custody.py` (gate `ledger-custody`,
  registry `institutio/governance/ledger-custody.yaml`) closes that: every commit touching a
  governed ledger must be a keeper ship (A), every production toucher must be declared (B), and
  every committed row must be a distinct, correctly-ordered census (C). The five historic
  passengers are baselined as history; a sixth is a red check. C is the write-side twin of the
  read-side defect fixed in #1873, where a live uncommitted working copy was counted as a second
  observation and the resulting window shift reported **+182 from 1111** for a series whose truth
  was **+234 from 1059** — so the number this ideal is measured by was itself wrong.
- **Status:** PARTIAL — merge daemon live (`merge-policy.sh`); the trend probe reports distance and
  the producer now feeds it on a cadence. The open distance is the *trend itself*: the last measured
  reading was **+105 over three days**, and the ideal's word is monotonically down.
- **Owner:** Claude (predicate) + merge daemon.

### IF-PUBLICATION-ESTATE — every repo's visibility is a judged, enforced decision
- **Ideal form:** the whole GitHub estate carries its publication policy as declared data — every
  repo classified (vault / operation / portal / floor) with a `why:`, visibility drift a red
  predicate, private→public flips history-swept + lever-gated, the public tail converging to an
  SEO standard by beat, mixed repos split by the fresh-history protocol. Zero unclassified, zero
  unswept flips, zero hand-maintained lists.
- **Distance:** engine SHIPPED (PRs #1152–#1159, 2026-07-16): 308/308 classified (108 judgment
  rows), rungs G/J/K/M armed, flip pipeline + SEO organ + split protocol live-dark. Residual is
  ENACTMENT — the armed valves (`LIMEN_SEO_BACKLOG_APPLY`, L-SEO-METADATA, L-PORTAL-PUBLISH-WAVE-1)
  and the owed splits (session-meta, hospes transcripts), all lever/registry-homed; SEO baseline
  6/166 passing.
- **Status:** SHIPPED (engine) / OPEN (enactment).
- **Owner:** GITVS + publication-policy organs; his hand for the three levers.

### IF-HOT-CACHE — the machine holds nothing it cannot re-summon

- **Ideal form:** the local floor is a hot flash cache. Every summoned surface — worktree, agent
  runtime, scratch clone, session branch, fan-out agent — is born for one purpose, returns its
  result to source, and self-erases; losing the disk loses zero state. Residue is a defect caught
  by predicates, never a periodic cleanup chore. (The operator's Meeseeks law, decision 5 of the
  2026-07-30 PORTVS/ASTRA plan.)
- **Distance:** DERIVED — `python3 scripts/check-ideal-forms.py --measure`.
- **Evidence (measured 2026-07-30 by `scripts/residue-census.py`):** four caps breached. Worktrees
  **38/8**; local branches **520/40**; `.agent-runtime` **10,663 MiB / 2,048**;
  `docs/prompt-atom-ledger.json` **571 MiB / 128**. Remote branches sit at **1,620** against a
  cap of 100 but are counted report-only, because their relief is double-dark behind a filed lever
  whose acceptance ledger has never once been written to. `logs/` is the one class **within** cap
  (127/256).
- **Why the distance went unseen:** `verify-hot-cache.sh` (PR #1681) shipped the court and is
  honest about its own blind spot — R5 excludes worktrees and quarantines "by marker … never
  silent" because those carry their own reap organs. Nothing then asked whether those organs were
  **keeping up**. Two of the six classes have no working relief at all:
  `scripts/agent-state-metabolism.py` is written and wired to nothing (and cannot simply be
  beat-wired — it needs the Archive4T vault mounted, dual-restoration verification, private
  receipts, and carries its own `RETIREMENT_AUTHORIZATION_REQUIRED` gate), and the atom ledger —
  the single largest artifact on the machine — has **no reaper whatsoever**, despite being a
  regenerable snapshot of the private corpus, i.e. precisely what this ideal calls a hot cache.
- **Status:** PARTIAL — the court and the census are shipped and beat-wired; the reaping is not.
  Measuring was the missing half, and it was missing entirely.
- **Owner:** Claude (the census + the court) · the reap organs for relief · his hand only where
  relief is destructive (the archive-then-delete step, the remote-reap lever).

### IF-LIVE-TREE-COHERENCE — the live checkout never drifts
- **Ideal form:** the live daemon checkout is always `≡ origin/main`; capture/sync keeps it
  fast-forwarded; no ahead/behind divergence, no stranded local commits.
- **Distance:** DERIVED — `python3 scripts/check-ideal-forms.py --measure`.
- **Evidence (re-measured 2026-07-29 by `scripts/check-live-checkout.py`):** the hand-written
  distance this entry carried — "ahead 6 / behind 24" — had gone stale by **5×** and nobody
  knew, which is the defect the probe now closes. At 10:37 the live checkout sat at a
  **2026-07-23** commit: **behind 120**, one unpushed local commit, 12 dirty paths — so for six
  days the fleet executed a tree in which CORPORA, CONVERGENCE and ATOM-HOMING did not exist.
  It went unseen because `sync-release.sh` fails *open* when a park is not fully-pushed-and-clean,
  and nothing read that. Masked meanwhile by the governor holding autonomy paused behind the
  evacuation fence — a loaded gun, not a firing one. By 10:43 it had fast-forwarded on its own
  to `b5d7909f`; the probe then caught a **second, subtler** failure the first draft would have
  passed: comparing HEAD to the local `origin/main` *ref* reports `behind=0` on a checkout that
  simply has not fetched. Ground truth is `git ls-remote`, so a stale ref is drift, not a green.
- **Status:** OPEN — coherent at this instant, but the ideal is *never drifts*, and the only
  thing that makes that checkable is the probe; the beat-sensor wiring is the remaining distance.
- **Owner:** Claude + the sync organ (`scripts/sync-release.sh` owns reconciliation — a
  hand fast-forward of a daemon-contended tree races the running beat).

### IF-SESSION-NON-CONTENTION — sessions don't sit in contended worktrees
- **Ideal form:** an interactive session's cwd is an isolated, non-recycled worktree; the fleet
  never rebases or `clean`s the tree a live session is working in.
- **Distance:** DERIVED — `python3 scripts/check-ideal-forms.py --measure`.
- **Evidence:** the founding incident — this ledger's original entry — was a session whose cwd
  (`.claude/worktrees/stateful-dazzling-rainbow`) was checked out to a fleet PR branch
  (`fix/creds-hydrate-noninteractive-guard`, #276), rebased, and amended **by the daemon
  mid-session.**
- **Evidence (2026-08-06):** the row's stated distance was **stale, and the probe is what found
  it.** Enumerating every path that can rewrite or remove a tree turns up three, and two were
  already guarded: the dispatch allocator *preserves* an existing worktree directory and retries
  under a fresh `secrets.token_hex` suffix rather than reusing it — so the #276 mechanism above can
  no longer recur — and `reclaim-worktrees.py` is liveness-gated on its delete path. Only the
  **live checkout** was exposed, through `sync-release.sh`, which every beat runs `git switch`,
  `git reset --hard` and `git stash push` against `$LIMEN_ROOT` while consulting nothing but git
  state. That guard now exists (`live_checkout_occupant`, consulted at each destructive site), and
  the distance is `exposure + incidents`, measured by `scripts/check-session-contention.py`.
  Three exclusions in the probe are load-bearing, and each was found by *running* it on the
  operator host rather than by reading code: **nested worktrees** (16 of this host's 31 linked
  worktrees sit under `$LIMEN_ROOT`, so the naive containment rule reports it occupied in close to
  the modal state), **gitignored ground** (`reset --hard` only rewrites tracked content, so two
  codex plugin-cache processes were not occupants), and **non-session processes** (an MCP server
  and a static file server sat in tracked directories; the ideal's subject is *"an interactive
  session's cwd"*). Without all three the guard would fire constantly and the sync organ would
  never converge — recreating the failure `IF-LIVE-TREE-COHERENCE` already records. It fails
  **open**, inverting its sibling probe, for the same reason. A clean fast-forward is never
  blocked; only the destructive valves defer.
- **Status:** SHIPPED — every tree-rewriting path is occupancy-guarded and contention is now a
  recorded, counted event rather than an unobservable one.
- **Owner:** Claude (worktree allocation / harness convention).

### IF-HARNESS-SENSED — the Claude harness root is declared, resolved once, and sensed
- **Ideal form:** the Claude harness runtime tree — the external substrate the fleet reads its own
  session state from — is declared once (PARAMETERS: `LIMEN_CLAUDE_HARNESS_ROOT`), resolved in
  exactly one place (`cli/src/limen/harness_paths.py`), and sensed at beat cadence
  (`scripts/harness-root-probe.py`), so relocating it is a red check rather than a silent blinding.
  The fleet senses its work product (lint, tests, contracts, deploys); it must also sense the worker.
- **Distance:** DERIVED — `python3 scripts/check-ideal-forms.py --measure`.
- **Evidence:** none — probe green. Reached 2026-07-30 after the harness moved its tree from
  `~/.claude` to `<repo>/.agent-runtime/claude` and the location, hard-coded in **ten** places,
  blinded every consumer at once with nothing going red: `action_admission` stopped recognising
  plan-file writes (breaking plan mode, and re-breaking PR #1521's fix six days after it landed),
  CONTINUITY globbed an empty directory while still reporting `"status": "ok"`, and
  `claude-workflow-guard`'s untiered-fan-out audit silently found no sessions. Detected only because
  the operator got angry. Precedent: `PREC-2026-07-30-external-substrate-undeclared`.
- **Status:** DONE (2026-07-30).
- **Owner:** Claude (`limen.harness_paths` + `harness-root-probe` sensor).
- **Next form:** the same shape for the remaining vendor roots (`~/.codex`, `~/.copilot`,
  `~/.gemini`, opencode's sqlite) — each is undeclared today and is the same bug waiting.

### IF-SENSOR-REGISTRY — the beat sensors are declared data, all consumers derive
- **Ideal form:** the beat's continuous-runtime sensors live in one registry
  (`institutio/governance/sensors.yaml`, VIGILIA's third axis beside GATES + PARAMETERS); the beat loop
  and every consumer that reads a sensor gate **derive** from it; `check-sensors.py` holds it in parity.
  Adding a sensor is one registry entry, never a hand-wired shell block in three places.
- **Distance:** DERIVED — `python3 scripts/check-ideal-forms.py --measure`.
- **Evidence:** DONE for the beat. Phase 1 (#884) shipped the registry (now 20 sensors), `beat-sensors.py`
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
- **Distance:** DERIVED — `python3 scripts/check-ideal-forms.py --measure`.
- **Evidence:** nearly closed. Effector (`scripts/mail-beat.sh`), done-predicate
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
  *(2026-08-05: check D read this PARTIAL against a green probe and called the prose stale. The prose
  was right and the row was under-declared — the probe counts DRAFTS at one instant, so it is blind
  to the DISARMED send valve this status reports, and one green inbox reading cannot prove a claim
  about every message. The probe is now `instantaneous: true`, which lets distance fire and forbids
  achievement. The repair was in the contract, not the sentence.)*
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

### IF-NO-MODAL — no approval question for non-destructive work, with the gauge left alive
- **Ideal form:** zero approval questions for non-destructive work in every lane, with the
  remaining destructive boundary *derived and measurable* rather than switched off: the trust
  hook wired from the cartridge source, `permissions.ask` carrying its five-rule fail-safe
  backstop, and `permissions.autoMode.allow` teaching the classifier the same boundary the hook
  enforces — so `defaultMode` stays `"auto"`. `bypassPermissions` is explicitly **not** the
  ideal: it does not close the distance, it deletes the instrument (you cannot measure "does it
  ask?" where nothing can ask), and it silently un-gates the `rm` class that once wiped the live
  checkout. `never-hang-permission-spec.md` R1/R4/R5 + §Design-consequences-2.
- **Distance:** DERIVED — `python3 scripts/check-ideal-forms.py --measure`.
- **Evidence:** the estate was **measured but unregistered** — `dialogs-silenced.sh` has printed
  the classes since 2026-07-09 across 25 recorded raisings, while this ledger carried no row, so
  nothing held the measurement to an owner. Two defects found 2026-07-31 and closed here:
  **(a)** the hook's standalone branch was far stricter than its own `cd`-chain branch — `cd $W
  && npm run build` was silent while `npm run build` *from inside `$W`* prompted; closed by a
  cwd-gated fallback reusing `analyze_clause`, matrix 77 → 99 cases with the boundary asserted
  (sudo, force-push, non-disposable `rm`, primary-checkout `reset --hard`, `$(`, pipes,
  redirections, background forks, and a bad clause inside a good chain all still fall through).
  **(b)** class 1d detected the unwired hook but carried only a printed cure string while its
  neighbour 1b carried an organ (`heal-hook-drift.sh`) — closed by `scripts/heal-hook-wiring.py`,
  which asserts hook + `ask` + `autoMode` in the **cartridge source** (never the rendered file —
  the old cure text instructed a Rule #6 violation) and then `chezmoi apply`s.
  **(c)** the effector's first arming failed closed: it parsed the source with `json.loads`, but
  the live template's statusLine carries `"command": {{ printf … | toJson }}` — an action
  producing a JSON value at the *structural* level — so the source is not parseable and never
  will be. The wrong thing was the predicate, not the parser: "is the source valid JSON?" is not
  the property that matters, **"does the source render to valid JSON carrying all three
  assertions?"** is. Rebuilt as a uniquely-anchored textual splice proven through `chezmoi cat`,
  restoring the backup on any failure, with `scripts/tests/heal-hook-wiring.test.sh` (16 cases)
  pinning the non-JSON shape, idempotence, backup, verbatim action preservation, and hard-stop
  exit 2 on an absent or ambiguous anchor. It refused rather than corrupting a permission file —
  the fail-closed half was already right.
  Remaining distance is exactly one operator act: arming that effector.
  Armed 2026-07-31; three further defects surfaced only by running it against the real host,
  each now pinned by a case: the source is a **template, not JSON** (statusLine carries an
  action producing a JSON value, so the predicate became "does it RENDER to valid JSON?");
  the deploy would have **silently dropped `model`** (IF-CONFIG-OWNERSHIP in reverse — the
  cartridge clobbering an app atom, since the entry declares no `app_managed`); and a **false
  green**, where a correct-but-undeployed source reported clean while the live gate was still
  open. Two sensor defects went with them: 1d used `endswith` and so reported NOT WIRED
  against a correctly wired gate (the wiring is a *guarded* invocation ending `|| true`), and
  1a demanded `bypassPermissions` for green — so the estate could never reach ALL CLEAR while
  holding the configuration this very ledger recommends.
- **Status:** SHIPPED — probe exits 0; every permission class in `dialogs-silenced.sh` green
  (`defaultMode` 'auto' + hook wired + five ask rules + `autoMode.allow`). The only residue is
  the **`split` + `modify_` promotion** of `.claude/settings.json`, which retires `--allow-drop`
  by making `model`/`theme` app-owned instead of discarded — tracked on IF-CONFIG-OWNERSHIP,
  whose successor list already names this exact pattern.
- **Owner:** Anthony (arm the effector) + Claude (hook, effector, matrix). The arming is
  genuinely his: the auto-mode classifier blocks the **act** of an agent widening its own gate,
  not merely the path — verified 2026-07-31 to cover the chezmoi source and even a read-only
  dry-run. That is a correct guardrail. The effector is deliberately **not** beat-wired for the
  same reason: an auto-armed valve here would let the system widen its own gate unattended.

### IF-HOST-PRESSURE — exogenous load never stacks unseen
- **Ideal form:** every host-pressure axis — memory, CPU load, the backup crawler, test fan-out —
  has an executable gauge and a mechanical valve; no stack of individually-legitimate loads can
  thrash the host because each is gated where it starts, and the gauges themselves are watched.
- **Distance:** DERIVED — `python3 scripts/check-ideal-forms.py --measure`.
- **Evidence:** incident 2026-07-15 (16 GB host: swap 6.4/7.2 GiB, load 5.7, 24 min after reboot)
  had three stacked loads, all invisible to the armed VITALS memory gate: (a) Backblaze
  `bztransmit` re-crawling ~748 worktree roots / 61 GiB of regenerable state at 95 % CPU,
  (b) one session running FULL `pytest tests/` twice concurrently — the scoped-verification law
  was prose-only, and (c) ~10 claude bg-spare processes tipping RAM into the swap spiral.
  Four forms close it: **(1)** `scripts/hooks/pytest-scope-guard.sh` + the `pytest-scope` audit
  in `claude-workflow-guard.py` (this branch) make the scoped-verification law mechanical;
  **(2)** a VITALS load-average axis + `host-pressure-stale` sensor rung (branch
  `feat/vitals-load-axis`) gives the throttle/shed valve a CPU gauge and watches the gauge;
  **(3)** the Backblaze exclusion estate — sensor `backblaze-exclusions` + the `--apply`
  effector (PR #1147: bzinfo.xml proved USER-owned, retiring lever `L-BACKBLAZE-EXCLUDE`;
  exclusions are organ-tended) — retires the crawl storm; **(4)** the closed pressure loop
  (2026-07-16 recurrence: swap 17.3/18 GiB and 94 MB free RAM while jetsam reported only
  'warn' for hours, every relief step manual) — a VITALS swap/starvation axis with
  sustained-warn escalation, the `host-relief` effector rung (restarts over-ceiling
  `com.limen` agents via kickstart; escalates untouchable root hogs with the pre-formed
  `sudo kill` one-liner), onset-deduped macOS notifications (`scripts/_notify.py`, also
  wired into `host-pressure-stale`), and RSS/wall-clock self-bounds in `overnight-watch.py`
  (issue #1148: one tick wedged 51 min at 3.1 GiB).
- **Evidence (2026-08-06):** this row sat `probe: null` for a reason that was right about live
  pressure and wrong about the ideal — *"a one-shot repo probe would report the pressure of
  whatever machine happened to run pr-gate."* True, and a good reason not to measure the
  **weather**. But the ideal's own sentence is *"every axis **has** an executable gauge and a
  mechanical valve … and the gauges are watched"* — estate completeness, which is a repo fact.
  The vacuum was a noun error, not a missing capability. `institutio/governance/host-pressure-axes.yaml`
  now declares the estate (6 axes + the watcher, read **by capability**, never by sensor id) and
  `scripts/check-host-pressure-estate.py` derives the distance: every axis must keep a gauge whose
  named symbol still exists in its source, and a valve that is **armed-by-default** (`default: "1"`
  on an `args_when` entry carrying `armed_valve_type`). It is a ratchet, not a thermometer — it
  cannot go red because the operator compiled something, only because a gauge was refactored away
  or a safety valve was quietly disarmed. That second case is the SILENT-OFF class
  `armed-valve-audit.py` names, applied to the specific axes that thrash this host. The registry
  declares six axes where the prose enumerates four: swap is a distinct assessor in `vitals.py`
  with its own severity, and disk has a full gauge+valve pair — declaring fewer axes than the
  estate defends would make the ratchet weaker than the system.
- **Status:** SHIPPED — all four forms mechanical; the operator is no longer the sensor of
  last resort. The only human residue is the pre-formed root-kill one-liner, pushed by
  notification when it exists.
- **Owner:** Claude (all four forms).

### IF-LEDGER-OF-IDEALS — this ledger (self)
- **Ideal form:** every Claude-originated ideal is a tracked named param here; the ledger is
  linked from memory and the autopoiesis heartbeat references it (closing the self-loop).
- **Distance:** DERIVED — `python3 scripts/check-ideal-forms.py --measure`.
- **Evidence:** created 2026-06-25 with the gap recorded as "not yet wired into a
  verification/heartbeat lane" — **still exactly true 34 days later**, `metabolize.sh` referencing
  this ledger only in a *comment*. That is what a hand-maintained distance does: it decays with
  nothing to notice, and two entries here had. Closed 2026-07-29 for the **verification** half:
  `institutio/governance/ideal-forms.yaml` + `scripts/check-ideal-forms.py` (checks A–E) make
  every distance a derived number, wired into pr-gate as the seventh VIGILIA axis. The
  **heartbeat** half closed the same day: the `ideal-forms-distance` rung (`sensors.yaml`,
  cadence 12, advisory) runs `--measure`, which additionally executes the `host` and
  `network` probes pr-gate cannot — and that is the whole reason a beat rung exists, since
  a distance measures the SYSTEM, not the diff, and rots with neither file edited. It
  earned itself within the hour: `IF-LIVE-TREE-COHERENCE` read `at-ideal` at 11:0x and
  `drift=1` by 12:0x as merges landed and the live checkout fell a commit behind.
- **Status:** DONE — the self-loop is closed: the ledger is a registry, the registry has a
  predicate, the predicate runs per-PR *and* per-beat, and the predicate's own row points
  at itself (environment `self`, declared and never executed — the cycle guard).
- **Owner:** Claude.

### IF-DECORUM — no public surface is ever egg-facing
- **Ideal form:** DECORVM (`scripts/decorum-keeper.py`) federates the estate's six quality organs
  (experience / visual / seo / countenance / links / moat) plus a new polish/voice lane into ONE
  verdict (`logs/decorum.json`, schema `limen.decorum.v1`); departments + the severity floor are
  declared data (`institutio/governance/decorum-surfaces.yaml`); an unmeasured department is
  skipped fail-open, never failed. It runs every beat (the `decorum` sensor, cadence 6), files one
  idempotent `DECORUM-<lane>-<surface>` ticket per finding through the tabularius broker when its
  deliverable valve is armed (`LIMEN_DECORUM_APPLY=1`, dry-run otherwise), and re-queues a prose
  surface for model-in-the-loop voice-judgment whenever its content changes. Fully alive ⟺
  `--sweep` is green at a fixed point (nothing on any public surface is currently embarrassing).
- **Distance:** DERIVED — `python3 scripts/check-ideal-forms.py --measure`.
- **Evidence:** Phases 0–2 + 4 landed and verified (2026-07-22): federator + beat-wire + HTML face
  + deterministic polish lane + effector proven idempotent against an isolated board;
  `check-sensors` green (53 sensors). First live sweep is RED — it correctly surfaced a moat leak,
  the portfolio rendering as unstyled HTML, and 3 other broken frontends (these are real, pre-existing
  egg-faces, now ticketable). Phase 3 voice-judge is the on-change queue + `decorum-judgments.yaml`
  store; the model scoring is the companion judge (sibling of experience-judge), SEEDED. Off-platform
  surfaces (LinkedIn / social bios / résumé PDF) are designed-in registry slots (`off_platform: {}`).
- **Status:** PARTIAL — keeper + mentor live and green-wired; the estate it watches is red until its
  findings are worked (that redness is the point, not a defect).
- **Owner:** Claude + the `decorum` organ (beat) + `his-hand-levers.json` for any off-platform capture.

### IF-LEARNING-ENGINE — one learning engine, many subjects (never build the 7th)
- **Ideal form:** The operator's **Adaptive Personal Syllabus (`aps`)** is the sole curriculum +
  personalization engine; **daily-engine** is the cadence spine; **application-pipeline/interview_prep.py**
  owns interview content; **agon**'s spaced-repetition is the one plugin; **gamified-coach-interface** is
  the reward surface; **my-knowledge-base** is the content-atom source. Every new study/prep need is a
  *subject* authored as `aps` `PersonalizedLesson` records + a `LearnerProfile` — never a new engine.
  Pedagogy primitives (Wings, personalization-first, ChainBlockARK provenance, quality gates, wave cycles,
  5-persona critique, evaluation→growth, Studio-Quest ladder) are load-bearing and preserved.
- **Distance:** Decision recorded + owners named (`docs/convergence/learning-engine.md`, 2026-07-23).
  First subject — **ASI FSE interview prep** — authored in the `aps` schema and driven by `agon`
  (ChainBlockARK ledger verifies intact). BLOCKER surfaced: `aps` can't run in-checkout (`koinonia-db`
  absent + organ-coded `generate`); the subject conforms to the schema rather than being invoked via
  `aps plan generate`. Phase 2 = lift daily-engine's core into a shared substrate, decouple `aps` from the
  organ taxonomy, wire gamified surface + KB feed, implement the critique-synthesis fixes.
- **Status:** PARTIAL — convergence decided + first subject converged (agon = thin tenant, greenfield
  `curriculum.yaml` retired); full `aps`-invocation + the Phase-2 lift are pending.
- **Owner:** Claude + the Adaptive Personal Syllabus (`aps`); ASI subject tracked in matter `job-asi-algora`.

### IF-SHARED-SUBSTRATE — a capability has exactly one implementation, imported not copied
- **Ideal form:** every capability in the estate has one owner; everything else is a tenant
  (a subject/cartridge in the owner's schema) or retired. The convergence registry
  (`institutio/governance/convergence.yaml`) is the machine form; `check-convergence.py` makes
  "never build the 7th" a red check instead of a memory.
- **Distance:** DERIVED — `python3 scripts/check-ideal-forms.py --measure`.
- **Evidence (measured 2026-07-25):** ZERO cross-repo code dependencies across ~310 repos — no
  internal packages, no submodules, no template repo; six Cloudflare Workers each hand-rolling
  Stripe/auth/rate-limiting; rubric logic encoded four ways; `data_export.py` copy-pasted across
  three repos; two full builds of the speech-score product, neither referencing the other or the
  existing `vox` voice infrastructure.
- **Status:** PARTIAL — registry live with **13** capabilities (**7** converged, **5** lifting,
  **1** counted vacuum: `mirror-drift-detection`); the worker-toolkit and daily-engine-core lifts
  are the named next extractions. *(The counts above read "12 (6/4/2)" until 2026-07-29 — stale
  the moment a row landed. They are now derived: `check-ideal-forms.py` extracts the unresolved
  count from `check-convergence.py` and fails when this prose disagrees.)*
- **Owner:** Claude (registry + predicate) + the per-row `owner_of_record`.

### IF-ATOM-HOMING — every harvested atom lands in a git-tracked owner, or is dispositioned
- **Ideal form:** every semantic atom the harvest produces is either **homed** in an owner that
  git tracks, or **dispositioned** with a cited reason — residue and deferral both reaching their
  floor. Homing is **distillation, never transfer**: counts, ids and generalizations cross into
  the public tree; a *statement* never does (the executable form of `redacted: false ⇒ never
  leaves its store`). Adding a kind is one registry row.
- **Distance:** DERIVED — `python3 scripts/check-ideal-forms.py --measure`.
- **Evidence:** the axis shipped 2026-07-29 (PR #1608) — `institutio/governance/atom-homing.yaml`
  (8 kinds, each with a home / `admits` gate / unit / ratchet), `check-atom-homing.py` (checks
  A–G), a statement-free `atom-census.yaml`, and a monotonic residue ceiling. What it *measures*
  is the open distance: of 4,099 drained atoms, **4,099 remain residual** and **2,080 are
  deferred** — homing itself has not begun. Two fail-open bugs found by negative-testing before
  merge (a nonexistent public home read as advisory; a `re.escape`d pattern making `git grep -E`
  exit 2, which the caller read as "no matches", silently disabling the entire leak scan).
  Blocked only in appearance: the corpus is sealed in `organvm/arca`, restorable off the
  evacuation fence's measured volume.
- **Status:** PARTIAL — the registry and predicate are live; the homing is the work.
- **Owner:** Claude (registry + predicate) + the per-kind `owner_of_record`.

### IF-DOMAIN-STREAMS — the operator's streams are life/work domains, derived
- **Ideal form:** "what session streams do I open? (~6-10)" is a derivation, never a recollection:
  one `family: domain` row + cartridge per workstream channel (`derive-domain-streams.py`, from
  `workstream.py` meta lanes + `organ-ladder.json` pillars), ordered by `open_rank` with the
  operator-ratified head (correspondence, financial, representation, consulting, legal, health,
  education, governance, contributions — 9, inside his stated 6-10); `limen streams` opens them by
  default, the constellation family stays the consulting domain's interior, and check N holds the
  projection to the roster on every pr-gate.
- **Distance:** DERIVED — `python3 scripts/check-ideal-forms.py --measure`.
- **Evidence:** shipped 2026-07-30 after the question was answered wrongly three times (governance
  phases s0-s10; per-project collaborator lanes; per-person lanes still one altitude low). Root
  cause measured by the full-history excavation (all AI apps, local + external + remote): the
  roster existed only as derived data — the operator deliberately declined to enumerate (Codex
  2026-06-26) — so every session that missed `workstream.py` re-invented a list. The lineage is
  distilled in `organvm/knowledge-corpus` `reduced/session-streams-domain-lineage.md`; the probe
  is the generator's own `--check`.
- **Status:** SHIPPED — the family, generator, launcher default, and parity check are live.
- **Owner:** Claude (generator + checks) + the channel roster (`workstream.py` / `organ-ladder.json`).

### IF-DIURNAL — the day is a loop that scores its own claims and prunes itself
- **Ideal form:** the briefing is not a report, it is a falsifiable loop. Morning emits a
  dashboard PLUS claims of the form "section X's metric falls below N today"; midday re-probes
  each claim mid-flight and pushes only on drift; evening scores every claim held/missed/noop,
  carries the remainder forward, and CUTS sections that scored noop for
  `LIMEN_DIURNAL_CUT_THRESHOLD` consecutive ENGAGED days. Every line probes or wears its own
  staleness — a stale cache is withheld, a frozen registry is annotated, neither is ever printed
  as current. Sections are declared data (`institutio/governance/diurnal.yaml`) because an
  auto-cut cannot edit Python source, and `cuttable: true` implies both a `metric` and an
  `acted_when` because you cannot prune what you cannot score.
- **Distance:** DERIVED — `python3 scripts/check-ideal-forms.py --measure`.
- **Evidence:** the loop is built and closes — driven end to end 2026-07-31 in a sandbox: claims
  emitted, re-probed, scored, one cut fired at threshold, receipted to `cuts.jsonl`, reversed by
  `--uncut`. **It has never run against the live organism.** `docs/diurnal/` holds no dated page,
  so the 5-engaged-day cut runway has not started and no scoring rule has yet been tested against
  a real day. Two defects found by driving it are fixed (#1740 the liveness guard, #1742 three CLI
  edges); two residuals remain declared in `institutio/registry/organs.yaml` (fleet-wide cuts are
  proposals only; `calendar` is `render: absent` because no calendar state exists on disk anywhere
  in the estate). The emitted page also has no reader yet — no route, no index, no nav — so it is
  write-only until something reads it back.
- **Status:** PARTIAL — the organ, registry, predicate, sensor and parameters are live and merged
  (#1732); the loop's evidence is entirely synthetic until a live day runs.
- **Owner:** Claude (organ + predicate) · the beat's `diurnal` sensor (execution) · the operator
  (the `calendar` lever, which is a real gap and not a render bug).
- **Next form:** the claim/score/cut loop is not specific to a day. Every registry in the estate —
  GATES, SENSORS, PARAMETERS, STREAMS, ORGANS, IDEAL-FORMS — has a `check-*.py` proving structural
  consistency and NONE that scores whether the declared thing is doing anything. This ledger's own
  **Distance** field is hand-maintained prose; DIVRNAL's evening pass is its executable form. Do
  not start that generalization until a live day has proven the scoring rule on one registry.

### IF-AGENT-IDENTITY — protected-resource identity is a stable bundle, not a rotating path
- **Ideal form:** every TCC grant the fleet depends on is held by `org.organvm.domus.agent-host`,
  a bundle whose identity survives vendor version rotation — so a Claude Code update mints no new
  client and re-prompts for nothing. The count of rotating-identity paths holding live grants is
  zero **across every service**, and that number is *measured*: a run that could not read the TCC
  database reports `unmeasured`, never a clean bill of health.
- **Distance:** DERIVED — `python3 scripts/check-ideal-forms.py --measure`.
- **Evidence:** the architecture shipped 2026-07-31 (`docs/architecture/tcc-stable-agent-host.md`);
  the host is valid and signed under a fixed-host requirement, and all ten configured GUI/MCP
  ingresses route through `domus-agent-host ensure --`. What was missing was the *measurement*, and
  on 2026-08-05 the gap produced a false discharge of `L-DOMUS-AGENT-HOST-TCC`. Three defects, all
  in the instrument rather than the architecture:
  1. **The update guard was blind to the update switch.** `inventory_green()` refuses a green when
     `automatic_updates_disabled`, but `_disabled_updates()` scanned only `DISABLE_*` env vars,
     `settings.json` `env` blocks and `~/.limen.env` — never `autoUpdates` in `.claude.json`. That
     field was `false` in **both** config roots (`~/.claude.json` and the `CLAUDE_CONFIG_DIR` copy
     the live session actually reads), so the version could not advance, the "survives a vendor
     update" proof could never be exercised, and the audit printed `automatic updates: enabled`
     while they were off. The lever was discharged pinned to `version: 2.1.222`.
  2. **Unmeasured rendered as measured, in both directions.** With the TCC database unreadable
     `clients` is empty, which produced one false green (`active_leaks` ok/0 — asserting zero leaks
     having observed nothing) and two false reds (`stable_host_app_management_grant_missing`,
     `unrelated_app_management_grants_changed` — naming defects nobody looked for). The codebase
     already had the right instinct once: `stable_host_tcc_identity_missing` was guarded on
     `database_error is None`. It simply was not applied to its four siblings.
  3. **One service was judged; a different one was prompting.** `APP_MANAGEMENT_SERVICE` was the
     only service any predicate filtered on, while the operator's dialog reads
     `"<version>" would like to access files in your Documents folder` —
     `kTCCServiceSystemPolicyDocumentsFolder` against a path client under
     `~/.local/share/claude/versions/<version>/`. The audit already *read* those rows and already
     knew the path shape (`MANAGED_CLIENT_PATTERNS` → `claude_version`); nothing judged them. Track
     C could be perfectly green while every update re-prompted.
  All three are closed by executable contract in `cli/tests/test_tcc_identity_audit.py`, including
  the exact operator case: App Management spotless, `rotating_identity_active_grants` red.
- **A concurrent lane reached the opposite verdict, and the disagreement is instructive.** PR #1833
  (a parallel Fable 5 session, landed while this work was in flight) fixed a **real and separate**
  defect: `latest_met_receipt()` reverse-globbed and selected `closeout-latest.json`, the mutable
  beat-rewritten alias, so the lever's own discharge pointer flipped to `blocked` when the inventory
  regressed at 16:53Z. Pinning discharge evidence to an immutable timestamped receipt is correct and
  is **retained** — the test now guards the *retracted* discharge with it. But #1833 concluded the
  discharge stood, on the premise that "Track C's formula was met on immutable evidence 13:30Z–16:08Z."
  That premise is falsifiable and false: the pinned receipt
  (`closeout-20260805T133718Z.json`) records `normalized_inventory.automatic_updates_enabled: true`
  while `autoUpdates` was `false` in both config roots — so the guard passed on an unread field, and
  the same receipt records `update_attempted: false` with `version_before == version_after`.
  `non_noop: true` only because the current version exceeds the 2.1.220 cutover baseline, never
  because an update was observed. Defect 1 is upstream of the pin: no receipt, however immutable,
  can carry a proof that was never exercised.
- **#1833 also corroborates defect 3 empirically, and shows the sprawl reproducing itself.** It found
  that grants attached to `versions/2.1.222` at 16:22Z (AppleEvents) and 17:07Z (Removable Volumes) —
  *after* the 14:14Z discharge — and filed them as `L-TCC-VERSIONED-CLIENT-LEAK-2-1-222`. That is
  exactly the class `rotating_identity_active_grants` now detects automatically, found by hand; and a
  lever **named for a version** is the sprawl pattern migrating from the TCC database into the lever
  registry. Routing the interactive lane through the host retires the pattern, not just the instance.
- **The measurement needs a grant of its own, and nothing said so.** Reading the TCC database is
  gated by `kTCCServiceSystemPolicyAllFiles` (Full Disk Access) — a *different* service from the
  `SystemPolicyAppBundles` every predicate judges. The lever's verification step read as automated
  ("run it beneath the host"), but a hosted run returns `tcc_database_unavailable` exactly like a
  bare one until `DomusAgentHost.app` holds FDA (verified 2026-08-05 by running both). So the honest
  `unmeasured` verdict shipped above is currently the *only* verdict this probe can return, on this
  machine, until an operator click lands — an ungranted human atom hiding inside a step that looked
  like a command. Now homed as click 1 of 2 in `L-DOMUS-AGENT-HOST-TCC`.
- **CORRECTION — a supervising host cannot hold this identity at all, and the fix is elsewhere.**
  The third distance claimed above ("the interactive lane is not hosted") was wrong, and the way it
  was wrong is the finding. The lane *is* hosted: `claude()` in `~/.config/zsh/25-agent-runtime.zsh`
  enters `domus-agent-runtime` → `DomusAgentHost`, and PID 30699 carried `DOMUS_AGENT_HOST_ACTIVE=1`
  with a real lifetime FD and ID. Claude Code then re-execs itself with
  `process.execve(..., {macDisclaimResponsibility: true})` — `responsibility_spawnattrs_setdisclaim()`
  — which **deliberately severs inherited TCC responsibility** so a consent dialog names "Claude Code"
  rather than the terminal that launched it. That is a correct vendor design, and it means **no
  wrapper, host, or launcher can carry an identity across it**: `domus-agent-host verify-lifetime`
  exits 1 downstream, precisely as the host's own safeguard specifies. Hosting still owns the fleet
  (LaunchAgents, the ten MCP ingresses); it was never going to own the interactive prompts. The
  method error was reading a *process tree* (`PPID 1`) as evidence of an *identity* — the host tracks
  detached descendants by inherited pipe, so PPID proves nothing here, and the shipped predicate
  (`verify-lifetime`) was one command away the whole time.
- **The real mechanism is one `??`, and it fails silently.** The disclaimed identity is chosen by
  `let e = await _jb() ?? process.execPath`. `_jb()` materializes `<store>/ClaudeCode.app` —
  `CFBundleIdentifier: com.anthropic.claude-code`, a bundle whose identity survives every version —
  and hardlinks the running binary into it. It wraps `mkdir` + `writeFile` + `stat` + `unlink` +
  `link` in a **single bare `catch { return null }`**, and the fallback is `process.execPath`:
  `<store>/versions/<version>`. TCC resolves a client by the bundle enclosing the exec'd path, never
  by the bytes: the two paths are the **same inode**, but only the bundled one has an identity to
  resolve, so the other is named by its own filename. `_jb()` takes an early return when the hardlink already carries the running
  binary's inode, skipping the `unlink`/`link` pair — which concurrent session starts (bg jobs,
  spares, fleet lanes) can interleave into an `EEXIST` that silently demotes one session to a
  versioned identity. Keeping the bundle inode-correct keeps every start on that early return.
  `scripts/claude-identity-bundle.py` is the organ; sensor `0g8d` runs it every beat; contracts in
  `cli/tests/test_claude_identity_bundle.py`.
- **CORRECTION 2026-08-05 (second): the organ does not close the prompt class, and this row said it
  did.** Verified against a live process tree *while the keeper reported `at-ideal`*, with the
  dialogs still firing: `~/.local/bin/claude daemon run` (launchd-rooted) spawns its pty host **from
  the bundle**, then hands the session process its `versions/<version>` path as literal argv — and
  that session is what disclaims into its own TCC client. Four of five live processes ran from the
  versioned path; only the pty host was bundled. Independently corroborated by lever 17, which
  records real TCC rows bound to `versions/2.1.222`. The argv is composed inside the vendor binary,
  so no external change reaches it. **Method error, and it is the same one twice: a mechanism was
  named from reading vendor source and never confronted with the running system.** `ps -o args=` on
  the live tree falsified it in one command — the same shape as the `PPID`/`verify-lifetime` error
  in the bullet above. Naming a plausible mechanism is not evidence; the check was cheap both times.
- **Status:** PARTIAL, and the distance is now correctly attributed. **Closed:** the bundle keeps
  itself (organ + sensor + contracts), and both operator grants were already in place — the clicks
  this row asked for were owed to the fleet, never to this prompt class. **Open, upstream:** the
  per-version consent prompts are a vendor-side defect (disclaimed session exec'd by an unbundled
  path); disposition is a report to Anthropic, not an operator action and not a local patch.
  **Open, advisory:** two runnable versions remain in the store, whose differing inodes reopen the
  race for concurrent starts of *both* — reported by the keeper, not repaired by it, because
  deleting a vendor version is not its authority.
- **Owner:** Claude (the predicate) · the operator (the single grant).
- **Why this row exists at all.** Its status previously lived in a hand-written `discharged:` field
  in `his-hand-levers.json` carrying `"version": "2.1.222"` — a status pinned to a version, in a
  field with nothing to check it. That is precisely the shape this registry exists to abolish
  (*no row may carry a distance or a status; there is no field to lie in*). The lever now cites
  this row and the probe decides. Precedent: the same defect class as the funnel's
  `confirmed = 0`-from-an-unwired-ledger reported as a shortage — an unmeasured condition
  reported as a measured one, in both cases discovered only because the operator got angry.

### IF-GATEKEEPER-INERT — a vendor bundle is present for exec, absent from LaunchServices
- **Ideal form:** every `.app` bundle a vendor materializes around a **bare-signed** Mach-O is inert
  to Gatekeeper — present and inode-correct where the vendor expects it, and carrying **zero**
  LaunchServices registrations, so macOS is never asked to assess a bundle that provably cannot
  pass. The count is zero **across every scanned domain**, and it is *measured*: a run that could
  not ask LaunchServices reports `unknown`, never `inert`.
- **Distance:** DERIVED — `python3 scripts/check-ideal-forms.py --measure`.
- **Evidence:** the `"ClaudeCode.app is damaged and can't be opened"` dialog recurred ~10–15× over
  six weeks and **24 commits** (#1206 effector → #1219 organ family → #1242 "instant" WatchPaths
  heal → #1704 TCC audit → #1837 identity keeper) while every cure reported green. Reproduced from
  scratch 2026-08-05: the CLI is signed as a **bare Mach-O** with `Sealed Resources=none`, so the
  *same inode* passes `codesign --verify --strict` bare (exit 0) and fails it bundled (exit 1,
  `code has no resources but signature indicates they must be present`). The bundle is invalid **by
  construction**, deterministically, every time it is written.
  **Both attractors the lineage chased are unreachable.** *Absent* is undone by the live binary on
  every start (the vendor's own `_jb()`: `mkdir` + `writeFile(Info.plist)` + `link(execPath)`).
  *Valid* would require re-signing a bundle whose `Contents/MacOS/claude` is a **hardlink** to the
  running `versions/<v>`, rewriting Anthropic's Developer ID signature on the live CLI in place.
  So the cure was a duty cycle: `lsregister -dump` costs **2.85s** and the WatchPaths agent carries
  `ThrottleInterval 10`, a **≥12.85s exposure window per start** against a three-syscall write —
  #1242 named itself "instant" and could not be.
- **The window is now ~10s, and the remainder is not the effector's to close.** Re-measured
  2026-08-05: `lsregister -dump` **2.99s** against `codesign --verify --strict` on one known path at
  **0.009s** — 332×. The effector now cures `$CLAUDE_SHARE/ClaudeCode.app` *before* paying for
  enumeration (the vendor's `_jb()` targets exactly that path on every start), so time-to-unregister
  falls from ~13s to ~10s. What remains is `ThrottleInterval 10` itself, which is **deliberately not
  lowered**: each firing costs a 2.99s dump, and this host is a 16GB machine with logged jetsam
  kills. The honest statement is that the window is now dominated by a throttle chosen for host
  safety, not by the effector being slow.
  The fast path is an **optimization, never a filter** — the full enumeration still runs and stays
  authoritative, so a `~/.Trash` reseed or a second store is caught exactly as before. Narrowing the
  *scan* to the known path would repeat the mistake `condemnable()` already made once here. Its
  finding test is `lsregister -u`'s exit code (measured: **0** when it actually dropped a
  registration, **1**/`-10814` when there was none), because `condemnable()` answers *"is this
  assessable"* and the cured steady state is present-and-unassessable-and-unregistered — keying on
  it alone would have logged a phantom cure on every beat, forever.
- **Two shipped organs held contradictory invariants over one file, and nothing adjudicated.**
  `claude-identity-bundle.py` (0g8d) kept the bundle **present**; `heal-claude-lsregister.sh`
  declared the steady state **"ZERO registrations … do NOT restore the stub"** and accepted that
  removal *"drops the mic/apple-events TCC identity."* Both were honest predicates of opposite
  ideals, both green, with `LIMEN_CLAUDE_LSREGISTER_HEAL=1` armed so the beat *and* the WatchPaths
  agent deleted what the keeper had just written. The conflict dissolves once the effector
  **unregisters instead of removing**: `execve` never consults LaunchServices, only the dialog does,
  so *present* and *unregistered* are two non-overlapping predicates over one file.
- **Why this row exists at all.** The class had an effector, a sensor, a launchd agent, a lever and
  24 commits — and **no ideal form**. Nothing declared the fixed point the five cures were
  converging on, so each optimized a private invariant and none could be wrong. `dialogs-silenced.sh`
  had printed class 4b since 2026-07-09 into no owner — the same *measured but unregistered* defect
  `IF-NO-MODAL`'s own Evidence names. Its root cause was homed in `[[macos-tcc-gatekeeper-dialogs-solved]]`,
  a wikilink cited from **five** registry surfaces that **did not exist on disk**; every session
  followed it, found nothing, and re-derived the root from the effector header, which carried the
  false premise. That note now exists (`docs/architecture/macos-tcc-gatekeeper-dialogs-solved.md`).
- **CORRECTION 2026-08-05 (in-flight, before shipping): the deep-link handler is symlinked, not a
  stale hardlink.** This row initially claimed `~/Applications/Claude Code URL Handler.app` held a
  hardlink to bytes from a deleted version (inode `330121218` vs live `560887613`). False. Its
  `Contents/MacOS/claude` is a **symlink to `~/.local/bin/claude`**, so it tracks the launcher and
  never goes stale; `ls -i` reports the symlink's own inode while `stat()` follows it, and the two
  were read as one measurement. Caught only by asking the running system a second way. The finding
  it actually carries is *registration*, not freshness — it sits in `~/Applications`, a
  LaunchServices-**scanned** domain, so no unregistration holds there. Same method error this
  lineage has now made three times; the cheap check falsified it in one command, again.
- **Status:** PARTIAL — the store bundle converges (effector inverted, contract-tested 17/17, and
  the contracts fail 5× against the prior logic, so they are not vacuous). The deep-link handler is
  measured, not repaired: its only convergent cure is the vendor's own `disableDeepLinkRegistration`
  setting, which is a feature trade and therefore the operator's, homed as
  `L-CLAUDE-DEEPLINK-REGISTRATION`.
- **Owner:** Claude (the enumeration + the effector) · the operator (one vendor setting).

### IF-NOTE-HOMED — a cited note exists; the estate cites nothing into a void

- **Ideal form:** every `[[wikilink]]` in a tracked surface — effector header, sensor registry,
  lever, ledger, source comment — resolves to a file that exists **and is committed**, so a claim
  and its refutation are both retrievable by the next session instead of re-derived. What is being
  held here is not accuracy but **reachability**: a citation that resolves and one that dangles are
  byte-identical at the call site, so the only thing that can tell them apart is a predicate that
  asks the filesystem.
- **Distance:** DERIVED — `python3 scripts/check-ideal-forms.py --measure`.
- **Evidence:** this row is the generalization of [`IF-GATEKEEPER-INERT`](#if-gatekeeper-inert--a-vendor-bundle-is-present-for-exec-absent-from-launchservices)'s
  root mechanism, not a new idea. That class recurred ~10–15× over six weeks because its root cause
  was homed in `[[macos-tcc-gatekeeper-dialogs-solved]]` — cited from **five** registry surfaces and
  written **nowhere**. Every session followed the citation, found nothing, fell back to the
  effector's header comment, and inherited its false premise. **The false belief propagated because
  its refutation had no home.**
  Measured at introduction (2026-08-05, `scripts/check-note-links.py`): **49 of 50** cited note
  slugs across 3,387 tracked files resolved to nothing. The one that resolved was the note written
  to close that class. So the six-week loop was not an unlucky one-off — it was the expected
  outcome of a 98%-dangling citation estate, and nothing anywhere could have reported that, because
  nothing was measuring it.
  A citation is deliberately *not* required to be accurate — that is `IF-*`'s own job elsewhere and
  no text predicate can do it. It is required to be **followable**, which is exactly the property
  whose absence let five competent cures ship against one false premise.
- **Scope, stated rather than assumed:** single-token citations (`[[link]]`, `[[redirects]]`, and
  the `PERSON_1`/`ORG_X` redaction placeholders) are **not** gated — in this estate a note slug is
  kebab-case with ≥2 segments, and Python's `[[0], [1, 2]]` is live source in `check-danse.py`. They
  are printed as `unclassified` on every run rather than dropped, because a filter that silently
  narrows its own scope is precisely the defect `condemnable()` carried for six weeks in the class
  this row generalizes.
- **Status:** PARTIAL — the ratchet is shipped, contract-tested (18/18, against a fake repo so they
  test the gate rather than today's tree), and proven to bite end-to-end; the 49 pre-existing
  dangling slugs are recorded as a **shrink-only** work-list, not forgiven. A line leaves
  `note-link-baseline.txt` exactly one way — by writing the note it names — and a stale line fails
  the gate, so the baseline cannot quietly become permission. `at-ideal` is an empty baseline.
- **Owner:** Claude (`scripts/check-note-links.py` · `institutio/governance/note-link-baseline.txt`).

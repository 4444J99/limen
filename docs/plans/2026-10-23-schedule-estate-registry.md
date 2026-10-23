# Schedule-estate registry: every scheduler plane's allotment, jobs and utilization as declared data

Issue: #3177
PR: #3178

## The real problem

Scheduled work now runs on eight planes — GitHub Actions cron (`4444J99/ops`, limen's own workflows, `ops-witness`), the Cloudflare scheduler ops operates, the limen local heartbeat, claude.ai cloud scheduled tasks, ChatGPT scheduled tasks, Grok automations, Gemini scheduled actions, and Jules — and no surface said what each plane is **allotted**, what is **scheduled** against it, where a run's **receipt** lands, or whether the allotment was **consumed**. "Nothing left on the floor" was unmeasurable. Measured on 2026-10-23 it was also false on every plane that could be measured.

## What was found (2026-10-23, direct session + six inventory agents)

| plane | state | evidence |
|---|---|---|
| claude.ai routines (iii) | **dark** — 0 of 20 triggers enabled; 7 auto-off after `ACCESS_DENIED` from 2026-08-31..09-05, 6 bulk-disabled at 2026-10-17T00:13Z after succeeding on 10-16 | live `list_triggers` census → `docs/receipts/claude-triggers-snapshot-20261023.json`; delivery to the session-meta rolling issues stopped ~08-17 (last comments 07-20..08-17 on 6 of 8), weeks before the fire-side failures |
| GitHub cron, ops + ops-witness (i) | **dark** — every scheduled job since 10-07 refused at start: *"The job was not started because recent account payments have failed or your spending limit needs to be increased"* | check-run annotations on ops job 120447871476 and ops-witness job 120476682144; both repos private, limen (public) still runs |
| Cloudflare scheduler | **unmeasured** — its only evidence is the weekly witness, which is dead (above); last report 2026-10-04 | `ops-witness:audit/` |
| limen GitHub cron | 4 of 6 cron workflows `disabled_manually` (deploy, deploy-danse, auto-scale, conductor-report); the two active ones fire, and `cloudflare-kv-preflight` fails hourly on an open incident (ops#6) | `gh api .../actions/workflows`, `gh run list` |
| limen beat (ii) | unmeasured from the cloud container; on the host the voice stamps are the evidence. Dispatch valves off by default (`L-FLEET-DISPATCH`, governor observe) | sensors.yaml, autonomy-governor.py |
| ChatGPT scheduled tasks | 5 of 15 slots configured (limen#2680, 2026-09-20); no delivery on #2680 since 10-05 | #2680 comments |
| Grok automations | no registry row, no receipt path anywhere in the estate; `~/.grokbot` residue only | corpora.yaml, ai-vendor-spend.md |
| Gemini scheduled actions | no registry row, no receipt path; the Sept-17 window proposal is not a receipt; API key dead (`L-FLEET-CAPACITY`) | limen#2680, levers |
| Jules | 0 launches in the rolling 24h recorded by this broker; gauges exist, REST transport unarmed, native scheduled tasks are UI-only with no API, competing callers unreconciled | tasks.yaml, jules-rest-transport.md, #2680 |

Vendor limits read the same day: Claude cloud tasks min interval 1h, 100 scheduled runs/hour/account, no daily cap stated; Jules Pro 100 per rolling 24h, 15 concurrent (entitlement unverified); Gemini 10 active actions; ChatGPT Pro 15 active tasks (secondary reporting); Grok unpublished.

## Design (judged: three designs, three judges, synthesis; the limen-homed registry won two of three judges)

**Not a scheduler.** Per `ops/OPERATIONS.md`, `4444J99/ops` owns schedule/admission policy and limen owns evidence aggregation. This registry declares allotments and audits receipts; nothing that reads it can start, retry or deploy a run. Rows for planes ops operates are **projections** carrying `authority: {owner_repo, upstream_state: proposed}` and are verified against the sibling clone when one is on the host (absent ⇒ *unverifiable here, not drift*). Planes limen itself configures are **derived** from their source files (workflows, `sensors.yaml` cadences, `cloud-routines.json` + the newest trigger snapshot), never duplicated.

1. **`institutio/governance/schedules.yaml`** — one `planes` entry per plane (provider, surface, allotment {runs, window, concurrency, source, entitlement}, fill_policy/floor, jobs_source or declared rows, evidence {kind, locator}, owner, effector, `declared_off`, `authority`) and one `jobs` row per declared job (cron or list, tz, delivery, class, source_of_truth, enabled).
2. **`scripts/check-schedules.py`** (gate `check-schedules`, pr-gate) — A schema, B derivations, C claude parity (manifest ↔ snapshot by routine and cadence class), D sibling parity, E the ops stagger rule as a shrink-only ratchet (`schedule-stagger-baseline.txt`), F consumers wired. `--slot-map [--compact] --day` prints the 24h UTC map of every clock-scheduled job across all planes.
3. **`scripts/schedule-utilization.py`** (sensor `schedule-utilization`, hourly metabolize sensor pass) — per plane: allotment, declared (cron fires pro-rated to now, active jobs, or the floor), observed (per evidence kind), **allocation gap** (allotment − declared, same unit only) and **execution gap** (declared − observed), verdict ∈ full / idle-by-design / unscheduled-headroom / underfilled / dark / undeclared-off / declared-off-but-active / unmeasured. Red lines name the plane's `effector`. Exit 0 green; 1 red; **3 stale-readback** (a plane with an evidence path could not be read, or a plane with no evidence path has sat unmeasured past its readback budget — never reported as green). Headline: `measured k/n`. Receipt `logs/schedule-utilization.json` (atomic) + `.jsonl` history.
4. **`docs/receipts/claude-triggers-snapshot-<date>.json`** — the fire-side evidence for plane (iii); `list_triggers` is in-session-only, so an interactive session re-exports it (weekly, or the plane reads unmeasured).
5. **`his-hand-levers.json#L-GITHUB-ACTIONS-BILLING`** — the one atom that revives plane (i) and its witness.

## Slot map

`python3 scripts/check-schedules.py --slot-map --compact --day <YYYY-MM-DD>` is the durable form (ET-declared ChatGPT jobs shift +1h UTC on 2026-11-01; the map is computed per date). Stagger violations today, all baselined: limen `deploy` and `auto-scale` on the hour and sharing :00; `cloudflare-kv-preflight`, `conductor-report`, `deploy-danse` sharing :17; ops-witness `jules-api-witness` at :00. Moves proposed once the disabled workflows are re-enabled (separate PRs; `deploy.yml` is website-sensitive): auto-scale `11 */4`, conductor-report `36 */6`, deploy-danse `23 *`, deploy `49 *`.

## Human atoms (irreducible; filed, never nagged)

- `L-GITHUB-ACTIONS-BILLING` — GitHub Billing & plans for 4444J99: fix the payment method or raise the Actions spending limit. Revives ops, ops-witness and the Cloudflare witness in one stroke.
- claude.ai: repair the GitHub connection behind the `ACCESS_DENIED` auto-off, record why the six were bulk-disabled on 2026-10-17, then re-enable the chosen routines at claude.ai/code/routines (spends subscription usage).
- ChatGPT / Grok / Gemini / Jules native: UI-only schedulers — post one readback each (active tasks, cadence, destination) so the registry rows and a delivery locator can be declared; until then those planes are `unmeasured` by construction.
- `L-FLEET-DISPATCH`, `L-FLYWHEEL-VALVE-ARM`, `L-FLEET-CAPACITY` (Gemini key) — unchanged, already filed.

## Follow-ups (filed here, not widened into this PR)

- routine-freshness organ: any comment counts as delivery (a stray 2026-10-19 comment on session-meta#34 reads a ~69-day-dead routine green); require a delivery marker; read the trigger snapshot for live-enabled state (limen#894).
- jules-quota / jules-flywheel: rolling-24h window instead of UTC-day; external callers (ChatGPT steward, native tasks) are invisible to the broker count (#2680).
- ops: adopt `schedules.yaml`'s projected rows (or publish its own) and flip `upstream_state` to `synced`; extend the weekly witness to read the registry (ops-witness).
- `cloud-routines.json`: `generated_at` is 2026-07-08; the contract should carry the trigger id and cron per routine.

## Adversarial review residuals (four refuters over the synthesized design, 2026-10-23)

What shipped already answers the two blockers, and the rest are recorded here as the owners' follow-ups rather than widened into the PR:

- **"ops may host a new `schedules/registry.yaml`" — refuted** (`ops/AGENTS.md:37`, `OPERATIONS.md:53-62`: extend `manifest.ts`, no parallel registry). Shipped shape: no ops-side file; the Cloudflare and ops rows in limen are a *projection* (`authority.upstream_state: proposed`) held to the owner's source by check D whenever a sibling clone is on the host. Residual: the crons of projected rows are restated (so CI can build the slot map without a clone); the ratification path is either an ops carve-out for a cross-plane index or generating those rows from `manifest.ts`/the ops workflows, at which point `upstream_state` flips to `synced`.
- **"claude fire-side evidence has no producer" — refuted** for the design's census marker. Shipped shape: the dated snapshot receipt is the producer, exported from an interactive session (the only surface that can call `list_triggers`), aged out after `LIMEN_SCHEDULE_SNAPSHOT_MAX_AGE_DAYS`. Residual: the producer is manual; a routine that exports the snapshot would make it unattended (it must run with routine access, so it is a human-created routine).
- Measurability: planes a runner cannot read must say *why*. Shipped: every unmeasured row carries its reason in `detail`; `measured k/n` counts machine evidence only; a plane with no evidence path trips exit 3 after its readback budget.
- Minimality cautions for later PRs: no new in-process sender for bookend markers (post via the Bash rail or a sanctioned publisher); do not suppress Jules supply minting while the vendor count is unmeasured; cross-plane same-minute sharing is informational, the per-repo rule is the one GitHub's congestion actually punishes.
- Slot map: conversions and coverage held under both EDT and EST; the Cloudflare 12:00 tick has 5 targets due against 4 per tick (an ops#6 note, not a limen change).

## Review round 1 (PR #3178 head `2ba8109`, Codex, 2026-10-23) — three claims verified, all three real, fixed

- **Jules read 0 → `dark` from the public projection.** `tasks.yaml` in the checkout is `limen.public_board_projection.v1` (`tasks: []`, no `dispatch_log`), so it proves nothing about launches. Fixed: the board reader resolves `LIMEN_TASKS`, then `$LIMEN_ROOT/tasks.yaml`, then the checkout, and a public projection is **unmeasured** with the reason in `detail`; a real but empty board is still 0.
- **Sensor `cadence` is beats, not hours.** `beat-sensors.py::_due` fires on `beat % cadence == 0` or stamp age ≥ cadence × loop_max, so the only wall-clock bound is the worst case, cadence × `LIMEN_LOOP_MAX` (1,800s default). Fixed: `Job.cadence_hours` is now that worst-case bound (`cadence_beats` keeps the declared value); `cadence: 48` is daily and `daily-execution`, `conversion-funnel`, `collaboration-hub-sync` are back in the daily set (57 declared, was 54).
- **A failed sibling read scored as an observed 0.** Fixed: the sibling read is tri-state (present / absent / unreadable); absence is confirmed only by a parent-folder listing that lacks the file, because an unauthenticated read of a private repository is also a 404. Unreadable is unmeasured, never zero.
- Found while verifying: a `logs/.voice` directory that exists but was never stamped (a worktree, CI) read as a dark heartbeat; it is now unmeasured.

## Review round 2 (PR #3178 head `f1dda55`, Codex, 2026-10-23) — three claims verified, all three real, fixed; the two-round bound is now spent

- **A `dispatched` row is a claim, not a launch.** The serial dispatcher writes a reservation row before the provider runs and `_apply_result` writes the confirmed submission, so every launch was counted twice and a reservation whose launch never started counted once. Fixed: only confirmed submissions count (reservation/guard rows are recognised by their output prefix and guard session ids), deduplicated per task and provider session; the detail names the claim rows it skipped.
- **Voice stamps were scored against UTC midnight.** A cadence-48 sensor stamped at 23:59 read as missing at 00:01. Fixed: a stamp is current while younger than 2 × its worst-case cadence window, the same bound `beat-sensors.py --canary` uses for STALE, so the two can never disagree.
- **The readbacks lever discharged on three of its four planes.** Jules native scheduled tasks had no plane row, and the broker's launch count says nothing about which native tasks exist. Fixed: `jules-native-scheduled-tasks` is a plane of its own (evidence `none`, unmeasured by construction, under the same readback budget as Grok and Gemini) and the predicate requires all four present and measured.
- Any further automated-review round is a generator, not a gate (`PREC-2026-08-12-advisory-review-loop-has-no-fixed-point`): residual findings become follow-up issues; `scripts/merge-policy.sh` alone decides the merge.

## Done predicate

`scripts/check-schedules.py` exit 0 and `bash scripts/run-pytest-hermetic.sh cli/tests/test_schedules_registry.py -q` green on the merged tree; on the host, `python3 scripts/schedule-utilization.py --receipt logs/schedule-utilization.json` writes a receipt whose `measured` numerator rises as the atoms above are pulled.

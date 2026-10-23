# Schedule-estate registry: every scheduler plane's allotment, jobs and utilization as declared data

Issue: #3177
PR: (pending)

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

## Done predicate

`scripts/check-schedules.py` exit 0 and `bash scripts/run-pytest-hermetic.sh cli/tests/test_schedules_registry.py -q` green on the merged tree; on the host, `python3 scripts/schedule-utilization.py --receipt logs/schedule-utilization.json` writes a receipt whose `measured` numerator rises as the atoms above are pulled.

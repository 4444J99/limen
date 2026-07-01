# Carrier-Wave Media organ — NEXT (residual work)

Durable record of what remains, so nothing hangs in a session or a chat. Two federated
spines (see KERNEL.md): **A = media-ark** (archive product, standalone repo) and
**B = this organ** (outbound distribution). Established / landed 2026-07-01.

## Landed (this convergence)
- Organ body (`CHARTER/KERNEL/PIPELINE-FIRE-001`) + `photos-duplicate-proof.py` + receipts → main (#504).
- `media-atomize.py` fork resolved: read-only Photos.app `--photos-metadata` slice → main (#505).
- Capture front-ends → main (#506): native **SCK recorder** (`tools/recorder`, builds; system audio w/o BlackHole) + rescued **screen-capture importer** (`tools/screen-capture-importer`, provenance fixed).
- Outbound **scheduler** (`scheduler/social_scheduler.py`, drafts-only) + 5 levers (#508).
- Stale draft PR #497 closed; 7 empty dud branches pruned.
- **media-ark CI turned GREEN** (`organvm/media-ark` PR **#51**, merged `c28bf83`, 2026-07-01) — first ever. Corrected issue #5's stale "runner-pickup" theory: the hosted runner picks up fine; the red was a **half-landed #43 auth refactor**. Fixes: readiness probes → public `/`; wired the `GET /api/export/{fmt}` route (export.py existed, unwired); added the `SyncConfig`/`load_sync_config`/`pro_enabled` config layer (sync.py imported symbols that existed nowhere); migrated `verify_release.py` to the authed/sandboxed model; guarded `src/platform/__init__.py` against shadowing the stdlib `platform` module (py3.11 `uuid` collision); fixed the tox invocation (`-e` not `-m`). Full suite 94 passed; CLI smoke + tox(py311,py314) + actionlint green.

## Spine A — media-ark (repo `organvm/media-ark`) — separate, larger effort
- ~~CI is RED~~ **DONE** — CI green on main (PR #51). See "Landed" above.
- **Close 5 superseded dud PRs** #44/#45/#46/#48/#49 (the old "Make CI green" attempts; #51 supersedes them). **Human atom** — closing PRs the session didn't open is classifier-gated (External System Writes). One-liner: `for p in 44 45 46 48 49; do gh pr close $p -R organvm/media-ark --comment "Superseded by #51 (CI now green)."; done`.
- **Update + close issue #5** with the accurate root-cause (half-landed #43 auth refactor, fixed by #51 — not the runner-pickup theory). **Human atom** — issue comment/close is classifier-gated. One-liner: `gh issue close 5 -R organvm/media-ark --comment "Resolved by #51 — root cause was the #43 auth refactor, not runner pickup. CLI smoke + tox(py311,py314) + actionlint green on main."`.
- **Rebase the 3 substantive PRs** onto current main — all now **CONFLICTING/DIRTY** and each likely carries its own #43-style wiring gaps (separate per-PR effort): **#29** (quota/paywall, +778 — the missing revenue primitive), **#34** (dashboard-pro, +535), **#42** (api-docs, +651).
- **Rename the `src/platform` package** — the permanent fix for the stdlib-`platform` shadow (currently guarded in `__init__.py`). Touches all `from src.platform…` sites + `python -m src.platform.*` invocations + tests.
- **Undeployed + $0**: `media-ark.org` CNAME set but nothing served; Stripe not connected; `sync.py` crypto is a placeholder XOR (not real AEAD) — wire before any Pro launch.
- **Reconcile local checkout** `~/Workspace/4444J99/media-ark` (24 behind origin, dirty, ~35 stale fleet branches).
- **Free-tier quota mismatch**: docs say 5GB, `billing.py` says 1000 items — pick one before launch.

## Spine B — this organ — next slices
- **Scheduler `send`**: implement real per-platform API calls (currently refuses). Gated on lever `L-SOCIAL-OAUTH` (vendor apps + tokens → creds-hydrate, never chat) then `L-SOCIAL-SEND` per publish.
- **Scheduler select**: read the media-ark `index.jsonl` / `out/` tree directly (currently a source dir).
- **Caption enrichment**: optional keyless `claude -p` captions from OCR/sidecar text.
- **Beat wiring**: heartbeat runs `media-atomize.py --apply` (docs only) — add `--photos-metadata` to run photo atomization autonomically.

## Aspirational (original vision doc, still unbuilt)
- Vision captions slice (keyless `claude -p` on images) and cross-modal "distill my year" convergence over photos + docs + words.

## Human atoms (in `his-hand-levers.json`)
`L-TCC-RECORDER` · `L-AUDIO-BLACKHOLE` · `L-TCC-PHOTOS-AUTOMATION` · `L-SOCIAL-OAUTH` · `L-SOCIAL-SEND`.

## Housekeeping
- Remote branch `origin/feature/ORG-media-organ-deepen-0630` left in place (content on main; remote-delete is human-gated). Prune when convenient.
- Consider migrating capture front-ends (`tools/recorder`, `tools/screen-capture-importer`) into the media-ark repo once its CI is green (cleaner Spine-A ownership).

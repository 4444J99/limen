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

## Spine A — media-ark (repo `organvm/media-ark`) — separate, larger effort
- **CI is RED** (issue #5, hosted-runner-pickup heartbeat). Root-cause once, then **close the 5 duplicate "CI-green" PRs** (#44/#45/#46/#48/#49, keep one).
- **Rebase the 3 conflicting substantive PRs** onto current main: **#29** (quota/paywall — the missing revenue primitive), **#34** (dashboard-pro), **#42** (api-docs).
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

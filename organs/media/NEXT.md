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
- **media-ark paywall landed** (`organvm/media-ark` PR **#52**, merged `9371420`, 2026-07-01) — first substantive feature since the CI resurrection. Rebased+completed #29's per-user quota (`quota.py`, free/pro tiers, `429` on exhaust, free `GET /api/quota`) and reconciled its identity model onto the AuthStore bearer gate. Tier is ledger-owned, leaving the MONETA licence seam. See Spine A → Phase 2.
- **media-ark ↔ MONETA licence wiring landed** (`organvm/media-ark` PR **#53**, merged `67a67bf`, 2026-07-01) — pure-stdlib ECDSA-P256 verifier (`src/platform/license.py`) + `POST /api/license`. A MONETA-signed Pro licence now upgrades a user's tier offline (no processor). The BTC→MONETA→licence→verify→pro→quota chain is **code-complete**; only deploy remains. See Spine A → Phase 3.

## Spine A — media-ark (repo `organvm/media-ark`) — separate, larger effort
- ~~CI is RED~~ **DONE** — CI green on main (PR #51, `c28bf83`). See "Landed" above.
- ~~**#29 quota/paywall**~~ **DONE** — rebased onto green main + landed as **PR #52** (`9371420`, 2026-07-01). Reconciled #29's spoofable `X-User-Tier` header model onto #51's AuthStore bearer identity: the quota subject is now `str(auth_user.id)` and **tier lives in the ledger, never a client header** (a `X-User-Tier: pro` header would have handed anyone the pro budget). Folded quota-DB isolation back into the API test env. **110 tests green on py3.11 AND py3.14; `release:verify` exit 0** (both CI jobs reproduced locally via `uv --python 3.11`).
- **Close superseded PRs** #44/#45/#46/#48/#49 (old "Make CI green" duds) **and #29** (rebased+superseded by #52). **Human atom** — closing PRs the session didn't open is classifier-gated (External System Writes). One-liner: `for p in 44 45 46 48 49 29; do gh pr close $p -R organvm/media-ark --comment "Superseded (CI green; #29 rebased into #52)."; done`.
- **Update + close issue #5** with the accurate root-cause (half-landed #43 auth refactor, fixed by #51 — not the runner-pickup theory). **Human atom** — issue comment/close is classifier-gated. One-liner: `gh issue close 5 -R organvm/media-ark --comment "Resolved by #51 — root cause was the #43 auth refactor, not runner pickup. CLI smoke + tox(py311,py314) + actionlint green on main."`.
- ~~**Phase 2 — wire the paywall to MONETA**~~ **DONE** — landed as **PR #53** (`67a67bf`, 2026-07-01). `src/platform/license.py` verifies MONETA's offline **ECDSA P-256 / SHA-256** Pro licences with a **pure-stdlib** P-256 implementation (zero third-party deps — `hashlib` + integer point math). `POST /api/license` (behind the AuthStore bearer gate) verifies the licence against the embedded MONETA pubkey (`MEDIA_ARK_LICENSE_PUBKEY`) and sets the caller's ledger tier to `pro` on valid+unexpired+pro — the **only** path to pro (tier is never a client header). 22 license tests over vectors minted by MONETA-format Node WebCrypto (cross-impl interop proof, incl. forged-payload + wrong-key rejection); **132 tests green py3.11+py3.14; release:verify exit 0**. The revenue mechanism (BTC→MONETA→signed licence→verify→pro→quota) is now complete **in code**.
- **Phase 3 — deploy (needs a hosting decision). THE remaining major lever.** Nothing is served yet, so despite the mechanism being code-complete, revenue is still $0 until it's live. The stdlib-http **media-ark API needs a real host** (Cloud Run / Fly / VPS); the static dashboard → Pages (CNAME `media-ark.org` already set). **MONETA also needs a host** for the BTC→licence flow; media-ark's deployed build then sets `MEDIA_ARK_LICENSE_PUBKEY` to MONETA's public key. **Decision pending (owner): where to host** (self-sovereignty/cost trade-off, per [[sovereign-cash-intake]]).
- **Rebase the 2 remaining substantive PRs** onto current main — both **CONFLICTING/DIRTY**, each likely with its own #43-style wiring gaps (separate per-PR effort): **#34** (dashboard-pro, +535), **#42** (api-docs, +651).
- **Rename the `src/platform` package** — the permanent fix for the stdlib-`platform` shadow (currently guarded in `__init__.py`). Touches all `from src.platform…` sites + `python -m src.platform.*` invocations + tests.
- **Undeployed + $0**: `sync.py` crypto is a placeholder XOR (not real AEAD) — wire before any Pro launch. (Stripe is **not** the path — MONETA is; see Phase 2.)
- **Reconcile local checkout** `~/Workspace/4444J99/media-ark` (24 behind origin, dirty, ~35 stale fleet branches).
- **Reconcile free-tier numbers against `quota.py`.** #29's `quota.py` `TIERS` now encodes free = 5 GB storage + 1,000 monthly calls (separate resources). Align `billing.py` / docs to that as the source of truth (the old "5GB vs 1000 items" note was comparing storage to calls).

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

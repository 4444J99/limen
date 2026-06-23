# Reclassify needs_human — 2026-06-23

`needs_human` holds **37** tasks. By signal (not by hand-picked id) they split into:

- **KEEP — 22** genuinely need your hand (secret / account / admin / merge gate / irreversible cutover / Cloudflare-credential-gated deploy).
- **FLIP — 10** are fleet-buildable code/docs parked behind a false gate. `--apply` flips these to `open` so the fleet does them. Reversible.
- **STALE — 1** precondition already met — recommend close, don't re-queue.
- **REVIEW — 4** one quick triage call (skip vs *kill* — kill is irreversible, never auto-flipped).

> `--apply` changes ONLY the FLIP bucket; KEEP / STALE / REVIEW are never auto-touched. Flipping `needs_human -> open` only lets the fleet *attempt* the work — fully reversible.

## FLIP — fleet-buildable code/docs — no human-only signal

| id | type | repo | title |
|---|---|---|---|
| `GH-meta-organvm-meta-organvm-superproject-6` | code | organvm/meta-organvm--superproject | Omega #15: Flip — portfolio validation page is LIVE |
| `GH-organvm-ii-poiesis-organvm-ii-poiesis-superproject-2` | code | organvm/organvm-ii-poiesis--superproject | Add README for performance-sdk |
| `GH-organvm-iii-ergon-sign-signal-voice-synth-3` | code | organvm/sign-signal--voice-synth | Implement Layer 1: Dialogue Looping Tracker (60 tasks) |
| `GH-organvm-iv-taxis-organvm-iv-taxis-github-io-1` | code | organvm/organvm-iv-taxis.github.io | EV Activation Audit: ship-now — ORGAN-IV landing page live (HTTP 200) |
| `GH-organvm-v-logos-organvm-v-logos-github-io-1` | code | organvm/organvm-v-logos.github.io | EV Activation Audit: ship-now — org landing page live (HTTP 200) |
| `GH-organvm-vi-koinonia-organvm-vi-koinonia-github-io-1` | code | organvm/organvm-vi-koinonia.github.io | EV Activation Audit: ship-now — org landing page live (HTTP 200) |
| `GH-organvm-vii-kerygma-organvm-vii-kerygma-github-io-1` | code | organvm/organvm-vii-kerygma.github.io | EV Activation Audit: ship-now — org landing page live (HTTP 200) |
| `GH-organvm-vii-kerygma-organvm-vii-kerygma-superproject-5` | code | organvm/organvm-vii-kerygma--superproject | Epic: Kerygma Pipeline Activation (POSSE Distribution) |
| `GH-organvm-vii-kerygma-organvm-vii-kerygma-superproject-2` | code | organvm/organvm-vii-kerygma--superproject | Add missing READMEs for kerygma-pipeline and kerygma-profiles |
| `GH-organvm-i-theoria-atomic-substrata-1` | code | organvm/atomic-substrata | EV Activation Audit: ship-soon — UAKS pipeline operational but unrelea |

## STALE — precondition already satisfied (daemon already dispatching) — recommend close

| id | type | repo | title |
|---|---|---|---|
| `ASK-7-dispatch-drain-open` | code | — | Live-dispatch across all 6 vendors to clear the 255 open tasks; keep o |

## REVIEW — irreversible/ambiguous (skip-vs-kill) — one human triage pass

| id | type | repo | title |
|---|---|---|---|
| `GH-organvm-iv-taxis-organvm-iv-taxis-superproject-6` | code | organvm/organvm-iv-taxis--superproject | ACTIVATION AUDIT: skip |
| `GH-organvm-iv-taxis-organvm-iv-taxis-superproject-5` | code | organvm/organvm-iv-taxis--superproject | ACTIVATION AUDIT: kill |
| `GH-organvm-v-logos-organvm-v-logos-superproject-6` | code | organvm/organvm-v-logos--superproject | ACTIVATION AUDIT: kill |
| `GH-organvm-vi-koinonia-organvm-vi-koinonia-superproject-3` | code | organvm/organvm-vi-koinonia--superproject | ACTIVATION AUDIT: kill |

## KEEP — real human atom (secret/account/admin/merge-gate/cutover/credential-gated deploy)

| id | type | repo | title |
|---|---|---|---|
| `LIMEN-072` | docs | organvm/organvm-engine | descent: expand branch protection to all organs |
| `LIMEN-077` | docs | organvm/organvm-engine | Fix soak-test LaunchAgent — gh CLI auth fails under launchd |
| `LIMEN-091` | docs | organvm/public-record-data-scrapper | PR #234 security gate prerequisites (JWT_SECRET, org_id) |
| `BLD2-a-i-chat--exporter-deploy` | code | organvm/a-i-chat--exporter | a-i-chat--exporter: deploy |
| `BLD2-public-record-data-scrapper-deploy` | code | organvm/public-record-data-scrapper | public-record-data-scrapper: deploy |
| `BLD2-mirror-mirror-deploy` | code | organvm/mirror-mirror | mirror-mirror: deploy |
| `BLD2-universal-mail--automation-deploy` | code | organvm/universal-mail--automation | universal-mail--automation: deploy |
| `BLD2-peer-audited--behavioral-blockchain-deploy` | code | organvm/peer-audited--behavioral-blockchain | peer-audited--behavioral-blockchain: deploy |
| `BLD2-the-invisible-ledger-deploy` | code | organvm/the-invisible-ledger | the-invisible-ledger: deploy |
| `BLD2-promptscope-deploy` | code | organvm/promptscope | promptscope: deploy |
| `BLD2-writelens-deploy` | code | organvm/writelens | writelens: deploy |
| `BLD2-edgarflash-deploy` | code | organvm/edgarflash | edgarflash: deploy |
| `BLD2-trendpulse-deploy` | code | organvm/trendpulse | trendpulse: deploy |
| `BLD2-essay-pipeline-deploy` | code | organvm/essay-pipeline | essay-pipeline: deploy |
| `BLD2-tab-bookmark-manager-deploy` | code | organvm/tab-bookmark-manager | tab-bookmark-manager: deploy |
| `BLD2-narratological-algorithmic-lenses-deploy` | code | organvm/narratological-algorithmic-lenses | narratological-algorithmic-lenses: deploy |
| `BLD2-card-trade-social-deploy` | code | organvm/card-trade-social | card-trade-social: deploy |
| `BLD2-bountyscope-deploy` | code | organvm/bountyscope | bountyscope: deploy |
| `BLD2-vulnpulse-deploy` | code | organvm/vulnpulse | vulnpulse: deploy |
| `ASK-2-one-container-cutover` | code | — | Run the gated one-container cutover (container/migrate.sh S4-S13) unde |
| `ASK-5-open-merge-gate` | code | — | Open the merge gate: parallel merge pass on the ~111 merge-ready PRs,  |
| `ASK-20-container-relocate-state` | code | — | Extend container/manifest.tsv to relocate bulky agent state dirs (~/.c |

---
*Generated by `scripts/reclassify-needs-human.py`. Re-run `--apply` to flip the FLIP bucket, or say the word and I will.*

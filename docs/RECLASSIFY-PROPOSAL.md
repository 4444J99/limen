# Reclassify needs_human — 2026-07-15

`needs_human` holds **100** tasks. By signal (not by hand-picked id) they split into:

- **KEEP — 85** genuinely need your hand (secret / account / admin / merge gate / irreversible cutover / Cloudflare-credential-gated deploy).
- **CHRONIC — 0** churned ≥3 reopens with zero PRs and carry no human atom — fleet debt. `--apply` parks these `failed_blocked` (honest terminal state; flipping them to `open` is the ping-pong that refills this queue). Reversible.
- **FLIP — 0** are fleet-buildable code/docs parked behind a false gate. `--apply` flips these to `open` so the fleet does them. Reversible.
- **STALE — 1** precondition already met — recommend close, don't re-queue.
- **REVIEW — 14** one quick triage call (skip vs *kill* — kill is irreversible, never auto-flipped).

> `--apply` changes ONLY the FLIP and CHRONIC buckets; KEEP / STALE / REVIEW are never auto-touched. Both flips are status-only + a provenance label — fully reversible.

## FLIP — fleet-buildable code/docs — no human-only signal

| id | type | repo | title |
|---|---|---|---|

## CHRONIC — reopened ≥3× with zero PRs, no human atom — fleet debt, park failed_blocked

| id | type | repo | title |
|---|---|---|---|

## STALE — precondition already satisfied (daemon already dispatching) — recommend close

| id | type | repo | title |
|---|---|---|---|
| `ASK-7-dispatch-drain-open` | code | — | Live-dispatch across all 6 vendors to clear the 255 open tasks; keep o |

## REVIEW — irreversible/ambiguous (skip-vs-kill) — one human triage pass

| id | type | repo | title |
|---|---|---|---|
| `ASK-quicken-d2l` | ops | — | the D2L go-live click + cadence confirm (your login + judgment) |
| `ASK-quicken-delete` | ops | — | approve the irreversible delete/clear (archived reversibly; purge is y |
| `ORG-financial-organ-deepen-0703` | content | organvm/limen | Deepen the financial organ toward a usable institution |
| `ASK-quicken-send` | ops | — | send the drafted message (never auto-send) |
| `ASK-quicken-escalate-4a4c2aa8` | ops | — | finish stalled session 'Build alchemical synthesizer for audio sampl'  |
| `ASK-quicken-escalate-e0f151ab` | ops | — | finish stalled session 'bash permission config investigation' (breathe |
| `ASK-lane-starved-agy` | ops | — | Lane 'agy' starved: silent >42.5h with open queue + ok budget |
| `ASK-lane-starved-gemini` | ops | — | Lane 'gemini' starved: silent >47.8h with open queue + ok budget |
| `ASK-lane-starved-opencode` | ops | — | Lane 'opencode' starved: silent >42.4h with open queue + ok budget |
| `ASK-quicken-escalate-6a48ce1d` | ops | — | finish stalled session 'Design movement ontology and workout composi'  |
| `ASK-quicken-escalate-0bd3a5ed` | ops | — | finish stalled session 'Design movement ontology and workout composi'  |
| `SOVEREIGN-0708-GPG-UID` | ops | organvm/limen | Add the later recourse.email UID to the current GPG identity |
| `ASK-quicken-escalate-9feaa902` | ops | organvm/limen | finish stalled session 'Complete chat tasks with appropriate model a'  |
| `ASK-quicken-escalate-9c934372` | ops | organvm/limen | finish stalled session 'Complete chat tasks with appropriate model a'  |

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
| `REV-organvm-styx-revenue-ship-0623` | code | organvm/styx | Drive Styx to deploy-ready |
| `REV-organvm-styx-revenue-readiness-0623` | code | organvm/styx | First-paying-customer readiness pass on Styx |
| `ASK-quicken-login` | ops | — | one login/identity step (your hand: browser/OAuth/portal) |
| `REVENUE-exporter-first-dollar` | ops | — | Drive live ChatGPT Exporter to first-$ rail (Sponsors + Pro tier) |
| `GH-organvm-limen-265` | code | organvm/limen | needs-human (L-FLEET-CAPACITY): Re-mint the 3 fleet credentials — they |
| `GH-organvm-limen-264` | code | organvm/limen | needs-human (L-MODEL-TIER): Stop the interactive Claude burn at the so |
| `GH-organvm-limen-263` | code | organvm/limen | needs-human (L-IANVA-CLOUD): Stop the claude.ai connector 'needs authe |
| `GH-organvm-limen-262` | code | organvm/limen | needs-human (L-IANVA-LOCAL): Kill the per-agent MCP re-auth for every  |
| `GH-organvm-limen-260` | code | organvm/limen | needs-human (L-EDU-PERTERM): The per-term recapitulation ritual is aut |
| `GH-organvm-limen-259` | code | organvm/limen | needs-human (L-ENC1102-GRADEBOOK): Resolve the ENC1102 D2L gradebook w |
| `GH-organvm-limen-258` | code | organvm/limen | needs-human (L-ENC1101-GOLIVE): Take ENC1101 Summer 2026 (771624) live |
| `GH-organvm-limen-257` | code | organvm/limen | needs-human (L-BRANCH-PROTECT-072): Branch-protection across the organ |
| `GH-organvm-limen-255` | code | organvm/limen | needs-human (L-CONTAINER-CUTOVER): One-container cutover |
| `GH-organvm-limen-254` | code | organvm/limen | needs-human (L-CLOUDFLARE-DEPLOY): Cloudflare deploy auth |
| `GH-organvm-limen-253` | code | organvm/limen | needs-human (L-REVENUE-ACCT): Revenue first-dollar accounts |
| `ASK-quicken-credential` | ops | — | land the credential/secret (your account/identity) |
| `REV-organvm-public-record-data-scrapper-revenue-ship-0628` | code | organvm/public-record-data-scrapper | Drive Public Record Data Scraper to deploy-ready |
| `REV-organvm-universal-mail--automation-revenue-readiness-0628` | code | organvm/universal-mail--automation | First-paying-customer readiness pass on Universal Mail Automation |
| `REV-organvm-the-invisible-ledger-revenue-readiness-0628` | code | organvm/the-invisible-ledger | First-paying-customer readiness pass on The Invisible Ledger |
| `REV-organvm-public-record-data-scrapper-revenue-readiness-0629` | code | organvm/public-record-data-scrapper | First-paying-customer readiness pass on Public Record Data Scraper |
| `REV-organvm-universal-mail--automation-revenue-ship-0630` | code | organvm/universal-mail--automation | Drive Universal Mail Automation to deploy-ready |
| `REV-organvm-the-invisible-ledger-revenue-ship-0630` | code | organvm/the-invisible-ledger | Drive The Invisible Ledger to deploy-ready |
| `REV-organvm-mirror-mirror-revenue-readiness-0630` | code | organvm/mirror-mirror | First-paying-customer readiness pass on Mirror Mirror |
| `GH-organvm-limen-535` | code | organvm/limen | needs-human (L-GCP-DEPLOY-SA): media-ark hosted go-live — a HUMAN HOST |
| `GH-organvm-limen-534` | code | organvm/limen | needs-human (L-PII-SWEEP-CONTAIN): Contain the org-wide personal-data  |
| `GH-organvm-limen-533` | code | organvm/limen | needs-human (L-SOCIAL-SEND): Pull the actual PUBLISH |
| `GH-organvm-limen-532` | code | organvm/limen | needs-human (L-SOCIAL-OAUTH): Create the developer apps + mint first a |
| `GH-organvm-limen-531` | code | organvm/limen | needs-human (L-TCC-PHOTOS-AUTOMATION): Grant Automation permission to  |
| `GH-organvm-limen-530` | code | organvm/limen | needs-human (L-AUDIO-BLACKHOLE): FALLBACK ONLY |
| `GH-organvm-limen-529` | code | organvm/limen | needs-human (L-TCC-RECORDER): Grant Screen Recording + Microphone perm |
| `GH-organvm-limen-538` | code | organvm/limen | needs-human (L-STUDIO-GOLIVE): Take Object Lessons Studio public — the |
| `GH-organvm-limen-563` | code | organvm/limen | needs-human (L-CARTRIDGE-REPOINT): Re-plug the chezmoi cartridge into  |
| `ORG-governance-organ-deepen-0703` | content | organvm/limen | Deepen the governance organ toward a usable institution |
| `ORG-governance-organ-selffeed-0703` | content | organvm/limen | Wire the governance organ to advance autonomously |
| `REVIEW-peer-audited-726-thread-remediation-0707` | code | organvm/peer-audited--behavioral-blockchain | Address live review blockers on peer-audited#726 before merge |
| `GH-organvm-limen-651` | code | organvm/limen | needs-human (L-FLEET-DISPATCH): The whole board is partitioned + route |
| `GH-organvm-limen-657` | code | organvm/limen | needs-human (L-LAVREA-LAUNCH): Post the LAVREA launch kit under your o |
| `REV-organvm-mirror-mirror-revenue-ship-0707` | code | organvm/mirror-mirror | Drive Mirror Mirror to deploy-ready |
| `GH-organvm-limen-686` | code | organvm/limen | Add historical token tombstone audit to the credential wall |
| `RETRO-0708-CODEX-BUDGET-RESET` | code | organvm/limen | Codex per-task budget reset + pre-dispatch uncached-token cap |
| `GH-organvm-limen-719` | code | organvm/limen | L-ARCA-KEY-ESCROW: escrow the ARCA vault key off-machine (his-hand) |
| `ASK-quicken-escalate-0305e50a` | ops | — | finish stalled session 'Audit Codex handoff and validate token-accou'  |
| `GH-organvm-limen-791` | code | organvm/limen | needs-human (L-DAILY-ENGINE-PHONE-SETUP): Daily-engine phone setup |
| `GH-organvm-limen-790` | code | organvm/limen | needs-human (L-ESTATE-MOUNT-4444J99): MOUNT the 4444J99 SSD to recover |
| `GH-organvm-limen-789` | code | organvm/limen | needs-human (L-MONETA-LAUNCH): Post the MONETA Mint-as-a-Service launc |
| `GH-organvm-limen-827` | code | organvm/limen | [his-hand] Arm the Fable interactive-guard settings snippet |
| `REV-organvm-mirror-mirror-revenue-ship-0709` | code | organvm/mirror-mirror | Drive Mirror Mirror to deploy-ready |
| `GH-organvm-limen-961` | code | organvm/limen | needs-human (L-OBSERVATORY-ACTIVATE): Activate OBSERVATORY (the legibi |
| `GH-organvm-limen-960` | code | organvm/limen | needs-human (L-MAIL-AUTOMATION-GRANT): Grant macOS Automation permissi |
| `GH-organvm-limen-934` | code | organvm/limen | needs-human (L-INTEGRATION-RENOVATE): install Renovate on organvm + tr |
| `GH-organvm-limen-933` | code | organvm/limen | needs-human (L-INTEGRATION-CODERABBIT): install CodeRabbit on organvm  |
| `GH-organvm-limen-928` | code | organvm/limen | needs-human (L-OPENCODE-AUTH): optionally authorize OpenCode catalog a |
| `GH-organvm-limen-927` | code | organvm/limen | needs-human (L-IDENTITY-POPULATE): Populate the core personal-fact ato |
| `GH-organvm-limen-926` | code | organvm/limen | needs-human (L-FABLE-GUARD-ARM): Arm the Fable interactive-guard setti |
| `GH-organvm-limen-912` | code | organvm/limen | needs-human (L-STORAGE-DRAIN-PUSHED): Flip LIMEN_RECLAIM_PUSHED_OK=1 i |
| `GH-organvm-limen-910` | code | organvm/limen | needs-human (L-LIMENBOT-INSTALL): Create + install the limen[bot] GitH |
| `SOVEREIGN-0708-GPG-ESCROW` | ops | organvm/limen | Escrow the current GPG private material off-machine |
| `SOVEREIGN-0708-GPG-DISCOVERABILITY` | ops | organvm/limen | Publish the current GPG public key to a discoverable surface |
| `GH-organvm-limen-1057` | code | organvm/limen | needs-human (L-DAILY-ENGINE-PHONE-LEAVES): Install the two daily-engin |
| `GH-organvm-limen-1053` | code | organvm/limen | needs-human (L-REMOTE-REAP-APPLY): Arm the remote-branch reaper's seco |
| `GH-organvm-limen-1046` | code | organvm/limen | needs-human (L-LAUNCHAGENT-HEAL): Arm the launch-agent self-heal effec |
| `GH-organvm-limen-1090` | code | organvm/limen | needs-human (L-REVENUE-ACCT): Create Ko-fi account + Lemon Squeezy sto |
| `GH-organvm-limen-1087` | code | organvm/limen | needs-human (L-BACKBLAZE-EXCLUDE): Backblaze exclusions — one Settings |

---
*Generated by `scripts/reclassify-needs-human.py`. Re-run `--apply` to flip the FLIP bucket and park the CHRONIC bucket, or say the word and I will.*

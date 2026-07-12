# needs_human digest — 2026-06-20

23 tasks are blocked on a human. They collapse to **4 distinct actions**.
Doing #1 alone unblocks **16** of them.

## 1. Cloudflare deploy auth — unblocks 16 BLD2 deploys
**Action:** `wrangler login` (or export `CLOUDFLARE_API_TOKEN` into the lane env), then re-dispatch.
**Why:** every `BLD2-*-deploy` fails because wrangler is not authenticated, so `wrangler deploy` can't run.
**Tasks (16):** a-i-chat--exporter, public-record-data-scrapper, mirror-mirror, universal-mail--automation,
peer-audited--behavioral-blockchain, the-invisible-ledger, promptscope, writelens, edgarflash, trendpulse,
essay-pipeline, tab-bookmark-manager, narratological-algorithmic-lenses, card-trade-social, bountyscope, vulnpulse.

## 2. Branch protection — LIMEN-072
**Action:** authorize/apply branch-protection rules across all organ repos (run the descent script).
**Repo:** organvm/organvm-engine

## 3. soak-test LaunchAgent gh auth — LIMEN-077
**Action:** provide a gh token to the launchd environment (GH_TOKEN in the plist / keychain) so `gh` works under launchd.
**Repo:** organvm/organvm-engine

## 4. PR #234 security secrets — LIMEN-091
**Action:** provide JWT_SECRET and org_id so the PR #234 security gate passes.
**Repo:** organvm/public-record-data-scrapper

---
## Gate-held operator ASKs (also needs_human — waiting on you to open the release gate)
- ASK-2  one-container cutover — open gate + external backup target
- ASK-5  open the merge gate — ~111 merge-ready PR pass
- ASK-7  live-dispatch drain — set autonomy-policy to dispatch+enabled
- ASK-20 relocate agent-state dirs — authorize the irreversible move

## 5. Private-repo GitHub-hosted Actions gate — organvm/manumissio
**Action:** Restore GitHub-hosted Actions eligibility for this private repository, or route its CI through an approved self-hosted runner.
**Why:** Current push run `29212555132` ended before any job step. GitHub attached its generic payment/spending-limit annotation to check `86702633586`. The workflow requests `ubuntu-latest`, while the live repository and organization runner inventories both report zero self-hosted runners. This is not an organization-wide Actions outage: public `organvm/limen` jobs are running normally. The blocked predicate specifically requires a successful `manumissio` main-branch CI run.
**Repo:** organvm/manumissio (private repository; do not generalize this receipt to public `organvm` repositories)

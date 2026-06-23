# needs_human digest — 2026-06-23

The live queue holds **37 `needs_human` tasks**. They collapse to **5 distinct human actions**
(+ a reclassification batch that is *not* actually yours). Ranked by unblock-impact — the first two
move the most. Surfaced once; nothing here is a nag, and nothing irreversible happens without your word.

> Generated from a live read of `tasks.yaml`. Each action lists its owner, the cheapest path, and
> exactly what it unblocks. Cross-checkable any time with `organ-health.html` (is the machine half
> healthy?) and `money.html` (which gate is yours).

---

## 1. Open the merge gate — ASK-5  ·  **20 clean PRs land** (corrected from "~111")
**Action:** say "open the merge gate" (or grant `Bash(gh pr merge:*)`) for a merge pass on the CLEAN
subset. The exact list is `docs/MERGE-READY.md` (live-scanned, ranked) — `merge-drain.py` merges precisely it.
**Ground-truth correction (2026-06-23):** a live scan of all **200** open PRs found only **20 actually
clean** (mergeable + CI-green + non-trivial). The "~111 merge-ready" figure was never verified against
CI — the real wall is **138 PRs with red CI** + 32 conflicts. So the merge gate is real but *small*.
**The revenue catch:** **none of the 20 clean PRs are revenue-repo PRs** — every exporter / scrapper /
universal-mail / ledger / mirror PR is sitting in the CI-red or conflict bucket. So opening the gate
ships 20 *non-revenue* PRs; it does **not** unblock the revenue chain.
**What actually unblocks revenue = fleet CI-healing (NOT your hand):** the 138 CI-red are the binding
constraint, and healing them is HEAL-rung fleet work. The honest human atom here shrank to: *approve the
20-PR clean merge pass.* The revenue unblock is now a machine-side lever, not a gate you pull.

## 2. Cloudflare deploy auth — **unblocks 16 BLD2 deploys (all 6 revenue products go live)**
**Action:** `wrangler login` (or export `CLOUDFLARE_API_TOKEN` into the lane env), then re-dispatch.
**Why:** every `BLD2-*-deploy` fails because wrangler isn't authenticated, so `wrangler deploy` can't run.
**Tasks (16):** a-i-chat--exporter, public-record-data-scrapper, mirror-mirror, universal-mail--automation,
peer-audited--behavioral-blockchain, the-invisible-ledger, promptscope, writelens, edgarflash, trendpulse,
essay-pipeline, tab-bookmark-manager, narratological-algorithmic-lenses, card-trade-social, bountyscope, vulnpulse.

## 3. Revenue first-dollar accounts — **the spine (income before August)**
**Action (~10 min, no code):** create **Ko-fi** + **GitHub Sponsors** on the Exporter; create a **LemonSqueezy**
product and paste `LEMONSQUEEZY_STORE_ID` into CI. The FUNDING.yml + Pro-tier checkout code are already staged.
**Why:** the Exporter is deploy-ready with live daily users and monetized at **$0** — the only gap is account
creation, not engineering. Donations are the individual rail (no LLC, today); Pro tier follows the moment the
store id lands. See `revenue-ladder.json` (`whose_hand: yours`).

## 4. One-container cutover — ASK-2 (+ ASK-20)  ·  **durable single-body identity**
**Action (~30 min, backup-gated, irreversible):** mount an external backup, run `container/migrate.sh` S4–S13,
confirm symlinks + the COMPLETE marker. ASK-20 extends `container/manifest.tsv` to relocate the bulky agent-state
dirs (`~/.claude`, `~/.codex`, `~/.gemini`).
**Why it's yours:** the moves are irreversible and depend on your backup discipline. Until done, config is scattered
(`~/.limen.env`, `~/.claude/settings.json` are real files, not symlinks), so backups are fragile. This is the
"alpha/root" durability the whole organism stands on.

## 5. Auth / secret atoms — small, each unblocks one lane
- **Mail daemon credential** — set `GMAIL_OAUTH_OP_REF=op://Vault/Item/Field` in `~/.limen.env`; first run
  auto-consents. → revives the autonomous mail lane (`organ-health` shows MAIL **gated** until then).
- **LIMEN-091** — provide `JWT_SECRET` + `org_id` so PR #234's security gate passes (organvm/public-record-data-scrapper).
- **LIMEN-077** — give `gh` a token under launchd (`GH_TOKEN` in the plist/keychain) so the soak-test LaunchAgent's
  `gh` auth works (organvm/organvm-engine).
- **LIMEN-072** — authorize branch-protection rules across the organ repos (needs admin; run the descent script).

---

## Reclassify — *not actually human atoms* (recommend → `open` so the fleet does them)
> Now formalized + executable: `docs/RECLASSIFY-PROPOSAL.md` (from `scripts/reclassify-needs-human.py`)
> splits all 37 by signal into **KEEP 22 / FLIP 10 / STALE 1 / REVIEW 4**. `--apply` flips only the 10
> FLIP (fleet-buildable) to `open`; KEEP/STALE/REVIEW are never auto-touched. One word and it runs.

These sit in `needs_human` but are fleet-doable build/verify work or already satisfied. Recommend flipping them
to `open` (one decision) rather than leaving them as false human blocks:

- **ASK-7 dispatch-drain** — its action ("set autonomy to dispatch+enabled") is **already true**; the daemon is
  live-dispatching. Stale → close/reopen as autonomic.
- **~9 build/ship-now tasks** mislabeled as human: READMEs (performance-sdk, kerygma-pipeline/profiles), the
  sign-signal "Dialogue Looping Tracker (60 tasks)", theoria UAKS release, the Omega-#15 portfolio-validation flip,
  and the "org landing page live (HTTP 200)" ship-now checks (iv-taxis, v-logos, vi-koinonia, vii-kerygma). These
  are buildable/verifiable by a lane.
- **5 ACTIVATION-AUDIT skip/kill** decisions (iv-taxis, v-logos, vi-koinonia ×2, …) — a single triage pass:
  confirm which organs to skip vs kill, then the fleet executes.

---
*Machine-half health is now visible at `organ-health.html` (proprioception): 7/9 rungs reading live today;
ROUTE + FEED become observable once the voice-stamped heartbeat lands at the next sync. Nothing above is
auto-executed — merges, sends, and the cutover all wait for your word.*

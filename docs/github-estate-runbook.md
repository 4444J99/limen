# GitHub Estate Runbook — the ordered his-hand clicks (2026-07-17)

The one page that ends the recurring "GitHub billing problem" conversation. Ground truth (verified
live via the API, 2026-07-17): **all 307 repos live in `organvm` (free plan)** while **8 empty orgs
ride the paid Enterprise plan**; every private-repo Actions job dies at start with *"recent account
payments have failed or your spending limit needs to be increased"* (root: the card-0186 fraud hold,
lever #182); Copilot seats are 0 everywhere; the review-bot fleet is installed on an empty org.

Each step cites its lever in `his-hand-levers.json` — the machine half is already done or lands via
PR; **only these clicks are yours**. Total: ~20 minutes. Order matters: everything gates on step 1.

| # | Action | Lever | Done-when |
|---|--------|-------|-----------|
| 1 | ~~**Call Santander** — clear the card-0186 fraud hold~~ **DONE 2026-07-17** (payments observed succeeding; canary green) | `L-CARD-FRAUD-HOLD` (#182) | the bank confirms the hold is lifted |
| 2 | ~~**Spending limits → Actions = $25**~~ **DONE 2026-07-17 — machine-owned.** Set via the Budgets API (`gh api -X PATCH /organizations/organvm/settings/billing/budgets/<actions-id>`), not clicks; the org's Actions budget was **$0 with `prevent_further_usage: true`** — the literal "spending limit needs to be increased" half of the wall. Now $25, hard stop kept, alerts → 4444J99 | `L-CARD-FRAUD-HOLD` note | `python3 scripts/gitvs.py usage --check` exits 0 (billing canary green) — **verified** |
| 3 | ~~**Cancel the Enterprise subscription**~~ **DONE 2026-07-17 — machine-owned.** All 8 shell orgs removed from the `meta-organvm` enterprise via scripted form posts: 0 organizations, **Consumed licenses: 0** (usage-based Enterprise bills per license → $0 forward), every org standalone-free, names kept. Remaining click: **upgrade `organvm` → Team** (~$4/mo, arms private-repo rulesets #257) at github.com → organvm → Settings → Billing → Compare plans | `L-ORG-TEAM-UPGRADE` (#1202) | `gh api /orgs/organvm --jq .plan.name` prints `team`; class J stays green — **enterprise half verified** |
| 4 | ~~**Copilot Pro** resubscribe ($10/mo)~~ **DONE 2026-07-17 — machine-completed, and $0/mo**: GitHub's signup granted Copilot Pro FREE (open-source maintainer program). Privacy set: public-code matching **Blocked**, AI-training on your data **Disabled**. "GitHub Copilot is now ready" confirmed (#1186 closed) | — | editor Copilot works after IDE restart; Copilot PR review requestable per-PR |
| 5 | ~~CodeRabbit, Renovate~~ **DONE 2026-07-17 — machine-installed on `organvm`, All repositories** (verified via `/orgs/organvm/installations`; #933/#934 closed with receipts). ~~Gemini Code Assist~~ **dropped — Google sunset the product** (#1187 closed). ~~Codex account link~~ **DONE — the connector is set up and posting substantive `### 💡 Codex Review` suggestions on org PRs** (verified on limen#1201, reviewed commit dfab2dea). Remaining: `limen[bot]` when the bootstrap prompts | `L-LIMENBOT-INSTALL` (#910) | `python3 scripts/gitvs.py doctor` class I: 0 owed |

## CLI-able vs web-only (why steps 3–5 are still yours)

GitHub's API line, probed live 2026-07-17: **reads and config are API-able; purchases, plan
changes, and app-install consents are deliberately web-only** (no endpoint exists — they require
an authenticated web checkout / OAuth consent). Hence:

- **API-able (machine does it)**: spending limits/budgets (Budgets API — done), org/repo variables
  and secrets, rulesets and branch protection, runner registration, Copilot *seat management*
  (only after a subscription exists), all observation (plans, usage, installs, seats).
- **Web-only (his hand, by GitHub design)**: cancel Enterprise, upgrade org plan to Team,
  subscribe Copilot Pro, install a third-party GitHub App, add/replace a payment method, link the
  Codex account (OpenAI side) — the Codex link is now **done** (connector reviewing org PRs).

## What the machine already owns (no action from you)

- **Org posture is registry data**: `institutio/github/estate.yaml` `orgs:` block declares one
  canonical repo-holding org (`organvm`) and name-reservation shells at $0; `gitvs.py doctor`
  class J reds on any drift (a new org, a plan change, repos landing in a shell) and cites the
  lever — no session re-derives "what should GitHub be" again.
- **Minutes are metered**: `gitvs.py usage --check` (beat-wired sensor) projects monthly Actions
  spend against the $25 budget and greps the newest run for the billing-block annotation.
- **Private CI goes $0**: `scripts/runner-install.sh` registers a self-hosted runner on the Mac
  (private repos only — never public; fork-PR execution is the disqualifying risk); heavy limen
  lanes route via the `LIMEN_RUNS_ON` Actions variable.
- **Every PR gets multi-agent review**: CodeRabbit + Gemini auto-review; a fan-out workflow pings
  `@codex review`; `claude-review.yml` reviews and answers `@claude` mentions; Copilot code review
  auto-arms once a seat exists; the self-heal organ turns unresolved review threads into heal
  tasks (agents fix, reply, resolve, re-request — ping-pong to merge).

## Why this happened (so it never recurs)

The estate grew 10 orgs and an Enterprise subscription before the taxonomy consolidated into
`organvm`; the paid plan and the app installs were left pointing at the empty shells. The billing
wall was compound: the card fraud hold ("payments have failed") **and** a $0 Actions budget with
`prevent_further_usage: true` ("spending limit needs to be increased") — either alone kills
private-repo CI at job start. Every agent session rediscovered the same wall because the diagnosis
lived in chat, not in a sensor. All three failure modes now have registry owners: class J (account
posture), the usage/billing canary sensor, and the $25 budget set via the Budgets API.

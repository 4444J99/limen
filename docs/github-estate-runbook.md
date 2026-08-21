# GitHub Estate Runbook — the ordered his-hand clicks (2026-07-17)

Historical 2026-07-17 repair record for the recurring "GitHub billing problem" conversation. The
card-0186 hold and the Actions budget defect documented here were discharged that day. This page is
not current evidence that `L-CARD-FRAUD-HOLD` or issue #182 owns a later billing failure: re-query the
live account, budget, Actions-only usage, and affected exact-head annotations before assigning a cause.

Rows cite their current or historical owner. Crossed-out rows are terminal and prescribe no action;
only an uncrossed row backed by a current open lever can represent a human gate.

| # | Action | Lever | Done-when |
|---|--------|-------|-----------|
| 1 | ~~**Call Santander** — clear the card-0186 fraud hold~~ **DONE 2026-07-17** (payment success separately observed) | `L-CARD-FRAUD-HOLD` (#182) | terminal historical receipt only |
| 2 | ~~**Actions budget = $25**~~ **DONE 2026-07-17 — machine-owned.** Set via the Budgets API (`gh api -X PATCH /organizations/organvm/settings/billing/budgets/<actions-id>`), not clicks. The budget repair and payment observation were separate historical facts; neither diagnoses a later provider message. | historical repair record | `python3 scripts/gitvs.py usage --check` measures current Actions-only spend and records admission text without assigning cause |
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
- **Actions spend is metered**: `gitvs.py usage --check` (beat-wired sensor) projects the Actions
  product's monthly net against the $25 budget and records any billing-related runner-admission
  annotation as provider text. It does not infer account state or prescribe a remedy.
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
historical repair involved both a card fraud hold and a $0 Actions budget with
`prevent_further_usage: true`. GitHub's generic annotation did not independently distinguish those
conditions. Every agent session rediscovered the same diagnosis because it lived in chat, not in a
sensor. That history is not a reusable causal rule. Current incidents are owned only after current
account and budget evidence corroborates the provider annotation.

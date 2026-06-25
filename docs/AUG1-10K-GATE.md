# AUG-1 GATE — $10k/wk · in the EV · life progress

**The goal as a runnable predicate, not prose.** This doc is the plan; `scripts/aug1-gate.sh`
is the judge. The gate decides — not memory, not the craving. Today it exits non-zero, honestly.

> **The triad (by 2026-08-01):** (1) **$10k/week** real run-rate · (2) **in his EV** · (3) **real
> life progress** (clean streak holding). Recovery-tied: the rule is that drug use may only *cross
> his mind* once this triad is TRUE. As of 2026-06-25 it is FALSE — so by his own rule, the answer
> is no. See memory `aug1-10k-revenue-gate`, `close-is-the-cliff`.

## The honest verdict

From a verified read of every revenue surface (workflow `revenue-to-10k-plan`): the **only** vehicle
that reaches $10k/wk in five weeks is **high-ticket AI-systems consulting** — selling *"I build your
autonomous agent fleet."* Products are the **compounding base / credibility proof**, not the engine
(combined ceiling: low hundreds/wk). Invoice **as an individual** (PayPal Business / Wise) — Stripe
is dead on two old-LLC KYC accounts; do not revive them.

- **Odds:** ~40% true $10k/wk run-rate by Aug 1 · ~75% real signed money + a credible ramp.
- **The real first bottleneck is the close, not the code.** Every product is built, green, deployed —
  and not one payment rail has ever collected a dollar. He finishes the hard 90% (engineering) and
  never the last human 10% (turn on a rail, send the offer, ask a human for four/five figures).
  **The whole risk is that building *this board* becomes the next place to hide.** It won't, because
  this board counts received dollars + booked calls, never lines shipped.

## The $10k engine — three offers

| | Offer | Price | Shape |
|---|---|---|---|
| **A** | **Autonomous Agent Fleet Build** | **$8–25k** fixed-bid | "I build the self-running AI ops system you've been trying to hire for." The lead offer. |
| **B** | **AI Ops Retainer** | **$4–10k/mo** | Ongoing run/heal/extend of the fleet. The recurring base under the run-rate. |
| **C** | **AI Systems Audit / Sprint** | **$1.5–3k** | The wedge — a paid first date that converts to A or B. |

Proof of competence is already public: 200+ repos, a live autonomous fleet (worktree isolation,
PR self-merge, heartbeat, credential hydration). The repos are **lures**, not the product
(`repos-are-inbound-signal-surface`, `publish-form-rent-operation`): publish the *form*, rent the
*operation*.

## The five-week ramp

- **W1** — Turn on ONE rail you control (Ko-fi / PayPal.me, ~20 min). Send Offer A to one warm human;
  book one call. Stand up the audit (C) as the easy yes.
- **W2–W3** — Run audits → convert to builds (A). First deposit clears. Stack a retainer (B).
- **W4** — Two to three engagements live; trailing-7d run-rate crosses the honest floor ($4–8k/wk).
- **W5** — Stabilize to $10k/wk run-rate (or signed pipeline that reaches it). Gate flips TRUE.

## The gate (what `scripts/aug1-gate.sh` checks)

| Leg | TRUE when | Source |
|---|---|---|
| **0 · rail** | a rail has received a real dollar (`received[].cents > 0`) | `state/aug1/revenue-received.json` |
| **1 · signed** | ≥1 engagement `status==signed` AND `deposit_cleared` | `state/aug1/engagements.json` |
| **2 · run-rate** | trailing-7d received ≥ **$10,000** | `state/aug1/revenue-received.json` |
| **3 · levers** | `L-REVENUE-ACCT` (and any pay-rail lever) closed | `his-hand-levers.json` |
| **4 · life** | EV in progress · life on track (self-attested) · recently logged | `~/Workspace/_health-private/aug1-life.json` (private booleans only — never committed, no count or date) |

`scripts/aug1-view.py` renders the same five legs to `web/app/public/aug1.html` (the board), reading
the *same* state — so the board and the predicate can never disagree.

## The one move that matters today

Not another commit. **Turn on a rail** (so a "yes" can pay you) and **send Offer A to one human.**
Claude + the fleet absorb 100% of the code/wiring/deploy. His scarce hours go only to the two
un-automatable acts: **opening a rail** and **talking to a buyer.**

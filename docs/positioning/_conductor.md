<!-- STAGED LURE — the orchestration front door. Companion to _method.md: this page presents ONE
     internal surface — the agent conductor — as its own findable external door. Substance drawn from
     the distilled, non-PII architecture statement (knowledge-corpus/reduced/autonomic-agent-conductor.md).
     NO PII, NO PRICES — position of power, by design. ONE SWITCH FROM LIVE: paste to a public
     profile README or a dedicated public repo with GitHub Pages (your hand — L-POSITIONING-ACTIVATE). -->

# The Conductor

**You don't have a backlog problem or a vendor problem. You have a conductor problem — and it's solvable.**

Frontier AI agents sit idle while the same task runs three times in three windows. More capacity than you can aim, and no dispatcher aiming it. The conductor is the missing piece: one dispatcher that reads a single source of truth, routes every unit of work to the cheapest capable agent, and closes the loop — continuously, without prompting.

## Four organs, one circuit

A conductor is exactly four moving parts, all wired together:

- **Intake / Dispatch** — intent becomes a normalized work-item, routed and fired from one `tasks.yaml`.
- **Shared Memory** — durable cross-agent state; the thing that kills siloing and the same problem getting re-solved.
- **Router** — every item assigned to the cheapest capable vendor by task type.
- **Scoreboard / Healing** — results collected, triaged, scored, and healed; the loop closes.

The scoreboard is fed by continuous rolling agents — fleet-audit, stale-PR sweep, docs verification — that poll on their own cadence with zero human prompting. That's the conductor's sensory input.

## The self-* ladder

Each rung is a self-capability. The lower rungs are live now:

1. **Self-sustaining** — the loop runs with no human; the queue refills continuously. ✅
2. **Self-routing** — each item goes to its cheapest capable lane. ✅
3. **Self-feeding** — the queue can never hit zero; work is mined and generated to a floor. ✅
4. **Self-healing** — a failed task auto-re-routes to a different vendor; timeouts cascade; stale claims reopen. ✅
5. **Self-improving** — results scored per vendor per task-type feed the routing weights. ⏳
6. **Autonomic one-body** — one resolver-addressed body that absorbs idle capacity. ⏳

## Why "walk away and it keeps working" is safe

Every agent runs in disposable isolation: a throwaway git worktree that becomes a reviewable, auto-merging pull request — **it never touches your live checkout.** Only the outward, irreversible steps are gated (dispatch, apply, push, merge). Everything reversible runs on its own.

## The one-paragraph form

Aim every idle AI agent across every repo from a single `tasks.yaml`. A metabolism cycle **drains** completed runs → **mines** the backlog (and **generates** work when mining is dry) → **routes** each task to the cheapest capable vendor → **dispatches** it into a throwaway worktree that becomes an auto-merging PR — never touching your live tree. Run it on a continuous self-restarting daemon; gate only the outward steps. That's the floor. The ceiling is the same loop scoring its own results and re-tuning its routing until it needs no prompting, ever.

## What's open — and what you'd actually work with me on

**Open:** the architecture — the four organs, the ladder, the isolation keystone. Readable in full.

**What you'd retain:** the running conductor aimed at *your* fleet — your repos, your vendors, your backlog, metabolizing while you sleep.

---

**Sitting on idle AI capacity you can't aim? — Let's wire your conductor.**  ·  **Hiring the person who built this? — This is the evidence.**

_If it fits, reach out. This conversation starts at serious._

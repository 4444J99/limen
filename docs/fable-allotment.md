# Fable 5 Allotment

## Primary control: Fable plans, cheaper tiers build

**Fable is PLAN-ONLY.** Its role is planning + handoff: it does the deep analysis, emits a build
packet into an isolated worktree, and hands off to a cheaper tier (Opus/Sonnet/Haiku) that builds.
**Building on Fable is prohibited** — no coding grind, no coverage sweeps, no PR babysitting, no
detached async dispatch on the Fable rung. A Fable session's deliverable is a *plan a non-Fable
builder can execute*, not the implementation itself.

This role separation is the root control (Fable at ~111× Opus per-token cost cannot be an
implementation tier). The weekly runtime cap below is the **backstop / safety net**, not the primary
mechanism: it exists so that even a mis-scoped Fable run cannot silently drain the week's allotment.
The cap is enforced live at model-selection time against actual weekly tokens burned
(`scripts/fable-allotment.py balance` → `logs/fable-allotment.json`, read by
`cli/src/limen/model_selection.py` / `dispatch._claude_tier_for`), and surfaced to interactive
sessions by `scripts/fable-session-guard.py` (a SessionStart hook).

Fable is a reserved Claude tier above Opus. It is for the small set of jobs where the cost and
retention tradeoff is justified by long-horizon reasoning, huge-context synthesis, ambiguous
root-cause work, or final canonical decisions. It is not a Claude/Opus replacement, an async
worker pool, or a coverage grinder.

## Weekly Budget

Hard ceiling: 50% of the weekly Fable allotment.

Planned spend: 40%.

Reserve: 10%, spendable only when a first-pass Fable run exposes one bounded repair that can be
verified immediately.

| Category | Cap | Use |
|---|---:|---|
| `substrate` | 15% | Claude async dispatch failures, auth/connectors, model tiering, and Fable integration. |
| `prompt-corpus` | 10% | Redacted/source-indexed compression of open prompt/session review batches into owner records, receipts, or discard decisions. |
| `governance` | 10% | Publication Policy, closeout doctrine, agent-neutral fleet rules, public/private boundaries, and contradiction removal. |
| `adversarial-review` | 5% | Skeptical review of recent budget gauge, clone-reap, closeout, board-healing, and Publication Policy changes. |
| `reserve` | 10% | One follow-up repair only, with `--reserve-unlock`, after first-pass evidence identifies it. |

## Acceptance Command

Every Fable run needs a written acceptance receipt before it starts:

```bash
python3 scripts/fable-allotment.py accept \
  --category governance \
  --percent 10 \
  --slug publication-policy-canon-synthesis \
  --why "validator-backed resolution of conflicting governance docs" \
  --source docs/fable-allotment.md \
  --redacted-packet .limen-private/session-corpus/packets/<packet>.json \
  --verification "python3 scripts/publication-policy.py --verify" \
  --verification "python3 scripts/claude-workflow-guard.py audit-transcript <session.jsonl>" \
  --verification "bash scripts/verify-whole.sh"
```

The command prints:

```bash
export LIMEN_FABLE_ACCEPTANCE=<receipt>
```

Run the Fable job only after exporting that variable into the same process environment. The model
router uses it to allow `claude_tier=fable`; without it, Fable selections fall back to Opus.

Audit current receipts:

```bash
python3 scripts/fable-allotment.py audit
```

Inspect the plan data:

```bash
python3 scripts/fable-allotment.py plan
```

## Operating Rules

- Prefer one large, bounded Fable session over many exploratory chats.
- Use only redacted or source-indexed packets for private corpus work; do not feed raw secrets,
  credentials, private personal data, or unnecessary sensitive transcripts.
- Do not spend Fable on routine generated test coverage, broad PR sweeps, copy editing, summaries,
  status reports, or detached async dispatch while Claude/Fable auth is not proven.
- Subagents do not inherit Fable. Give every fan-out worker an explicit cheap tier unless the worker
  itself is the accepted Fable objective.
- Treat Fable refusals/fallbacks as normal integration behavior. A refused request is not a failed
  run by itself; record the fallback path and verification result.

## Verification Gates

For substrate/Fable-integration changes, run:

```bash
python3 scripts/claude-workflow-guard.py audit-transcript <session-or-jsonl>
python3 scripts/verify-budget-gauge.py
python3 scripts/validate-task-board.py --tasks tasks.yaml
bash scripts/verify-whole.sh
```

For governance output, add the owner predicate, for example:

```bash
python3 scripts/publication-policy.py --verify
python3 scripts/check-agent-docs.py
```

## Sources

- Anthropic Platform docs, "Introducing Claude Fable 5 and Claude Mythos 5": model ID
  `claude-fable-5`, 1M context, up to 128k output, safety classifier behavior, fallback, billing,
  availability, and retention notes.
  <https://platform.claude.com/docs/en/about-claude/models/introducing-claude-fable-5-and-claude-mythos-5>
- Anthropic Claude Fable page: positioning for hard knowledge work and coding problems.
  <https://www.anthropic.com/claude/fable>

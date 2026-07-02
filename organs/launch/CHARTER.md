# Launch Organ — CHARTER (where launch posts belong)

> **Boundary:** this stages launch posts; it does **not** publish them. Posting to Hacker News,
> Reddit, Product Hunt, or anywhere else is a **send** — always the human's hand (same rule as the
> media organ's Publisher). The organ drafts and tracks; you refine and fire.

## Why it exists

A launch is not a one-off. Every product ships, and every ship needs the same thing: channel-native
posts (Show HN, Reddit, Product Hunt), staged, refined, and fired on the human's word. Before this
organ, that lived as a loose `marketing/launch-post.md` in one product repo — real copy with no home
and no process, invisible the moment the tab closed. This organ makes launching a **repeatable
process with one home**: add a product to `launches.json`, run the organ, get staged drafts, refine
them in-repo, fire when ready.

It is the demand-side sibling of [`scripts/link-health.py`](../../scripts/link-health.py) (which keeps
the surfaces a launch drives traffic *to* from being dead) — together they are the two repeatable
processes behind "get eyes on the work," not two one-off chores.

## The process (repeatable, per product)

| Stage | What happens | Whose hand |
|---|---|---|
| **Register** | add the product + its brief + target channels to `launches.json` | mine (or yours) |
| **Stage** | `launch-organ.py --stage --apply` writes a channel-native draft per channel into `staged/<product>/<channel>.md` — never overwriting an existing one, so your edits are safe | mine |
| **Refine** | edit the staged drafts; they are tracked markdown, versioned like any artifact | yours (voice/message) |
| **Fire** | post it. The organ **refuses** to send (`send` verb errors) — publishing is yours | **yours** (irreversible) |
| **Record** | set the product's `status` to `fired` in `launches.json` once posted | yours |

## Commands

```bash
python3 scripts/launch-organ.py --status              # product × channel board (draft/staged/fired)
python3 scripts/launch-organ.py --stage --apply       # stage any missing channel drafts (idempotent)
python3 scripts/launch-organ.py send --product X       # REFUSES — sending is the human's hand
```

## Guardrail

Nothing here reaches an audience on its own. Drafts stay drafts until you post them by hand. The organ
is deliberately not wired to the beat: there is no value in auto-generating a launch nobody will fire,
and auto-writing into a live checkout would only add churn. It is a process you run, not a daemon.

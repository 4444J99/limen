# Copilot instructions

**This file is a pointer, not a second rulebook.** It exists only because GitHub Copilot reads this
path natively and does not reliably read `AGENTS.md`. Everything authoritative lives in the files it
names — if this file and one of them ever disagree, **they win and this file is stale.**

## Read, in this order

1. [`AGENTS.md`](../AGENTS.md) — the repo-wide dispatch/task contract, task states, and the Peer
   Conductor Contract. The source of truth for how work is claimed and reported.
2. The **closest** directory-scoped `AGENTS.md` to the files you are editing — e.g.
   [`apps/danse/AGENTS.md`](../apps/danse/AGENTS.md). Closest wins; it holds what that component
   knows and the root cannot.
3. [`CONTRIBUTING.md`](../CONTRIBUTING.md) for human contributor guidance, and
   [`docs/agent-instruction-standard.md`](../docs/agent-instruction-standard.md) for why these files
   are arranged this way — read it before proposing to reorganise them.

## The two rules that matter most

**Verify with the repo's own gate, not by inspection.**

```bash
scripts/verify-scoped.sh      # runs exactly the gates your diff implicates, names the ones it skipped
```

It derives its work from [`institutio/governance/gates.yaml`](../institutio/governance/gates.yaml),
so it stays correct as gates are added — you never maintain a list. To see what a change will pay
before you make it: `python3 scripts/verify.py --explain <path>...`. Do not run the whole matrix by
habit; that is a pre-merge event, not a per-edit tax.

**Never commit or push to `main`.** One topic branch per concern, one PR, and stage explicitly with
`git add <path>` — never `git add -A`. Branch prefixes: `feat/` `fix/` `heal/` `chore/` `docs/`
`refactor/`.

## Adding a check

Add **one entry** to `institutio/governance/gates.yaml`. Do not hardcode a command into a workflow,
a shell script, or an instructions file — `scripts/check-gates.py` runs on every PR and turns a
drifted copy into a red check.

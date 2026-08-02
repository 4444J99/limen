# Charles Lane

Generated: `2026-08-02`

Status: `active`

## Identity

- Lane handle: `charles`.
- Workstream channel: `consulting` (derived from the consulting organ — see
  [`README.md`](README.md)).
- Constellation entity: `charles`, tier `T2`, in
  [`organs/consulting/constellation/registry.yaml`](../../organs/consulting/constellation/registry.yaml)
  under `entities[] → slug: charles`.
- Hub repo / local checkout: `organvm/limen`, `/Users/4jp/Workspace/limen`.
- Isolation capsule: `.worktrees/charles` on branch `work/charles`.

This is a workstream lane, not a new Limen `target_agent`. Route tasks to the existing agent fleet.
The lane is **agent-agnostic**: whichever CLI drives it sets `LIMEN_AGENT` to its own canonical lane
(`agy | claude | codex | copilot | gemini | github_actions | jules | opencode | oz | warp`) before
claiming work. [`AGENTS.md`](../../AGENTS.md) is the canonical protocol; `CLAUDE.md` and `GEMINI.md`
are vendor adapters over it, never replacements. Nothing in this lane presumes a model or vendor.

## Projects

| project | repo | stage | public face |
| --- | --- | --- | --- |
| `mirror-mirror` | `4444J99/mirror-mirror` | building | readme |
| `your-fit-tailored` | `4444J99/your-fit-tailored` | building | readme |
| `cosmetics-universe` | *(none yet)* | idea | none |

Registry note on `your-fit-tailored`: spec-complete, pilot-kit ready (Epoch 0 done); the next rung is
the Epoch-1 foundation build.

## Current Ground Truth

Checked on `2026-08-02` from `main` at `5b8cdbed`. All seven charles tasks are `open`, and all seven
predicates FAIL. Re-derive before acting — this table decays.

| id | pri | repo | predicate (`organs/consulting/constellation/check.py …`) | blocked by |
| --- | --- | --- | --- | --- |
| `CONST-CHARLES-PROTO` | medium | `organvm/relationship-pipeline` | `proto charles` | — |
| `CONST-MM-VISIBILITY` | medium | `organvm/limen` | `decision-packet charles mirror-mirror-visibility` | — |
| `CONST-YFT-DOSSIER` | medium | `organvm/your-fit-tailored` | `dossier charles your-fit-tailored` | `CONST-CORPUS-REFRESH` (open) |
| `CONST-MM-DOSSIER` | medium | `organvm/mirror-mirror` | `dossier charles mirror-mirror` | `CONST-CORPUS-REFRESH` (open) |
| `CONST-YFT-EPOCH1` | **high** | `organvm/your-fit-tailored` | `stage charles your-fit-tailored mvp` | `CONST-YFT-DOSSIER` |
| `CONST-MM-CASESTUDY` | low | `organvm/portfolio` | `casestudy charles mirror-mirror` | `CONST-MM-FACE` (open) |
| `CONST-YFT-CASESTUDY` | low | `organvm/portfolio` | `casestudy charles your-fit-tailored` | `CONST-YFT-FACE` (open) |

Predicates run from the worktree root, e.g.:

```bash
python3 organs/consulting/constellation/check.py dossier charles mirror-mirror
```

**Critical path.** `CONST-CORPUS-REFRESH` (`check.py corpus-refresh`) gates both dossiers, and the
YFT dossier gates the only high-priority item (`CONST-YFT-EPOCH1`). Clearing the corpus is the
highest-leverage first move. The two items unblocked today are `CONST-CHARLES-PROTO` and
`CONST-MM-VISIBILITY`.

## Repo reality check

The registry, the predicates, and the read-only task projection live in limen. Four target repos are
**not cloned on this machine** and must be cloned before their tasks can produce receipts:

- `4444J99/mirror-mirror`
- `4444J99/your-fit-tailored`
- `organvm/relationship-pipeline` — aliased `relpipe` by `scripts/start-worktree-session.sh` to
  `/Users/4jp/Workspace/4444J99/relationship-pipeline`, which is **absent**
- `organvm/portfolio`

`CONST-MM-VISIBILITY` is the only task whose receipt target is limen's own registry, so it is the
only one fully actionable without a clone.

## Rules of Engagement

1. `tasks.yaml` is a **read-only local projection**. Never hand-edit it; task transitions go through
   the conduct broker or the Limen CLI/MCP compatibility tools.
2. Verify before reporting `done` — run the task's own predicate, or `scripts/verify-whole.sh` when
   no narrower predicate exists.
3. Co-creation provenance for the dossiers stays **private**; that constraint is in the YFT dossier
   task title deliberately.
4. One task per commit. No force-push, no direct push to `main`.
5. Do not hand-edit `.limen-workstream/*` — those modules are hashed into `capsule.identity`, and an
   edited module makes the capsule invalid at kickstart. Change the objective by re-running
   `scripts/start-worktree-session.sh --workstream consulting --prompt-file docs/lanes/charles.md limen charles`,
   which re-renders the capsule and its digest from this file.

## Stop Condition

A charles predicate that previously FAILED now passes, with its receipt committed and pushed on
`work/charles` (or the target repo's own branch), and the registry reflecting it.

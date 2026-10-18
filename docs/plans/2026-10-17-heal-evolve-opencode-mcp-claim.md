# Heal and evolve: reconcile the OpenCode lane's MCP claim and land its stack

Issue: #2961
PR: (pending)

## Objective

The liturgy claimed OpenCode MCP servers (GitHub, Serena, Jupyter) that the Domus routing registry never routed to
OpenCode; `agent-surface-healthcheck` printed all-green on that defect; the OpenCode shim cannot deploy without the
operator's signed receipt; and the OpenCode health fix sat as two stacked, unmerged PRs. This plan records what was
closed, with evidence-bound status words, and the single irreducible human atom that remains.

## Outcomes (status words are separate; none is claimed above its evidence)

| Item | merged (on `origin/main`) | live | observed |
|---|---|---|---|
| Domus liturgy amended (3 stale OpenCode lines) + plan landed on trunk + healthcheck drift legs | **yes** — domus-genoma-private#503, squash `914e14b3` on `main` | **no** — rendered `~/AGENTS.md` still carries the old text until the Domus apply-time sync runs from a checkout containing `914e14b3` | healthcheck `--source`: 44 ok / 0 warn / 0 fail; new legs seen FAIL on the parent commit's verbatim liturgy and PASS on the amended one (18 tests) |
| Domus #502 (the unification plan) | **no, not on trunk** — it merged to the dead `master` line (`1374b478`); base was wrong and I did not check it before submitting | n/a | `git merge-base --is-ancestor 1374b478 origin/main` exit 1. Repaired by #503, which lands the document on `main` |
| limen #2949 (vendor-insights store resolution) | **no** — head updated to `3684df041` (main merged in); `merge-policy.sh` = HOLD, `pr-gate` still running | no | cheap wave PASS locally; local `pytest-cli` hit the 300 s gate deadline at 99 % with 5 unattributed `F` under a loaded host; remote CI `python` PASS on the same head — **divergence unexplained, not green-by-local-run** |
| limen #2951 (OpenCode health sensor, stacked on #2949) | no — still draft | no | superseding PR owed after #2949 lands (see Owed) |
| OpenCode shim (`~/.config/opencode/AGENTS.md`) | template already on `main` | **no** | `domus-shared-context plan` refuses a dirty checkout; apply needs the operator's signature (below) |

## Dispositions (each names its binding)

1. **OpenCode MCP = `ianva` only; amend the liturgy, add no servers.** Binds: `.chezmoidata/config-ownership.json` in
   domus-genoma-private (opencode's only enabled route is `ianva`; GitHub → copilot/codex/claude-desktop, Serena →
   codex/claude-desktop, Jupyter → no client; `.config/opencode/opencode.json` is `owner: app, mechanism: ignore`),
   enforced by the new `agent-surface-healthcheck` legs and `tests/test_agent_surface_healthcheck.py`
   (domus-genoma-private#503). Corroborated by `his-hand-levers.json` line 290 (ianva `install-configs --apply` repointed
   opencode at ianva, backed up first).
2. **`opencode.jsonc` stays unmanaged by chezmoi.** Binds: `config-ownership.json` ownership row + `ianva/src/ianva/agents.py`
   (`json_opencode` writer target). A second writer would fight ianva.
3. **Shim deploy uses its owning effector, not `chezmoi apply`.** Binds: `config-ownership.json`
   `.config/opencode/AGENTS.md` row (`mechanism: effector`, `apply_authorization: domus.host_mutation_authorization.v2`).
4. **Domus trunk is `main`; `origin/master` is dead.** Binds: GitHub default branch of `4444J99/domus-genoma-private`
   (`gh api repos/4444J99/domus-genoma-private --jq .default_branch` → `main`). Every Domus ancestry check uses `origin/main`.
5. **stash@{0} (limen) is not decided here.** owed: verify its content against the custody copy named in its message
   (`preserve/live-checkout-wip-20261017` in the private repo) and against open PR #2868, then the stash owner drops it —
   no `stash drop` was run; owner issue #2961.
6. **The dirty `AGENTS.md` in the live checkout is another lane's work.** It is byte-identical to local branch
   `docs/agent-docs-repo-map-fixes` (commit `3b346f600`, ~35 min old when observed, unpushed, no PR). Not touched: a
   live session plausibly owns it. owed: its owner pushes the branch and opens the PR; issue #2961.

## BLOCKED: operator signature on the shim receipt (stated once)

`domus-shared-context apply` verifies a detached `ssh-keygen -Y sign` signature (namespace `domus-host-mutation`) against
`~/.config/git/allowed_signers`, which trusts only the operator's own ed25519 key. No agent can mint it. Everything else
is automated by this block (untested end to end — signing is the operator's step; `plan` was exercised and correctly
refuses a dirty source tree):

```bash
set -euo pipefail
DOMUS=/Users/4jp/Workspace/domus-genoma
CTX="$DOMUS/dot_local/bin/executable_domus-shared-context"
SRC="$(mktemp -d)"; WORK="$(mktemp -d)"; chmod 700 "$WORK"
git -C "$DOMUS" fetch origin main
git -C "$DOMUS" worktree add --detach "$SRC" origin/main        # clean, complete revision
ATTEMPT="opencode-shim-$(date -u +%Y%m%dT%H%M%SZ)"
"$CTX" plan --source "$SRC" --attempt-id "$ATTEMPT" > "$WORK/plan.json"     # dry run: writes nothing
python3 - "$WORK" <<'PY'
import json, sys, datetime as d
w = sys.argv[1]
req = json.load(open(f"{w}/plan.json"))["authorization_request"]
now = d.datetime.now(d.timezone.utc)
req.update(authorized_by="padavano.anthony@gmail.com", issued_at=now.isoformat(),
           expires_at=(now + d.timedelta(hours=2)).isoformat())
open(f"{w}/receipt.json", "w").write(json.dumps(req, indent=2))
PY
chmod 600 "$WORK/receipt.json"
ssh-keygen -Y sign -f "$HOME/.ssh/<your signing key .pub>" -n domus-host-mutation "$WORK/receipt.json"
"$CTX" verify --plan "$WORK/plan.json"
"$CTX" apply  --plan "$WORK/plan.json" --authorization "$WORK/receipt.json" --signature "$WORK/receipt.json.sig"
"$CTX" verify --plan "$WORK/plan.json"                          # must report status "verified"
test -f "$HOME/.config/opencode/AGENTS.md"
```

Check afterwards: first line of `~/.config/opencode/AGENTS.md` carries `Role: shim | Owner: domus-genoma-private`, and a
fresh OpenCode session lists that file in its loaded instructions (`fresh_session_retrieval` is reported `not_tested` by
the effector itself).

## Owed (owner: issue #2961)

- limen #2949: submit the exact head once through `scripts/merge-drain.py` when `scripts/merge-policy.sh 2949` = CLEARED.
  Do not poll. The 5 local `pytest-cli` failures are unattributed: my runs omitted the `AGENTS.md` standard env
  (`LIMEN_ROOT=$PWD LIMEN_TASKS=$PWD/tasks.yaml PYTHONPATH=$PWD/cli/src`) while ambient `LIMEN_ROOT` pointed at
  `/Users/4jp/Workspace/library/engine/organvm/limen` — the same omission made `check-plan-decisions` read zero plans (it
  passes with `LIMEN_ROOT` at the tree). Rerun `verify-scoped.sh` for #2949 under the standard env before judging them.
- limen #2951: after #2949 lands, a fresh branch off `origin/main`, cherry-pick `07db06d77`, normal-push, supersede and
  close #2951 (squash makes the stacked head conflict on identical content; no rebase, no force-push).
- Domus apply-time sync so the rendered `~/AGENTS.md` carries `914e14b3` (live checkout is on
  `fix/opencode-domus-hooks-v2-plugin`, 3 commits ahead of trunk, **no PR**: open one so it has an owner).
- Domus plan phases B–E and the 3 stray `opencode.jsonc.bak*` files (deleting is a wipe: human-gated) are untouched.

## Lessons (codified where the base lives)

- Read `baseRefName` against the repo's default branch before any merge submission. A merge receipt for a non-default base
  is true and still not "merged". owed: a guard in `scripts/merge-drain.py` / `merge-policy.sh` that refuses a base that is
  neither the default branch nor an open PR's head (stacked PRs are legitimate).
- A scoped-gate run is bound to the tree it runs in; with an isolated-worktree session, detach that worktree onto the exact
  head first, and verify the checkout before trusting any green.

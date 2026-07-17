# Reacceptance Ledger v2 Continuation Capsule

## Objective

Continue the frozen recovery campaign from live owner evidence until all 105
historical rows and 208 finding discussions have durable terminal
adjudications. Keep Claude, Codex, Gemini, OpenCode, Agy, and every other
healthy peer workstream running independently. Executor names record
provenance, never hierarchy.

This capsule owns only the ledger-v2 and remedy-crosswalk slice extracted from
preservation PR #1163. Repository containment, the dedicated review-gate App,
provider routing, effectors, and owner-repository repairs keep their own
branches and receipts.

## Evidence index

- `scope.json` freezes the 29-session, 11-workflow, 65-PR, five-baseline-open,
  208-finding, three-row privacy, known-side-effect, and cutoff denominators.
- `ledger.json` stores v2 attempts, remedies, coverage, findings, owner
  evidence, derived gates, and normalized refresh history.
- `predicates.md` defines the executable terminal rules.
- `external-actions.md` prevents effect replay.
- `privacy-containment.md` and `incidents.md` retain their owner boundaries.

Raw prompts, personal records, credentials, private paths, and full private
hashes remain in private owner stores.

## Current verified state

Snapshot time: `2026-07-17T05:38:42Z`.

- Structural validation passes for exactly 105 rows and 208 unique finding
  URLs.
- Two complete live GitHub refreshes produced the same normalized evidence
  digest:
  `sha256:e132064474755b362b38247716cc3e731fc09ab336264513af69d923b3692ebe`.
  The continuation gate remains failed because no two distinct fresh owner
  receipts attest those exact refreshes.
- Campaign completion remains false: 105 rows are `repair_required`; review
  debt is P1=28, P2=180, unclassified=0; attempts and coverage are empty.
  Ten live replacement/umbrella PRs are registered as `repair_required`; none
  has been awarded acceptance or historical coverage.
- The five baseline-open IDs are frozen: Domus #304/#305 and Limen
  #1147/#1149/#1151.
- Replacement receipts currently exist as open draft PRs Limen #1162, Domus
  #306/#307, UMA #174, and Public Record #354, but none has complete
  exact-head peer acceptance and deployed-path evidence.
- Bounded recovery extractions now also exist as Limen #1165 (preview-only
  drain/reclaim truth) and #1166 (containment separated from protection).
  Both remain draft and CI is startup-blocked by the account billing/spend
  gate.
- Domus #308 now owns the tracked heartbeat template with dispatch live,
  merge drain disabled, and reclaim apply preview-only. It remains draft and
  has not been applied or loaded on the host.
- Fifty-three live auto-merge requests were canceled (49 Limen, four Domus);
  two consecutive complete inventories returned zero. Runtime
  `LIMEN_MERGE_DRAIN=0` and `LIMEN_RECLAIM_APPLY=0` are held while dispatch
  remains enabled. GitHub still reports `allow_auto_merge=true` on four
  private cohort repositories despite explicit PATCH/readback; branch deletion
  is disabled on all seven. Durable Domus configuration and the account-plan
  gate remain open.
- The original finding threads remain unresolved. Do not mark a finding
  repaired merely because a replacement resembles the requested change.
- Scope-pinned owner-adapter and effect-owner signatures are now enforced by
  the validator. The real scope intentionally leaves those public keys and
  the private content-manifest digest unprovisioned, so named owners or shared
  local receipt files cannot manufacture a release-ready result.

## Authorities and prohibitions

- Work in isolated single-purpose worktrees and preserve the dirty live root.
- Do not edit `tasks.yaml`; TABVLARIVS owns board projection.
- Do not stop, retune, close, or subordinate another keeper's session.
- Do not merge because generic Actions is green. Store the complete
  `limen.pr_review_gate.v1` receipt for the exact head and verify the deployed
  entrypoint.
- Do not replay mail, calendar, storage, media, backup, launchctl, or
  filesystem-move effects.
- Do not rewrite history, delete personal data, purge caches, republish a
  restricted repository, spend, or install account credentials without the
  applicable owner/human authorization.
- Do not duplicate spend. One attempt is registered once and may be referenced
  by many remedies and coverage links.

## First probes

```bash
git fetch --prune origin
git status --short --branch
python3 scripts/reacceptance-ledger.py --check
python3 scripts/reacceptance-ledger.py --require-release-ready
gh pr view 1163 --repo organvm/limen \
  --json state,isDraft,headRefOid,statusCheckRollup,url
```

Then query each remedy's current head, checks, reviews, conversations,
deployment/entrypoint receipt, original finding threads, provider catalog,
cutoff receipt, custody state, and side-effect owner. Prior handoff values are
evidence, never current authority.

## Next bounded work

1. Add accepted remedy and attempt records only after their full owner evidence
   exists.
2. Add one `coverage` entry per historical row and finding discussion that the
   remedy actually repairs, supersedes, reverts, or proves obsolete.
3. Resolve the original discussion only after its coverage evidence passes;
   refresh the ledger and confirm the finding becomes `resolved`.
4. Populate the five owner adapters from their native receipts. Never type a
   passing `completion_gates` status directly.
5. Run two complete refreshes. The final normalized digests must match, two
   distinct fresh owner receipts must bind them, and
   `--require-release-ready` must exit zero after its fresh GitHub comparison.

## Completion and switch predicates

The ledger lane completes only when:

- `python3 scripts/reacceptance-ledger.py --check` exits zero;
- `python3 scripts/reacceptance-ledger.py --require-release-ready` exits zero;
- all 105 rows and 208 findings are terminal;
- every remedy stores complete exact-head review and deployed-path evidence;
- all five derived owner gates pass;
- two ordered live refreshes have the same normalized evidence digest; and
- the current capsule and one-line launch command have a durable remote receipt.

At a billing, plan, App, reviewer-custody, privacy-history, deletion, storage,
mail, provider, host-pressure, or context boundary, file the exact atom in its
owner and continue every reversible lane. Do not manufacture green.

## Copy/paste successor command

From the Limen repository root:

```bash
bash scripts/start-worktree-session.sh \
  --from origin/work/claude-reacceptance-ledger-v2-20260716 \
  --workstream claude-reacceptance \
  --prompt-file docs/reviews/claude-reacceptance-2026-07-16/continuation.md \
  limen claude-reacceptance-ledger-v2-successor
```

If the existing `work/claude-reacceptance-ledger-v2-20260716` worktree is
active and cleanly owned, continue it instead of creating a competing writer.

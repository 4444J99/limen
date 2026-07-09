# GATES — the verification-gate registry

**Registry:** [`institutio/governance/gates.yaml`](../institutio/governance/gates.yaml) ·
**Resolver:** `scripts/verify.py` · **Drift predicate:** `scripts/check-gates.py` ·
**Precedent:** `PREC-2026-07-09-gates-as-data`

## What it is

One declarative registry for every verification gate: the runnable `command`, the `paths`
that implicate it (GitHub Actions glob semantics), the cost `tier`, whether it must
`serialize` behind the machine-wide lock, whether it is `scoped` (runs in the changed-path
push gate) or whole-matrix-only, and its guaranteed `ci_job` mirror if one exists. Plus the
`deploy_triggers` block (a 1:1 mirror of `deploy*.yml` `on.push.paths`) and the `file_sets`
that the whole-matrix syntax passes expand.

Scoped verification and the whole matrix are **two selections over the same data**, not two
scripts: `verify.py --changed` is the scoped push gate (`verify-scoped.sh` is a thin wrapper
kept for muscle memory), and `verify-whole.sh` remains the whole-system predicate while
deriving its file lists from the registry.

## Why it exists

Before 2026-07-09 the knowledge "which gates exist and which paths implicate them" was
hand-copied in eight-plus places (verify scripts, merge-policy regexes plus an awk staleness
guard, five workflow path filters, closeout subsets, charter prose with a literal
"keep in lockstep" instruction). The hand lists drifted **three times in the single day**
the registry was being built. Every drift guard in the old estate existed only because of
the duplication; deleting the duplication let the guards collapse into one predicate.

## How to change things

- **Add a gate** → add one registry entry. Nothing else. `verify.py` selects it, the whole
  matrix can run it, `check-gates.py` verifies its command exists.
- **Change deploy triggers** → edit the workflow *and* the `deploy_triggers` block; check C
  reds until they match exactly (fail-toward-caution: `merge-policy.sh` treats an underivable
  classification as website-sensitive).
- **Never reintroduce a literal copy** — the `ratchets:` block arms a check per converted
  consumer (`verify_scoped_wrapper`, `merge_policy_derives`, `verify_whole_derives`,
  `claude_md_pointer`); a literal list or regex reappearing in a consumer is a red check.

## Deliberate non-consumers

- `.github/workflows/*` — GitHub requires job definitions in-tree; the registry checks
  consistency (checks C–E), it never generates workflows.
- `scripts/closeout-fast.sh` — a receipt-flow, not a gate list.
- `verify-whole.sh`'s `LIMEN_VERIFY_LIVE` tail — env-gated live probes needing tokens/URLs.

## Verification lineage

- Selection equivalence: `scripts/tests/verify-resolver.test.sh` (17 fixtures transcribed
  from the pre-registry rules; permanent regression gate).
- Deploy-classification equivalence: `--deploy-regex` vs the old `DEPLOY_RE` — identical
  over the full tracked corpus plus synthetic edge probes (PR #787).
- Verdict-matrix regression: `scripts/tests/merge-policy.test.sh`, 17/17 including
  "resolver unavailable ⇒ forced sensitive" (PR #792).

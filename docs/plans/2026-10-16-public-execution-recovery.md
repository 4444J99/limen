# Public execution recovery — 2026-10-16

Issue: #2721
PR: #2880

Owner: GITVS publication and execution routing, continuing the existing repository
custody/publication work. This is a recovery checkpoint, not an estate-wide PASS.

## Operating target

Public editions contain reviewed reusable source, tests, synthetic examples and
build/release definitions with public dependencies. Private repositories retain
operational records, credentials, personal/client material and original history.
Private operation uses its existing isolated execution path with exact-revision
evidence. Standard public GitHub Actions must not depend on private Actions
admission, private reusable workflows, or undisclosed private checkout contents.

## Delivered and proposed source work

- Domus Genoma public edition: PR 1 merged at
  `829941a70411fa655b2b1f29bd03796ffd0723de`.
  [Main run](https://github.com/4444J99/domus-genoma/actions/runs/38973383116)
  passed the admitted-file boundary and four zsh syntax checks. Its private
  installation is a separate product and is not certified by this result.
- Central deterministic Actions lane: require live public carrier visibility
  during discovery, capacity checks and preflight; retain public target admission.
  This patch does not certify every custom dispatcher or another provider family.
- Whole source verification: honor the existing `LIMEN_VERIFY_LIVE=0` contract;
  explicit live verification retains its failure exit code and independent owner.
- Profile source: preserve metric definitions and distinguish successful empty
  observations from failed/incomplete observations after ownership consolidation.
- Public readiness source tests: use the existing public accepted snapshot with
  its pinned byte digest when historical Git objects are absent. Live validation
  still fetches the exact accepted revision and verifies its receipt and digest.

## Remaining owned work and acceptance

| Owner / surface | Evidence and concrete next action | Acceptance |
| --- | --- | --- |
| Existing CI relay owner | Reconcile its actual carrier visibility and target registry. Reuse the reviewed public deterministic worker where its predicate contract fits; otherwise extract only reviewed public implementation through the existing split protocol. | An admitted public carrier and public target execute the exact approved predicate with verifiable result custody. |
| Existing operations owner | The public caller still references a private reusable release workflow. Extract the generic scheduler modules and migrations with synthetic manifest/config fixtures; retain production manifest, provider configuration, boundary allowlist and release/reconciliation/custody scripts in private ownership. Never port the private contract-input artifact containing real provider config into public CI. | Public core tests pass, then native owner execution binds pinned public core plus private configuration. Preserve accepted-main ancestry, exact source identity, predecessor/binding/database checks and explicit apply authorization; prove runner availability with private-safe receipts before retiring the existing carrier. |
| Profile owner | Apply the collector repair, rerun the actual profile build, and independently read the generated accepted profile revision. Retry-only checkout PRs do not correct missing facts. | Complete observations yield the documented metrics; partial/unavailable data cannot render as a valid total. |
| Vulnpulse dependency owner, PR 16 | Main requests Vitest 4 while its lock still describes Vitest 2; current install crashes. Existing PR 16 also has a Wrangler/workers-types peer mismatch. Reconcile package constraints and regenerate the lock in the existing repair scope, then use `npm ci`. | Strict clean install, lint, typecheck, tests and dry-run build all pass on the resulting exact tree. |
| Styx dependency owners, PRs 1030 and 1006 | Current main already passed the full source pipeline at `0d730b84b75f946d960ec89a35e971c4c88345d2`. PR 1030 fails strict installation because pako is missing from its lock; PR 1006 has no current-head CI evidence. Preserve the wider runtime repair ownership. | Keep passing main; dependency branches require a complete consistent lock, strict clean install and all existing project gates on their accepted heads. |
| Gitvs publication / custody owner | For every remaining private code candidate, establish exact extraction manifest, content/dependency review, independent public history and a meaningful public predicate. Keep operational-only and archived repositories classified explicitly. | No unreviewed visibility flips; public editions actually pass, private execution has its own evidence, and the full repository denominator remains visible. |

No branch protections, review requirements, credentials, paid services, production
deployments or existing private visibility settings are changed by this recovery.
Unknown, missing, cancelled and skipped evidence must not become passing results.
A latest-run sample is not a complete workflow or required-check audit.


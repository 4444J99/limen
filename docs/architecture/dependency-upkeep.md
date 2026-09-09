# Dependency upkeep through the existing governor

Owner: dependency acceptance pilot for `organvm-vii-kerygma/portfolio` and
`organvm-iii-ergon/public-record-data-scrapper`. Source routing is implemented;
trusted installation, live review dispatch and automatic acceptance are not
established. Automatic acceptance still requires source implementation as well
as provisioning: there is no pilot dependency merge transaction or transition
from an approved review to that transaction. The tracked
`institutio/github/dependency-trust.json` deliberately
has `installed: false` until the evidence producers have landed and their exact
trusted source and reviewer identities have been audited.

The existing merge drain owns the cadence, bounded scan and review limit. There
is no additional scheduler. Weekly compatible Dependabot groups remain the
discovery mechanism; majors, behavior-sensitive updates and focused security
updates retain individual review. An explicit lifecycle hold protects active
human, preservation, blocked and superseded PRs even after a batch observation.

## Evidence and routing

The repositories produce `organvm.dependency-evidence.v1` artifacts named
`dependency-evidence-RUN_ID-RUN_ATTEMPT`. Each archive contains exactly one
`dependency-evidence.json`: base/head/tested revisions, dependency revision equal
to the tested merge, workflow identity,
lockfile SHA256 values, graph changes and baseline-to-candidate advisory results.
Frozen installs, formatting, compiler checks, tests and builds have independent
job/step evidence; skipped or advisory compatibility is insufficient.

`_dependency_acceptance.py` reads provider APIs and bounded archives as data.
It runs no candidate scripts. It verifies:

- Canonical repository ID, same-repository Dependabot identity, complete changed
  file inventory and modification-only manifest/lockfile changes.
- Exact current base B, head H and GitHub test merge M with ordered parents B/H.
- Reviewed immutable workflow/helper blob pins at B, H and M, every required
  workflow's current completed attempt, successful required steps, and checkout
  log evidence of M for the independently executed jobs.
- The exact run/attempt artifact, GitHub artifact digest, bounded regular ZIP
  member, lockfile Git blob identity and SHA256, and independently reconstructed
  graph changes.
- Explicit trusted manifest paths, including existing workspaces, with complete
  inventory equality from base/head/tested lockfiles and regular-file checks.
- Provider run start/update timestamps within the configured age limit (at most
  24 hours), rechecked before review. The deployed host must keep its UTC clock
  synchronized; artifact timestamps cannot refresh an old audit.
- Complete advisory evidence with no newly introduced or remaining high/critical
  findings and no producer-declared policy exceptions.
- Fresh B/H/M and workflow attempt readback after evidence collection.

These checks admit delegated review only. An Actions App ID or matching check
name alone cannot satisfy them. The final read does not claim an atomic merge
fence. The consumer always returns `automatic_acceptance: false`.

`_dependency_upkeep.py` requests the policy-configured independent bot review
after checking its live numeric identity and revalidating evidence. Existing
requested reviews and completed exact-head reviews prevent duplicate requests.
An unresolved latest decisive `CHANGES_REQUESTED` becomes an exception; a later
comment cannot erase it. Transport ambiguity produces an unconfirmed exception
and the next bounded beat reads live custody before another request. A review
request or comment is never an approval, merge receipt or completed acceptance.

The current completed-review state is a routing result, not a completed
maintenance result. `request_review()` returns `reviewed` for a completed
exact-head comment or approval; the drain does not merge either result. Even a
valid exact-head `APPROVED` review currently stops here. Installing reviewer
identities, credentials or repository settings cannot supply the missing code.

The drain's `DEPS-REVIEW` and `DEPS-PENDING` rows remain quiet. Known trusted
workflows still running wait for a later beat without review or merge effects.
Completed compatibility failures become exceptions. `DEPS-EXCEPTION` rows and review
request failures use the existing channel-aware notification broker with stable
repository/PR/head/reason identities. The registered event includes macOS and
ntfy channels; live remote delivery still requires a deployed broker and channel
receipt. Source tests do not establish background execution or notification
delivery. Existing `--dry-run` emits no review or notification effects.

Both the drain's mutation entrypoint and standalone `merge-policy.sh` hold pilot
dependency updates. They cannot fall back to the generic green-check merge
route, including an old portfolio alias, case variations or queued state.

## Trust installation and subsequent automatic acceptance

Populate the existing trust file through a reviewed change after accepted-main
producer verification. Its per-repository contract is:

| Field | Required evidence |
| --- | --- |
| `repository_id`, `base_ref`, `dependabot_actor_id` | Live canonical GitHub identities; main target |
| `workflow_path` | Artifact-producing workflow path |
| `trusted_files` | Exact Git blob OIDs for every required workflow and `scripts/dependency-evidence.mjs`, plus any imported evidence helper |
| `required_workflows` | Distinct paths; `jobs` maps actual job names to successful required step names; `checkout_jobs` names jobs whose checkout logs must prove M |
| `lockfiles` | Complete authoritative package-lock paths |
| `manifests` | Complete explicit root/workspace manifest paths matching each B/H/M lock inventory; no candidate-created paths |
| `max_evidence_age_seconds` | Positive maximum audit/run age, no more than 86,400 seconds; provider times and trusted-host UTC clock |
| `reviewer` | Independently configured bot login and numeric ID, not the candidate author |

The policy is deployment-owned configuration, never accepted from a PR artifact
or candidate tree. A policy update requires reviewed source pins and fresh
counterexamples; setting `installed: true` alone supplies neither credentials
nor evidence. A missing reviewer, unavailable audit, baseline advisory debt,
workflow drift, incompatible runtime, unexpected graph or failed compatibility
remains an exception with an explicit cause.

UCC's existing ruleset `12671627` was observed disabled with `strict: false`.
Portfolio's visible ruleset list was empty. Both classic branch-protection reads
returned `403 Resource not accessible by integration`; the connected operations
expose no administration writes. Repository ownership permission does not make
that capability available. UCC's staged settings planner preserves unrelated
controls and requires actual `gate` and `validate-dependencies` jobs. Its Actions
publisher binding is ordinary gate hardening, not proof of workflow identity.

After producer source acceptance, the owning administration channel applies the
reviewed compatibility settings and verifies complete readback and failing-check
canaries. This improves the gates; it does not activate dependency acceptance.

### Remaining implementation owner and boundary

The dependency-upkeep workstream in Limen, introduced by PR #2585, owns the
missing pilot acceptance code. Its existing extension points are
`_dependency_upkeep.request_review()`, the `DEPS-REVIEW` branch in
`merge-drain.main()`, and the dependency holds in `merge-drain.merge()` and
`submit_one()`. The standalone `merge-policy.sh` dependency hold must continue
to prevent a generic fallback until an accepted transaction owns the effect.

The accepted relay transaction in `_relay_merge.py` is a reference for that
implementation, not an installed pilot adapter. Its repository identity, API
scope, protection readback and trusted evaluator are hard-bound to
`4444J99/organvm-ci-relay` (ID `1350979676`). Relay issue #3 and relay PR #30 own
that separate trust root and deployment. Supplying their credentials or passing
their canaries cannot enable merging in portfolio or UCC.

The remaining pilot implementation must connect a fresh, independent exact-head
`APPROVED` review to a synchronous transaction over the current B/H/M tuple and
reviewed producer evidence. Comments, pending/dismissed reviews, or outstanding
changes-requested decisions cannot authorize it. The transaction must verify
the target repository and dedicated App identity, read back strict independently
enforced controls, publish its one-shot authorization only on M, recheck the
tuple and review before the exact-head merge, and retain positive landing and
cleanup/reconciliation receipts. Governor write credentials remain isolated
from candidate execution and from the read-only evidence consumer.

The protection contract must also account for ordinary project changes before
installation. A required governor check and exclusive App update rule on `main`
apply to **all** pull requests targeting that branch. Copying the relay rules
into a pilot while implementing only dependency acceptance would strand
ordinary PRs: their current generic route neither produces that required check
nor supplies the isolated App transaction. A reviewed, independently tested
route for those ordinary PRs, or an equally enforceable alternative, is therefore
an implementation prerequisite to any exclusive App control on the pilots.

Until these code and enforcement contracts are accepted, keep pilot automatic
acceptance disabled and preserve the existing review-only/no-fallback behavior.
The subsequent activation boundary is actual private credential delivery,
trusted deployment, complete settings readback, and protected positive/negative
GitHub canaries for each pilot. Source tests and an `installed` flag cannot
replace those live receipts. Missing implementation and missing provisioning
remain distinct; neither is a request to repeat standing user authorization.

## Verification

The scoped `dependency-acceptance-test` gate covers the consumer, upkeep adapter,
drain integration, policy, trust configuration and documentation. Its tests use
fake API data and fake notification/review effects; live activation is a separate
predicate. `merge-policy-test` and `merge-queue-contract-test` continue covering
the existing mutation rails.

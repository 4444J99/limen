# Career portal continuation

Objective: operate the existing career/network organism as a portal inside
Limen, complete the externally useful first pass, and leave every code,
relationship, application, distribution, and contribution leaf with a durable
owner receipt.

Current evidence and durable owners:

- [application-pipeline PR #83](https://github.com/organvm/application-pipeline/pull/83)
  owns submission-boundary hardening and its exact-head CI receipt.
- [UMA PR #174](https://github.com/organvm/universal-mail--automation/pull/174)
  merged the receipt-bound one-shot Gmail send contract.
- [application-pipeline PR #93](https://github.com/organvm/application-pipeline/pull/93)
  owns the 2026-07-28 opportunity/CRM/network pass and its regression receipt.
- [corpvs PR #542](https://github.com/organvm/organvm-corpvs-testamentvm/pull/542)
  owns registry repair, canonical dependency validation, and the hydrated
  BIFRONS import receipt.
- [Limen PR #1554](https://github.com/organvm/limen/pull/1554) owns regeneration
  and freshness of the generated `organs/observation/bifrons/PORTAL.md` view
  after the live store has been hydrated.
- [AuthPlane/python-sdk issue #20](https://github.com/AuthPlane/python-sdk/issues/20)
  is the first upstream relationship receipt.
- [Limen PR #1605](https://github.com/organvm/limen/pull/1605) owns this
  portal contract, its scoped verification, exact-head CI, and review record.
- TABVLARIVS task `CAREER-CONTRIB-CUSTODY-20260728`
  (`git:organvm/limen:tasks.yaml#CAREER-CONTRIB-CUSTODY-20260728`) owns the 17
  visible required-artifact drift entries; this PR preserves their visibility
  but does not absorb their restoration or re-homing.

Authorities: replies, eligible applications, the restart LinkedIn post, and the
promised AuthPlane issue are authorized subject to their existing provider and
action-time gates.

Prohibitions: no new service or repository, no LaunchAgent, no persistent global
submit arm, no LinkedIn API claim, no paid application service, no suspicious
site interaction, no credential disclosure, and no destructive evidence
deletion.

Preflight probes:

```bash
python organs/governance/validate-seed.py organs/representation/seed.yaml --strict-graph
python -c 'import yaml; yaml.safe_load(open("organs/representation/career-portal.yaml"))'
python organs/representation/validate-representation.py --fleet
python scripts/bifrons-organ.py --check
```

These are preflight-only. Closeout requires the owning receipts above plus the
following canonical gates; a probe result in a local shell is not a durable
receipt by itself.

| Predicate | Canonical closeout gate | Durable owner |
|---|---|---|
| representation seed and portal contract | the four preflight commands above, `git diff --check`, and `scripts/verify-scoped.sh` | Limen PR #1605 |
| BIFRONS store/engine liveness and hydrated import | `python scripts/bifrons-organ.py --doctor` and one `organvm portal import-stars` against the live engine/alchemia environment | corpvs PR #542 and the private BIFRONS store |
| generated BIFRONS view freshness | regenerate from the hydrated live store, then run `python scripts/bifrons-organ.py --check` | Limen PR #1554 |
| contribution mirror remains current | `python scripts/contributions-organ.py --check` | Limen PR #1605 and the SPECVLVM ledger |
| application policy regressions | scoped tests named by the changed application-pipeline paths, followed by exact-head CI | application-pipeline PR #83 |
| live opportunity/CRM/network state | a second `opportunity_sync` and network ingest are no-ops | application-pipeline PR #93 |
| runtime provider actions | provider Sent/application/post/upstream receipts plus matching owner transitions | UMA PR #174, application-pipeline PR #93, and the linked provider receipt |
| exact-head integration | the unchanged head SHA has green required checks and peer review before normal queue merge | each owning PR |

Executable campaign predicates:

- the representation seed and portal YAML parse and validate;
- the owner graph names only existing engines/organs and explicitly denies a
  LinkedIn API adapter;
- application-pipeline and UMA exact heads pass scoped tests and CI before
  normal queue merge;
- submitted applications have provider confirmation and current pipeline state;
- all purple Mail flag-5 threads have a terminal or waiting receipt;
- every public send has provider custody proof;
- contribution ingress uses BIFRONS/SPECVLVM rather than a replacement mirror.

Ownership and switching: mutations stay in their isolated worktrees and land by
reviewed PR. If the runway ends before all external gates clear, first push this
capsule, then launch an isolated successor through the workstream admission
path. Run the following from this capsule's clean worktree; it derives the
repository root, verifies the expected branch and exact remote-preserved head,
prints that evidence, and passes the immutable head to the launcher:

```bash
repo_root="$(git rev-parse --show-toplevel)" &&
test "$(git -C "$repo_root" branch --show-current)" = "work/career-portal-20260728" &&
test -z "$(git -C "$repo_root" status --porcelain)" &&
git -C "$repo_root" fetch origin work/career-portal-20260728 &&
expected_head="$(git -C "$repo_root" rev-parse origin/work/career-portal-20260728)" &&
test "$(git -C "$repo_root" rev-parse HEAD)" = "$expected_head" &&
printf 'verified branch=%s exact_head=%s\n' "work/career-portal-20260728" "$expected_head" &&
"$repo_root/scripts/start-worktree-session.sh" --autonomous --agent auto --conduct \
  --from "$expected_head" --runway 1d --workstream career-portal \
  --prompt 'Read docs/continuations/career-portal-20260728/README.md and continue the career portal to its executable fixed point.' \
  limen career-portal-20260728-s2
```

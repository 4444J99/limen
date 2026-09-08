# Verification artifacts

These recovered artifacts preserve the earlier remediation design and its tests.
They have three distinct evidence scopes:

| Artifact | What it can establish |
|---|---|
| `tests/e2e/verify_ecosystem_prs.py` Git fixtures | Real Git rebase and merge behavior in temporary repositories |
| Both `test_pr_remediation_pipeline.py` suites | Internal consistency of synthetic remediation models |
| Production module tests and `scripts/verify-scoped.sh` | The declared behavior of the candidate implementation at an exact head |

The intended coverage remains Git conflict handling, implicated test execution,
exact-head PR integration, independently verified branch/worktree custody, and
protection of other sessions. A model example does not satisfy these operational
requirements. Real integration follows the PR-only, no-force-push policy in AGENTS.md;
no command in a historical simulation authorizes an external effect.

Preservation additionally needs a named repository/ref or process identity, a
before observation, an after observation, and a durable owner receipt. An absent
path, an empty branch list, or a process lookup error is unmeasured evidence.

Run local fixture checks with the repository's hermetic pytest wrapper. The owning
scoped resolver selects production gates. Live receipts are produced only by their
registered owners, with the required authority and bounded resource admission.

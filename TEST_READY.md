# Verification scope and current evidence

The August 27 test counts were produced by local simulations. They do not certify
PR landing, remote branch custody, protected personal material, or live processes.
The former `READY (100% PASS)` certification is withdrawn as operational evidence.
The historical result remains in `docs/receipts/e2e_verification_report.json`, labelled
as model-only evidence with its original reported counts preserved.

`tests/e2e/verify_ecosystem_prs.py` now checks rebase behavior using real Git objects
inside disposable clones and rejects nonexistent commits and unresolved conflicts.
Its remaining model checks have the explicit `local_git_fixtures_and_synthetic_models`
scope. `--live` returns unavailable until owner-qualified before/after preservation
observations exist; missing evidence cannot produce a live pass.

Both copies of `test_pr_remediation_pipeline.py` contain synthetic stand-in engines.
Their passing counts apply only to those models. Production acceptance belongs to
the tests that import production code, the scoped predicate on an exact head, and
repository-qualified remote receipts.

The current reconciliation owner is
[the finish-line continuation](docs/continuations/git-finishline-20260908/README.md).

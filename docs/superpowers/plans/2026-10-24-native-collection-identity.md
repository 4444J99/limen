# Native collection identity implementation plan

> **For agentic workers:** Use superpowers:executing-plans. Execute the authorized scope without another design approval.

**Goal:** Prevent configured source-account label drift and record truthful local CLI execution evidence.

**Architecture:** Optional private account binding checks run before database access. Existing historical observations remain immutable. Collect/export can write a bounded private receipt containing actual local invocation facts, with supplied identity and window evidence explicitly identified as caller attestations.

**Tech stack:** Existing Python standard library, SQLite, argparse and hermetic pytest wrapper.

**Spec:** Current session instruction: strict source/surface/account/fresh-principal binding; local self-report receipts; no aliases, historical reconciliation, checkpoint changes, provider calls, timers or services.

## Global constraints

- Preserve existing unbound collection, observation hashes, imports and checkpoint behavior.
- Require both binding and profile observation when either is supplied; compare a profile no more than 900 seconds old against actual invocation time.
- Bind the source, provider, surface, account reference and SHA256 of `profile_provider + NUL + principal_id`.
- Never print private payloads, identifiers, binding values or paths in public success/error output.
- Receipt presence alone is not independent proof of authenticated or native scheduled execution.
- Only focused hermetic tests; root owns broader integration gates and publication.

## Review focus

- Account, provider/surface or principal mismatch must fail before database creation or mutation.
- Missing, stale, future or malformed profile evidence must fail closed.
- Same message IDs from distinct unbound accounts must remain distinct history.
- Receipt reuse/path collision and failed export must not overwrite prior evidence or claim success.
- Receipts must bind the bytes actually executed/exported without exposing raw principals or bodies.

## Task 1: Identity binding and CLI receipts

- [x] Add real CLI regressions in `cli/tests/test_schedule_collection_integration.py`; observe failures on the missing flags/behavior.
- [x] Add strict validation to `scripts/_schedule_evidence.py` and wire it before opening `EvidenceStore` in `scripts/schedule-collect.py`.
- [x] Add optional collect/export receipt flags, immutable invocation reservation and atomic terminal update; retain caller attestation labels.
- [x] Document exact private schemas, freshness, flags and claim limits in `docs/operations/schedule-collection.md`.
- [x] Run `bash scripts/run-pytest-hermetic.sh scripts/tests/test_schedule_evidence.py cli/tests/test_schedule_collection_integration.py -q`.
- [x] Review the exact diff, commit, and return SHA plus evidence to the root for integration.

## Execution record

- Baseline is reviewed commit `8bd55059c1205eb2ffb65a03e38cac89b94c662f` in a new isolated sibling worktree.
- Ruling: preserve old account labels without alias collapse because historical authenticated principal evidence is absent.
- Ruling: checkpoint changes are excluded because the newest natural run repaired the observed lag and preserved incomplete pagination correctly.

- Verification: baseline 133 focused tests passed; 25 added cases cover strict identity, receipt evidence, empty arguments, collision protection and readback/durability failures. Final focused run: 158 passed in 4.99 seconds. Ruff and git diff --check passed.
- Independent review: native observer reproduced receipt/SQLite sidecar collisions, receipt-lock/database collision and terminal receipt sync ambiguity. Each was fixed with a failing-then-passing regression; operation_outcome now explicitly precedes receipt publication.
- Root review: exact input bytes are hashed from the parsed buffer; exported bytes must match intended serialization or report uncertain commit state. Both findings have failing-then-passing regression coverage.

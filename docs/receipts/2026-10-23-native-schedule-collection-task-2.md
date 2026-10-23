# Task 2 implementation report

Local implementation commit: `d02c424` (`feat: collect native schedule evidence through existing audit estate`).
Base: `0695cc86876d5d83cf81352c31893e35ccac5f29`, preserving the normal merge of peer head
`2ba8109995a9b7962ebd0a604e5f6677141e0396` and the reviewed Task 1 core. No core changes.

## Delivered scope

- Extended the peer's **one** schedules registry, checker, sensor reader dispatch and existing
  schedules-test gate. No second registry, timer, sensor, queue, service, dependency or authority.
- Added operation-specific dated launch/input/retrieval provenance, `audit_only: true`, #3177
  ownership, explicit owner/next-action coverage gaps, Cowork/Grok Bot separation, and opaque
  public native inventory. Replaced five historical ChatGPT configuration rows with the supplied
  dated 15-enabled-task native inventory projection. Public responsibility summaries disclose no
  private task IDs, titles or prompts. OPS manifest projections and peer minute-offset ratchet remain.
- Added offline `schedule-collect.py` commands: collect, import, export, assess, checkpoint. Batch
  normalization is atomic; errors/status contain no source bodies. Input is bounded to 16 MiB and
  collection to 1,000 records. Generic artifact account/owner scope must match CLI scope. Private
  exports use expected revision digests, private temp files and atomic replacement; an export cannot
  replace its live database. Export/assess/checkpoint reject missing databases, and a missing expected
  export does not leave an empty sentinel. Collect/import can initialize a store.
- Added bounded native-snapshot reader through the canonical EvidenceStore semantic validator in
  an ephemeral private directory. Reports history separately from latest unique task/run identity,
  provider-dated execution, complete/partial collection, attribution, exact current assessments and
  assessment history. Repeated polling does not inflate observations; a newly observed unknown
  attempt supersedes older completion. No native IDs/references enter public counts. Snapshot account
  and historical coverage remains partial and cannot produce a whole-plane full verdict.
- Corrected comments-as-delivery/full, remote read failure-as-absence, public board absence-as-zero
  Jules usage, Claude configuration-as-execution, malformed GitHub run payload-as-zero, and a full
  100-run page-as-complete paths. Preserved explicit disabled-workflow and configuration parity checks.
- Capacity reports evidenced allowance, published ceiling, local policy, measured usage and usable
  remainder separately. Same-account/window/unit fresh complete usage and fresh evidenced downstream
  review/delivery are required for a remainder. Public caps and prior `entitlement: verified` labels
  alone cannot supply account entitlement. The OPS 2,000-attempt cap is classified local policy.
- Added runbook with existing hourly Intake only, exact reviewed deployment pin, preserved identity,
  original recovery scope/prompt/cadence, fixed current windows/overlap, bounded historical restoration,
  incomplete-page continuation, durable snapshot/assessment/history union, revision-safe durable
  handoff, private digest-keyed result body retention and append-preserved occurrence associations.
  Gmail canonical references replace raw MIME/header archival. Source, interactive, scheduled,
  acceptance and external delivery gates are separate.

## Tests first and observed failures

No actual private payloads or IDs were inspected or copied. All tests use synthetic source data.

Initial command:

```bash
bash scripts/run-pytest-hermetic.sh scripts/tests/test_schedule_registry.py -q
```

Observed **12 failed, 1 passed** before production edits: missing CLI and native reader/capacity/
authority interfaces, missing audit schema/flags, comments returning full, remote bookend failure
returning zero, aggregate board absence returning zero, and Claude enabled flags treated as execution.
The existing atomic-error case initially passed because the CLI was absent; it was retained and
subsequently exercised against the implemented CLI, including zero durable observations after error.

The first combined batch after implementation exposed **two existing peer assertions** encoding
superseded semantics (comments imply full; enabled Claude triggers imply execution). Updated those
two assertions and added an explicit separate configuration measurement assertion. No parity or
launch-safety test was weakened.

Additional red/green regressions:

- **2 failed, 19 passed**: malformed GitHub payload falsely returned zero; full-size 100-run page
  lacked partial coverage. Fixed both reader paths; partial coverage also prevents full verdicts.
- **2 failed, 21 passed**: later unknown attempt retained earlier completion; local policy cap was
  labeled published ceiling. Fixed current-readback ordering and explicit quota classification.
- **1 failed, 23 passed**: export could replace its own live SQLite file. Added same-path/inode guard.
- **4 failed, 24 passed** after root review: missing databases were created by export/assess/checkpoint,
  and rejected expected-missing export left a sentinel. Fixed before final batch.

Two intermediate fixture errors were corrected without production changes: pytest's parent directory
was already mode 0700 (the public-target test now creates an explicit 0755 directory), and the
synthetic Gmail fixture lacked required immutable internalDate metadata.

## Final exact verification commands and results

All commands ran in the dedicated isolated checkout. The mandatory hermetic wrapper was used.

```bash
bash scripts/run-pytest-hermetic.sh cli/tests/test_schedules_registry.py scripts/tests/test_schedule_registry.py scripts/tests/test_schedule_evidence.py -q
```

**Exit 0: 136 passed in 4.47s** (25 existing registry tests, 28 new integration tests, 83 core tests).
CLI smoke coverage includes all commands, ChatGPT/Grok/generic adapter routes, native offline snapshot
reporting, privacy/error output, exact assessment/delivery order and revision/missing-file protection.

```bash
python3 -m ruff check scripts/_schedules.py scripts/_schedule_reporting.py scripts/schedule-collect.py scripts/check-schedules.py scripts/schedule-utilization.py scripts/tests/test_schedule_registry.py cli/tests/test_schedules_registry.py
```

**Exit 0: All checks passed.**

```bash
python3 -m ruff format --check scripts/_schedules.py scripts/_schedule_reporting.py scripts/schedule-collect.py scripts/check-schedules.py scripts/schedule-utilization.py scripts/tests/test_schedule_registry.py cli/tests/test_schedules_registry.py
```

**Exit 0: 7 files already formatted.**

```bash
python3 scripts/check-schedules.py --json
```

**Exit 0:** `schema_valid=true`, `inventory_valid=true`, `audit_only=true`,
`operational_readiness="unverified"`, no failures. Advisories: no local sibling clones for OPS
(8 projected rows) or ops-witness (3 rows), so sibling parity is unverified here, not observed drift.

```bash
git diff --check
```

**Exit 0** after removing an extra EOF blank line from the registry. No source behavior changed
after the final green focused batch; the EOF-only fix preceded commit.

No broad suite, provider calls, browser work, credential lookup, launches, native task mutation,
GitHub writes/comments/PRs or publication ran in this lane. Root owns one final reviewed
`verify-scoped.sh` invocation against the pinned peer base; edits to the two old CLI assertions
legitimately implicate pytest-cli. The inherited live positioning-foundry gate failure remains a
root-owned named observation if it persists; this local offline registry pass does not resolve or
weaken it.

## Interfaces and limits

- Core API remains unchanged. The CLI additionally reuses core `_private_path` to enforce identical
  export-path protections; the reporting helper uses only EvidenceStore import/export for semantic
  validation. `_schedules.load_registry(root, registry_path=None)` preserves its original signature.
  Utilization `evaluate` gains optional `registry_path`/`snapshot_path`; legacy call sites still work.
- The supplied actual replay counts are provenance, not direct reads by this lane: 15 ChatGPT full
  artifacts (10 correlated, 5 unresolved) and a bounded sample of 20 Grok partial unresolved emails.
  Root performed their private replay, deduplication and body-archive persistence/readback.
- Native snapshot coverage is deliberately conservative. Complete account run history, entitlement,
  usage, downstream capacity and other-provider account access are not established. There is no
  launch/admission recommendation.
- Checkpoint observation IDs must already exist, but CLI cannot independently verify connector
  pagination or remote archive durability. The existing native collector must bind all pages/window,
  durable union/archive readback and terminal page status before supplying `--complete`.
- Expected-sha256 supplies local revision checking; remote durable storage requires its own
  revision-conditional update and re-read/import on conflicts. There is no remote CAS service here.
- Native schedule amendment, exact deployed pin, natural scheduled execution, owner acceptance and
  external delivery remain separate root-owned gates. Source schema validity is not activation.

Ready for independent review and root integration. Implementation report is committed separately
so it can reference the exact implementation commit above without a self-referential commit hash.

## Publication note after final review

The implementation and report commits `d02c424` / `9178bc6` above are local source-history evidence.
The final publication may be one reviewed-tree-equivalent commit on the pinned peer parent rather
than those local commits. Root must prove the published tree equals the reviewed local tree and pin
the actual published SHA in the native deployment receipt. Historical test command paths above
record their original execution; current integration tests live at
`cli/tests/test_schedule_collection_integration.py`.

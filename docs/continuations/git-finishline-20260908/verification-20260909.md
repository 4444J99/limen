# Recovery verification repair — September 9

Owner: [Limen #2576](https://github.com/4444J99/limen/pull/2576), stacked on
the existing [#2573 recovery owner](https://github.com/4444J99/limen/pull/2573).
Source commit: `1c6350d580fefffb0dc2a7f86060f9ea303720a9`; source tree:
`dfce9ce90e63c0866199afdf742c2a8561b8d701`. This receipt records partial
verification and preserves the merge hold. Machine-readable results and failing
test families are in `verification-20260909.json`.

## Repaired counterexamples

The prior hosted CLI run reported 38 failures and 7,393 passing cases. Its new
autouse fixture created `limen.env` inside every test's `tmp_path`, contaminating
filesystem retention, custody and no-side-effect assertions. The file's default
permissions also violated the production shell bootstrap's mode-0600 check.

The fixture now keeps its empty dispatch environment in a separate, private
fixture directory with mode 0600. The shell bootstrap receives an explicitly
selected absent conduct cache, so it cannot reload the operator's default cache
or mistake an empty file for complete authenticated credentials. The temporary
keeper and pre-network broker transport guard remain in force. The regression
checks an untouched test directory, the private mode, the explicit absent cache,
and local keeper selection after dispatch reload.

Recovery also contained two all-leaf digest checks. The earlier duplicate bypassed
the later redacted validator, raised inconsistent count errors and leaked a raw
`TypeError` for unhashable content. Removing that duplicate preserves the later
complete count/digest check and its safe exception handling. Both test families
now assert the same precise public denial codes. Independent source review found
no weakening of the authority or content boundary.

## Current-main and unique-source reconciliation

At governor `7c47dd6a950584a0f021d531b6e0b43080bda295`, recovery's `dispatch.py`
and archive-recovery regression file were byte-identical to that owner. They are
preserved shared implementation, not two independently completed tasks.

Recovery's repository-specific census generation validation, collector generation
fields, local-custody accounting, notification ownership, serving-boundary
security headers and source-reconciliation work remain distinct. No source was
deleted or declared superseded by resemblance.

The sole observed merge conflict with main
`1a5c4cae6676b1b63cc3c4ff09c8ba305632c5d0` was the recalibration launch prompts.
The recovery R05/R10/resume sections were reconciled with accepted #2579 without
altering W07 or other authority content. The resulting prompt blob exactly equals
current main (`ae278caa36ad7dabbc98937fec40ddde0e3e591f`). A non-mutating
`git merge-tree --write-tree HEAD origin/main` then exited 0. This proves conflict
resolution against that observed generation, not accepted-main integration.

## Actual verification

- Isolation/inventory/notification selection: 123 passed.
- Earlier 251-case filesystem/inventory/custody selection: 247 initially passed;
  the four remaining cases passed after selecting the installed environment for
  subprocess Python and the absent shell-cache fixture. No aggregate full-suite
  pass is inferred from these overlapping selections.
- Existing completion counterexamples: 17 passed. Source-reconciliation tests:
  six passed. These are synthetic validator checks, not campaign delivery.
- Four implicated prompt-documentation gates passed.
- `bash scripts/verify-scoped.sh --integration --base
  30c200b5982a56210b17f518010b1f15d580b9d5`: all 12 cheap gates passed;
  genuine heavy admission succeeded; full CLI executed with 7,342 passed,
  88 failed and five skipped in 426.58 seconds. The command exited 1 and also
  reported `gate-command-lingering-process-group`. The heavy lease was released.
  The API shard initially did not execute after that failure; its separately
  admitted registered follow-up subsequently passed all 51 tests in a 1.35-second
  gate. That heavy lease was also released.
- Published-source CI run 34351577127: Python lint, format, type checks, compile,
  dependency audit, shell checks and runtime-adapter steps passed. Worker and web
  npm audits failed before their build/runtime steps; those later steps were
  skipped. Source PR Gate run 34351577073 was still executing at inspection.

The known fixture/inventory regressions are absent from the new full-suite failure
list. Independent diagnosis accounts for all 88 failures:

| Cases | Cause and disposition |
| --- | --- |
| 84 | Process observation runtime: nested `ps` exits 1 with `fatal library error, lookup self`; a probe reports PID 5 while `/proc/self` resolves to 138202 and `NSpid` contains both. Required descendant census and identity validation fail closed. These integrations need a coherent process namespace. |
| 1 | GPG agent startup exits 2 before vault code (`No agent running`). The real round trip needs a functioning agent runtime. |
| 1 | Jules stage exceeded its 10-second deadline in the eight-worker suite; the single focused rerun passed. Contention is an inference, not a certified full-suite result. |
| 2 | Actual WAL scanner regression, repaired and verified as described below. |

A read-only SQLite connection changes WAL ctime when its first schema read
initializes metadata. The scanner incorrectly interpreted its own initialization
as a writer mutation and rejected valid WAL-only prompt appends. It now discards
that initialization transaction before binding the actual read snapshot. Bounded
SHA-256 reads before and after initialization prove identical WAL bytes; database
and WAL identity, size, mtime, database ctime and sidecar custody remain checked.
The actual scan still compares the complete signature, including WAL ctime.

All 281 prompt source tests passed in 4.39 seconds on the final correction. Six
new counterexamples reject database replacement, changed metadata, unsafe
sidecars, ctime changes during the actual snapshot, equal-size WAL byte rewrites
with restored mtime, and WAL content above the bounded read ceiling. Two separate
agents independently reviewed the correction and accepted its custody/content
boundaries. The JSON receipt binds this result to the source and test SHA-256
values. All 12 final implicated cheap gates, including the receipt documentation
checks, passed. The original failed full-suite receipt remains unchanged, and the full
suite was not repeated after this targeted repair.

## Remaining acceptance, with existing owners

#2576 owns the recorded process-observation and GPG integration predicates on a
functioning runtime, plus its exact-source hosted result. The API follow-up and
repaired WAL shard now have passing receipts. Start with the remaining failed
module/case inventory in the JSON receipt; rerun only the implicated failed shard
after its runtime capability is restored. Preserve unchanged
green evidence. No retry of the unchanged full local suite is justified.

#2561 retains the distinct dependency override owner; web and Worker audit/build
acceptance remains necessary before the child can be accepted. #2573 retains the
private source/archive reconstruction and semantic-outcome work. The live
`verify-completion.py` invocation still exits 1: 44 sources, all 1,150 candidates
preserved across 1,112 provisional atoms, and zero verified delivered atoms.
Missing private source inputs cannot be replaced with opaque-ID guesses or with
current task-state observations. Neither this repair nor a future child merge
discharges that campaign acceptance.

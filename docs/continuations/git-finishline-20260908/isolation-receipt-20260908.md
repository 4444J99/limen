# Recovery test isolation and acceptance corrections

Owner: recovery campaign, [Limen #2573](https://github.com/4444J99/limen/pull/2573).
This increment starts from `eef3466ee541b5d72d621706e19e02a3ed27590a` in a separate
`work/recovery-isolation-20260908` checkout. Original campaigns and archives remain
unchanged. It does not establish recovery reconciliation, landing, or deployment.

Protected execution: `codex-estate-recovery-delivery-20260908`,
run `run-034641855de71965a29f31c4abfdff26`, generation 1042. The previous MCP run
was already terminal with no active lease before this reservation.

## Root cause and correction

Dispatch's `_load_limen_env` reloaded the operator credential cache after the
autouse fixture removed conduct credentials. Authenticated HTTP then took
precedence over the temporary keeper. Each test now uses an empty temporary
credential file, exports that file to subprocesses, and retains its temporary
SQLite keeper. An urllib transport guard raises before actual conduct/board
requests; HTTP unit tests can still explicitly mock transport.

Incomplete shipping caches render `unavailable`, preserving the distinction from
verified zero. Recovery acceptance rejects malformed and empty extraction,
missing/invalid lineage digests, and a candidate denominator other than the frozen
1,150 in the campaign CLI. These structural checks do not semantically reconcile
the candidates.

## Live request audit

Authenticated read-only inspection at approximately 2026-09-08T22:46Z found the
test-created `codex-serial-reserve` registration, registered at
2026-09-08T22:19:44.611Z and last heartbeated at 22:23:15.303Z. It was unhealthy
with zero active leases. This is a confirmed unintended live mutation from the
previous test episode, not merely an attempted request. No registration was
deleted or peer signalled.

The live private board had neither `ACK-CUSTODY` nor `NEXT`; both authenticated
task-run lookups returned `found: false`. No retained task dispatch-log entry
matched `codex-serial-reserve`. These are current-state observations and do not
prove the absence of removed or unexposed historical events. Full historical
audit remains owned by #2573; predicate: reconcile the keeper event history for
that registration/time interval before claiming no other mutation. Next action:
inspect the credential-owned Worker audit export, without modifying live state.

## Verification

- Targeted isolation, four refund parametrizations, shipping-cache reader and
  HTTP-client batch: 21 passed (exit 0).
- Recovery batch: 151 tests and 15 subtests passed (exit 0), covering isolation,
  local prelaunch, inventory admission, archive recovery, young host fixtures,
  native HTML generation, and completion counterexamples.
- After adding nested malformed-evidence handling, only that changed shard was
  rerun: `env PYTHONPATH=cli/src python3
  docs/continuations/git-finishline-20260908/test_completion.py`, 17 passed (exit 0).
- `bash scripts/verify-scoped.sh --integration --base
  eef3466ee541b5d72d621706e19e02a3ed27590a`: cheap gates passed except inherited
  host-fixture formatting (exit 1). Corrected it and reran only the registered
  formatting command: 679 files formatted, exit 0. Unchanged green shards retained.
- `git diff --check`: exit 0.

Heavy admission at 2026-09-08T22:48:26Z: denied for `swap-fraction,vitals-shed`,
swap fraction 0.460144, no host lease. Owner #2573; missing predicate is the
implicated integration batch. Next command after changed host conditions:
`bash scripts/verify-scoped.sh --integration --base
eef3466ee541b5d72d621706e19e02a3ed27590a`, retaining unchanged green shards via the
existing receipt runner. No heavy predicate or full campaign completion claimed.

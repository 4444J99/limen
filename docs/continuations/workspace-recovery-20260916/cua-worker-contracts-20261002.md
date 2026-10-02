# Exact CUA worker contracts

Owner: Limen #2763, Domus #397. This is a process-measurement repair, not
certification of any historical session or authorization to stop processes.

The enabled CUA service declares `CUA_REPL_NODE_REPL_PATH`, but its three
direct native workers previously lacked individual service contracts. The
repair accepts exact configured-host app-server commands and exact Node worker
commands only with full script bytes embedded in the declared vendor helper.
The observed working directory, same-user direct parent, existing verified
parent service, registered native host, and file digests remain required.
Helper bytes are included in worker contract provenance, not merely inspected
once. Altered scripts, symlinks, unrelated executables, unknown directories,
argument expansion and unregistered app-server commands remain rejected.

Verification on 2026-10-02:

- Scoped cheap wave: all 34 gates passed; heavy wave denied admission with
  `heavy-lease-held`. This is exit 75, not a complete local verification pass.
- After adding the helper to contract file provenance, the changed shard passed:
  37 CUA/process-ownership tests and mypy on `process_services.py`.
- Read-only development observation recognized live workers 54525, 54526 and
  54527 as `verified_service_contract`, owner `codex/cua_repl`, with native
  host PID 955 and exact host start identity. No process was adopted or signaled.
- That broad Workspace observation still contained 19 unknown processes. Its
  denominator is not the historical multi-root predicate denominator; it cannot
  certify those sessions or claim an estate-wide reduction.

The new tests are included in the owning `session-closeout-test` gate. Remote
exact-head verification, source merge, installed-runtime adoption and historical
session predicate rechecks remain separate acceptance steps.

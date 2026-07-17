# Recovery Process Incidents

## 2026-07-16 scheduled-sensor invocation

During independent review of the relationship snapshot contract, a reviewer mistakenly invoked
the scheduled heartbeat sensor runner at beat 168 with an empty temporary voice directory. The
runner executed for roughly ten seconds before it was stopped. This was outside the requested
focused predicate and violated the recovery rule against broad runner execution.

Read-only containment evidence:

- the reviewer thread was interrupted and no further broad runner call was permitted;
- no remaining `beat-sensors.py` or `gitvs.py` process was found;
- `tasks.yaml` was not modified;
- no Claude or other peer session was inspected, signalled, stopped, or retuned;
- two accidentally regenerated tracked projections were restored byte-for-byte to the branch
  base (`docs/prompt-atom-ledger.md` and `organs/observation/bifrons/PORTAL.md`);
- three isolated ignored sensor receipts were removed from the recovery worktree;
- the provider-neutral `peer-integration` regeneration in `docs/always-working.md` was retained
  because it belongs to the independently verified co-equality correction.

The runner used start-new-session child groups, so absence of a surviving process is not proof
that every invoked sensor was zero-effect during the ten-second window. No remote or host mutation
was observed, but that claim remains bounded to the evidence above. Future contract review must
invoke only the named focused test and static registry checks; running `beat-sensors.py --run` is
prohibited in this recovery lane.

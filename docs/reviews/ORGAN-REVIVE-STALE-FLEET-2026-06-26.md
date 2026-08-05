# ORGAN-revive-stale-fleet report - 2026-06-26

Live state inspected from `$LIMEN_ROOT=/Users/4jp/Workspace/limen`.

## Diagnosis

Launchd was not the primary failure: `com.limen.heartbeat` was loaded and running.
The stale cluster came from three coupled causes:

1. `vitals-gate` treated memory pressure as a full idle beat and `continue`d before
   the lower-half organs could stamp liveness.
2. Higher-cadence voices (`HEAL`, `EVOCATOR`, `HEALTH`, `LIFE`, `HYGIENE`) depended
   only on the in-process modulo beat counter. Repeated heartbeat restarts and
   memory-pressure beats reset or skipped the counter before beat 6/8.
3. `MERGE` ran inside `scripts/drain.sh`, but nothing stamped `logs/.voice/merge`,
   and `organ-health.py` judged it as an every-beat organ instead of the drain voice
   it actually rides.

The live log also showed a board validation failure earlier in the day
(`tasks.0.created` missing) that collapsed the board until `heal-board.py` repaired
it. That was a contributing stale-base/board-health event, not a per-organ crash.

## Per-organ root cause and fix

| Organ | Root cause | Fix in this branch |
| --- | --- | --- |
| `merge` | No merge voice stamp; `organ-health` expected every beat while `merge-drain.py` actually runs under `drain.sh`. | `drain.sh` now stamps `logs/.voice/merge` after `merge-drain.py`; `organ-health.py` measures merge on `DRAIN` cadence. |
| `heal` | `C_HEAL=6` was starved by restart/counter reset and pressure short-circuiting. | Added `due_voice heal "$C_HEAL"` so stale heal fires immediately even after restarts. |
| `vigilia` | Memory-pressure path exited before `python -m limen.vigilia beat` and `stamp vigilia`. | Vitals pressure now skips only final dispatch; lower-half status organs still run. |
| `evocator` | `C_EVOCATOR=6` was starved by restart/counter reset and pressure short-circuiting. | Added overdue-aware `due_voice evocator "$C_EVOCATOR"`. |
| `health` | `C_HEALTH=6` was starved by restart/counter reset and pressure short-circuiting. | Added overdue-aware `due_voice health "$C_HEALTH"`. |
| `life` | `C_LIFE=6` was starved by restart/counter reset and pressure short-circuiting. | Added overdue-aware `due_voice life "$C_LIFE"`. |
| `hygiene` | `C_HYGIENE=8` was starved by restart/counter reset and pressure short-circuiting. | Added overdue-aware `due_voice hygiene "$C_HYGIENE"`. |

## Safety posture

No force-push, branch reset, or shared-ref rewrite is part of this fix. The merge
organ still uses the existing `merge-drain.py` policy: only mergeable, CI-green,
non-trivial PRs are eligible; conflict, CI-red, and stale-base PRs remain refused
and routed to heal work.

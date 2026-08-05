# Constant-time Claude SessionEnd

Claude project `SessionEnd` performs one bounded operation: it converts the hook payload to a
redacted `limen.session_end_breadcrumb.v1` record and appends one line to
the host-stable `${LIMEN_SESSION_END_BREADCRUMBS:-${XDG_STATE_HOME:-$HOME/.local/state}/limen/session-end-breadcrumbs.jsonl}`
queue. The queue never lives under a versioned installed runtime or checkout. The project settings
cap the hook at five seconds, the shell
wrapper uses an inner four-second timeout when available, and the producer's tested steady-state
budget is below 500 ms. An invalid payload or unavailable target fails open and never prints prompt
content.

The project settings resolve hooks from `CLAUDE_PROJECT_DIR` and fall back to the stable live Limen
checkout when that worktree has already been reaped. Host-global installation remains Domus-owned.
During the migration, global and project producers may both append the same SessionEnd occurrence;
their occurrence key makes that duplication harmless, while a later end of a resumed session resets
that session's consumers for the new transcript revision. If transcript metadata is unavailable, a
source-neutral payload identity pairs the bounded global/project deliveries while a unique delivery
identity makes a repeated same-source end start fresh. The cursor and per-occurrence consumer receipts
remain owned by the live Limen checkout under `logs/`.

## Heartbeat-owned consumers

`scripts/consume-session-end-breadcrumbs.py` owns all slower work. It serializes every entrypoint,
advances a corruption-tolerant device/inode-aware byte cursor, and partitions pending receipts from
terminal history so each heartbeat reads only a bounded active prefix. Legacy flat receipts migrate
atomically in bounded batches without evicting pending work. A successful consumer is never rerun
for the same occurrence merely for reassurance. Failures retry at most three times; spawn failures
are receipted, each subprocess has its own timeout and process group, output evidence is bounded,
and each heartbeat processes a bounded session count and runway. A valid producer duplicate upgrades
an earlier malformed receipt instead of inheriting its terminal state.

The current slow consumers are:

- isolation-worktree compatibility closeout ledger append;
- handoff refresh;
- orphan-watcher audit;
- transcript claim capture;
- model/workflow audit, with policy violations preserved in the model-tier warning ledger; and
- lifecycle-pressure refresh.

Heartbeat invokes the drain under singleton ownership before the rest of its routine work, including
while autonomy is paused or the network is offline. The project SessionEnd hook must never import any
of those commands back into the synchronous path.

## Predicates

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=cli/src python3 -m pytest -q -p no:cacheprovider cli/tests/test_session_end_breadcrumbs.py cli/tests/test_handoff_relay.py
bash scripts/tests/worktree-commit-guard.test.sh
python3 scripts/consume-session-end-breadcrumbs.py --check
bash -n scripts/heartbeat.sh scripts/heartbeat-loop.sh scripts/hooks/session-closeout.sh
```

After Domus installs the global producer, activation requires an installed-file hash check and three
real Claude start/end cycles with no cancelled SessionEnd. Only then may a normal Limen PR remove the
temporary project producer.

Domus issue [#318](https://github.com/organvm/domus-genoma/issues/318) owns that render/apply and
real-cycle activation. Limen issue [#685](https://github.com/organvm/limen/issues/685) owns the
dynamic retirement or explicit preservation receipt for retained worktrees that still carry the old
synchronous handler; neither lane authorizes manual home-config edits or ad hoc worktree deletion.

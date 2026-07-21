# Constant-time Claude SessionEnd

Claude project `SessionEnd` performs one bounded operation: it converts the hook payload to a
redacted `limen.session_end_breadcrumb.v1` record and appends one line to
the host-stable `${LIMEN_SESSION_END_BREADCRUMBS:-${XDG_STATE_HOME:-$HOME/.local/state}/limen/session-end-breadcrumbs.jsonl}`
queue. The queue never lives under a versioned installed runtime or checkout. The project settings
cap the hook at five seconds, the shell
wrapper uses an inner four-second timeout when available, and the producer's tested steady-state
budget is below 500 ms. An invalid payload or unavailable target fails open and never prints prompt
content.

The project settings resolve hooks from `CLAUDE_PROJECT_DIR`, not a possibly stale primary checkout.
Host-global installation remains Domus-owned. During the migration, global and project producers may
both append the same session; their stable event/session key makes that duplication harmless.
The cursor and per-session consumer receipts remain owned by the live Limen checkout under `logs/`.

## Heartbeat-owned consumers

`scripts/consume-session-end-breadcrumbs.py` owns all slower work. It advances a device/inode-aware
byte cursor, deduplicates receipts by a hash of session ID, and persists each consumer's attempts and
terminal state. A successful consumer is never rerun for reassurance. Failures retry at most three
times; each subprocess has its own timeout and process group, output is capped and reduced to a
digest, and each heartbeat processes a bounded session count and runway.

The current slow consumers are:

- compatibility closeout ledger append;
- handoff refresh;
- orphan-watcher audit;
- transcript claim capture;
- model/workflow audit; and
- lifecycle-pressure refresh.

Heartbeat invokes the drain before the rest of its routine work. The project SessionEnd hook must
never import any of those commands back into the synchronous path.

## Predicates

```bash
python3 -m pytest -q cli/tests/test_session_end_breadcrumbs.py
bash scripts/done-session-orient.sh
python3 scripts/consume-session-end-breadcrumbs.py --check
```

After Domus installs the global producer, activation requires an installed-file hash check and three
real Claude start/end cycles with no cancelled SessionEnd. Only then may a normal Limen PR remove the
temporary project producer.

# Overnight Watch

Use `scripts/overnight-watch.py` for overnight proof. Do not keep any
interactive agent turn attached just to poll heartbeat output.

Default mode is one-shot:

```bash
python3 scripts/overnight-watch.py
```

It writes:

- `logs/overnight-watch.jsonl` append-only receipts
- `logs/overnight-watch-state.json` repeated-tick state
- `logs/overnight-watch.md` latest human-readable status
- `logs/overnight-watch-alert.json` only when a `WATCH_ALERT` is active

Recommended supervisor cadence is a cheap one-shot invocation every five
minutes. The script exits non-zero only when it has concrete evidence of a
blocker, such as a missing heartbeat log, stale heartbeat log, repeated latest
tick with no active workers, or optional dispatch-env drift.

The repo includes a launchd job for that cadence:

```bash
cp container/launchd/com.limen.overnight-watch.plist \
  "$HOME/Library/LaunchAgents/com.limen.overnight-watch.plist"
launchctl bootstrap "gui/$(id -u)" \
  "$HOME/Library/LaunchAgents/com.limen.overnight-watch.plist"
```

For the overnight fleet profile, run with explicit expectations:

```bash
LIMEN_OVERNIGHT_WATCH_EXPECT_DISPATCH_ASYNC=1 \
LIMEN_OVERNIGHT_WATCH_EXPECT_DISPATCH_LANES=auto \
python3 scripts/overnight-watch.py
```

`--watch` exists for a local terminal, but it is not the interactive-agent
pattern. Agents should inspect the receipt or respond to `WATCH_ALERT`; they
should not spend a large conversation context on routine five-minute polling.

# Overnight Watch

- Status: `alert`
- Updated: `2026-07-18T08:13:08+00:00`
- Log age: `30` seconds
- Launchd: `active`
- Latest tick: `tick emitted: 2026-07-18T08:03:46+00:00 total=2668 open=402 spent=4/600`
- Latest async: `async: reaped 0 dead · harvested 0 · 0 still running · launched 0`
- Stale tick samples: `0`
- Active workers: `0`
- Heartbeat child processes: `2`

## Overnight Summary

- Launched: `0`; harvested: `0`; reaped: `0`.
- Done: `0`; failed: `0`; no-op: `0`; timed out: `0`.
- Stale handoff: `false`.
- Gate action: `stop_no_durable_progress` (exit `20`).
- Dispatch allowed: `false`.
- Lane switch: `blocked`; owner packet: `none`; tickets: `0`.
- Lane blocker: `overnight-owner-packets-gated`.
- Next command: `python3 scripts/always-working.py --write`.

## Gate Checks

- Handoff refresh: `0`; check: `0`.
- Value gate: `20`; action: `stop_no_durable_progress`.
- Dispatch control: all bounded owner packets are closed by current capability, lifecycle, owner gate(s).
- Selected owner: `organvm/limen`.

## Throughput

- Recent per-60min completions: `[0, 0, 0]` (derived floor `0.0`, median `0`).
- Below floor: `false`; suppressed: `no`.
  - child `65112` `R` `00:30` `/opt/homebrew/Cellar/python@3.14/3.14.6/Frameworks/Python.framework/Versions/3.14/Resources/Python.app/Contents/MacOS/Python -m limen release-stale --agent jules --hours 24 --apply`
  - child `65113` `S` `00:30` `tail -1`

## WATCH_ALERT
- `overnight-lane-switch-blocked`: blocker=overnight-owner-packets-gated owner=organvm/limen reason=all bounded owner packets are closed by current capability, lifecycle, owner gate(s)

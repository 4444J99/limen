# Overnight Watch

- Status: `alert`
- Updated: `2026-08-20T18:30:35+00:00`
- Log age: `647` seconds
- Launchd: `active`
- Latest tick: `tick emitted: 2026-08-20T18:19:10+00:00 total=3184 open=884 spent=8/600`
- Latest async: `None`
- Stale tick samples: `1`
- Active workers: `0`
- Heartbeat child processes: `1`

## Overnight Summary

- Launched: `0`; harvested: `0`; reaped: `0`.
- Done: `0`; failed: `0`; no-op: `0`; timed out: `0`.
- Stale handoff: `false`.
- Gate action: `switch_to_packetization` (exit `10`).
- Dispatch allowed: `false`.
- Lane switch: `blocked`; owner packet: `AW-VALUE-REPOS-77d88c87bfb2`; tickets: `0`.
- Lane blocker: `overnight-owner-conduct-unavailable`.
- Next command: `PYTHONPATH=cli/src limen conduct capabilities`.

## Gate Checks

- Handoff refresh: `0`; check: `0`.
- Value gate: `10`; action: `switch_to_packetization`.
- Dispatch control: authenticated conduct is unavailable for exact owner packet AW-VALUE-REPOS-77d88c87bfb2: conduct broker is not configured; set LIMEN_CONDUCT_URL and LIMEN_CONDUCT_TOKEN (LIMEN_CONDUCT_STATE is an explicit local test adapter).
- Selected owner: `organvm/limen`.

## Throughput

- Recent per-60min completions: `[0, 0, 0]` (derived floor `0.0`, median `0`).
- Below floor: `false`; suppressed: `no`.
  - child `56095` `S` `01-04:42:31` `/bin/bash /Users/4jp/Workspace/limen/scripts/heartbeat-loop.sh`

## WATCH_ALERT
- `overnight-lane-switch-blocked`: blocker=overnight-owner-conduct-unavailable owner=organvm/limen reason=authenticated conduct is unavailable for exact owner packet AW-VALUE-REPOS-77d88c87bfb2: conduct broker is not configured; set LIMEN_CONDUCT_URL and LIMEN_CONDUCT_TOKEN (LIMEN_CONDUCT_STATE is an explicit local test adapter)

# Overnight Watch

- Status: `alert`
- Updated: `2026-08-17T20:16:10+00:00`
- Log age: `391` seconds
- Launchd: `active`
- Latest tick: `tick emitted: 2026-08-17T18:08:25+00:00 total=3119 open=837 spent=8/600`
- Latest async: `None`
- Stale tick samples: `22`
- Active workers: `0`
- Heartbeat child processes: `1`

## Overnight Summary

- Launched: `0`; harvested: `0`; reaped: `0`.
- Done: `0`; failed: `0`; no-op: `0`; timed out: `0`.
- Stale handoff: `true`.
- Gate action: `switch_to_packetization` (exit `10`).
- Dispatch allowed: `false`.
- Lane switch: `blocked`; owner packet: `none`; tickets: `0`.
- Lane blocker: `overnight-handoff-blocked`.
- Next command: `python3 scripts/handoff-relay.py && python3 scripts/handoff-relay.py --check`.

## Gate Checks

- Handoff refresh: `0`; check: `1`.
- Value gate: `10`; action: `switch_to_packetization`.
- Dispatch control: handoff relay is not fresh enough to transfer one owner packet.
- Selected owner: `organvm/limen`.

## Throughput

- Recent per-60min completions: `[0, 0, 0]` (derived floor `0.0`, median `0.0`).
- Below floor: `false`; suppressed: `no`.
  - child `1297` `S` `06:08:15` `/bin/bash /Users/4jp/Workspace/limen/scripts/heartbeat-loop.sh`

## WATCH_ALERT
- `handoff-relay-stale`: handoff-relay --check: FAIL — provider headroom stale (141m > 90m)
- `overnight-lane-switch-blocked`: blocker=overnight-handoff-blocked owner=organvm/limen reason=handoff relay is not fresh enough to transfer one owner packet

# Network Health

Generated: `2026-06-28T19:21:02+00:00`

Status: `healthy`

## Scope

- Records the netmode/netmeter launchd safety state after the legacy timer incident.
- Read-only: no route changes, no launchctl writes, no credential/config reads, no agent stops.
- The netmode config file may contain local SSIDs or provider details and is intentionally not printed.

## Incident Class

- This is not only a current connectivity receipt. It is a guard against the single-lane failure mode: one agent patches one symptom, leaves no reusable gate, and the next lane rediscovers the same substrate problem.
- A network/environment repair is not closed until the tracked code, live installed path, launchd state, and conductor blocker surface all agree on the invariant.
- Future lanes should treat a failed network-health receipt as substrate work first, not as incidental flakiness inside an unrelated task.

## Live State

- Mode file: `observe` at `~/Library/Application Support/netmeter/mode`.
- Default route: `en0` via `192.168.1.1` (probe rc `0`).

## Safety Gates

| Gate | Status | Evidence |
|---|---:|---|
| Tracked netmode observe-only tick gate | `true` | `scripts/netmode.sh` missing: `none` |
| Live installed netmode observe-only tick gate | `true` | `~/Library/Application Support/netmeter/netmode.sh` missing: `none` |
| Legacy netmeter plist disabled | `true` | `container/launchd/com.user.netmeter.plist` missing: `none` |

## Launchd Labels

| Label | Disabled | Loaded |
|---|---:|---:|
| `com.user.netmeter` | `true` | `false` |
| `com.user.netmode.netwatch` | `true` | `false` |
| `com.user.netmode.keepalive` | `true` | `false` |
| `com.user.netmode.recycle` | `true` | `false` |

## Blockers

- none

## Verification

- `bash -n scripts/netmode.sh`
- `bash scripts/netmode.sh selftest`
- `plutil -lint container/launchd/com.user.netmeter.plist`
- `python3 scripts/network-health.py --write`

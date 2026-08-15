# Track C receipts (#1703)

Immutable attempt pack + live closeout owner.

| File | Role |
|---|---|
| `acceptance-2026-08-04.json` | Track B merged + first Track C attempt (no-op at 2.1.220) |
| `2026-08-04-baseline.json` / `2026-08-04-post.json` | Immutable strict-audit snapshots from the first attempt |
| `closeout-latest.json` | Latest `scripts/tcc-track-c-closeout.py` receipt |
| `closeout-*.json` | Timestamped closeout attempts |

## Formula

```text
track_c_pass = non_noop_update AND normalized_inventory_green
```

`non_noop` means `claude --version` advances past cutover baseline **2.1.220**.
A no-op `claude update` ("up to date") is wait evidence, never completion.

## Commands

```bash
python3 scripts/tcc-track-c-closeout.py --beat
python3 scripts/tcc-track-c-closeout.py --run
python3 scripts/tcc-track-c-closeout.py --finalize --write-lever   # only after met
```

Status projection: `logs/tcc-track-c-status.json` (beat owner receipt).

## 2026-08-15 finding — a normal restart does not heal the daemon leak

The #1703 containment assumption ("the pre-cutover background Claude daemon cannot be
retrofitted while live; policy preserves that active process until its normal restart") is
**falsified by observation**:

- The daemon restarted 2026-08-14 19:29:57 local and came back **unhosted again**:
  `claude daemon run … --origin transient --spawned-by {"label":"claude agents","pid":76274}`,
  reparented to launchd (PPID 1), self-responsible for TCC.
- Cause: the daemon is auto-spawned by whichever interactive `claude` runs first, and **no
  interactive ingress is hosted** — no shell wrapper, alias, or PATH shim routes `claude`
  through `domus-agent-host ensure` (verified 2026-08-15: `~/.zshrc`/`~/.zprofile` clean,
  `~/.local/bin/claude` is the raw Mach-O launcher). Every daemon generation therefore
  inherits unhosted ancestry, and TCC attributes its sessions' prompts to the per-version
  binary path — the operator sees dialogs from an "app" named `2.1.233`.
- Observed cost at 2.1.233: a fresh grant burst for
  `~/.local/share/claude/versions/2.1.233` — Documents (08-14 22:50), AppleEvents (23:01),
  Desktop (23:31), then FileProvider / Removable Volumes / Downloads / **Media Library** in a
  16-second prompt burst (08-15 12:37:21–12:37:37, all clicked Allow). This re-fires for the
  entire grant set at **every version advance** while the ingress stays unhosted.
- Consequence for Track C: `rotating_identity_active_grants` / `new_managed_identities`
  cannot go green by waiting for a restart. Paths to green are (a) the daemon-spawning
  ingress enters `DomusAgentHost` — and responsibility must be *proven* to survive the
  daemon's self-daemonization (upstream may disclaim responsibility on spawn; unverified) —
  or (b) upstream Claude Code gives its daemon/session processes a stable bundle identity
  instead of the per-version path (`ClaudeCode.app` exists at
  `~/.local/share/claude/ClaudeCode.app` but resumed sessions exec `versions/<v>` directly).

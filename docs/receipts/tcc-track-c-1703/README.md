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

## 2026-08-15 correction — Track C is upstream-blocked; no local ingress fix exists

The same-day finding above over-promised: path (a) is not a path. The "unverified" disclaim
hypothesis is now verified, and it forecloses every local ancestry fix. Responsibility map
measured live (`responsibility_get_pid_responsible_for_pid`, 2.1.233 process tree):

- daemon → **self-responsible**, exec'd via the `~/.local/bin/claude` symlink, which the
  updater re-points into `versions/<v>` on every update — so the daemon's own identity rotates;
- each bg-pty-host → **self-responsible**, exec'd from
  `ClaudeCode.app/Contents/MacOS/claude` (stable path, same inode);
- each session → responsible = its pty-host at spawn, but the vendor **disclaims at startup**
  and the session lands on its own exec path `versions/<v>` — the rotating TCC client the
  operator sees as an app named "2.1.233".

`scripts/claude-identity-bundle.py` (sensor 0g8d) has owned this exact diagnosis since
2026-08-05: Claude Code disclaims inherited TCC responsibility **by design**
(`macDisclaimResponsibility: true` — a supervising host, `DomusAgentHost.app` included,
cannot carry an identity into it), and the daemon composes the session's `versions/<v>` argv
inside the signed vendor binary — "nothing outside it can redirect the session onto the
bundled path." Its scope note says plainly that a green bundle keeper must not be read as
"prompts are fixed." Hosting any ingress therefore cannot green Track C.

Two structural consequences, both recorded here so the wait-state reads honestly:

1. **The hosted-update requirement can never fire while autoupdate is on.**
   `automatic_updates_enabled: true` means the vendor self-updates before any hosted update
   runs, so `update_attempted` stays `false` forever — the formula's non-noop
   through-the-host update is unreachable by construction, not by patience.
2. **The fix is upstream.** anthropics/claude-code#86706 (open, filed 2026-08-14,
   root-caused with TCC log evidence) and #74068 (open) cover exactly this defect: session
   identity should ride the stable `com.anthropic.claude-code` bundle, not the per-version
   path. Until a vendor version ships that, every update mints a new TCC client and the
   prompt burst recurs. Cost evidence: `versions/2.1.233` now holds allowed grants for
   Documents / Desktop / Downloads / Removable Volumes / FileProvider / Media Library /
   AppleEvents, and the system db shows three successive Full Disk Access **denials**
   (2.1.222, 2.1.226, 2.1.233) — the operator re-answering the same question each bump.

Wait-state: Track C stays `blocked` on the beat until a post-fix vendor version advances the
audit to green; no local action can discharge it. The one local dial that changes the
operator's experience meanwhile is `autoUpdates: false` (prompt bursts on a chosen update
cadence instead of the vendor's ~daily one) — an operator trade of freshness for quiet,
never an agent default.

## 2026-08-15 measurement — the two obvious local cures are REFUTED, with a predicate

"Upstream-blocked" above was challenged the same day: reading the vendor binary showed that
non-spare pty-hosts re-exec into the stable bundle (`Vsm()`) while **spare pty-hosts skip that
re-exec** (`if(!r) await Vsm()`), so background sessions claimed from pre-warmed spares carry
the `versions/<v>` identity. That is a true and useful refinement of the mechanism — and it
suggested two filesystem-level cures that reach where the vendor's argv cannot. A healer for
the first was written, wired, and opened as PR #2450 **before** its premise was measured. The
measurement refuted it, and the second cure with it. Both are now guarded by
`scripts/tcc-identity-attribution-probe.py`:

| Cure | Idea | Measured result |
|---|---|---|
| **Enclosure** | Move the store to `ClaudeCode.app/Contents/MacOS/versions`, symlink the old path, so every exec is bundle-enclosed | **REFUTED** — CoreFoundation resolves a binary nested one level below `Contents/MacOS` to its immediate **parent directory**, exactly as it resolves a loose binary. Bundle identity attaches only to the declared `CFBundleExecutable`. |
| **Symlink** | Point `versions/<v>` at the bundle's main executable so the kernel resolves onto it | **REFUTED** — the kernel records the path used at exec (the **symlink's own path**); only the underlying vnode (`lsof … -d txt`) shows the target. |

PR #2450 was held in draft and closed unmerged; nothing placebo-shaped landed. The probe is a
**ratchet on a negative result** — exit 0 while both refutations hold, exit 1 if macOS
behavior changes and the cures deserve a fresh look. It exists because an unrecorded negative
result decays into folklore and gets re-derived at full cost: this estate has already shipped
five cures against one false premise (IF-GATEKEEPER-INERT), which is the same failure this
entry is refusing to repeat.

Standing conclusion, now measured rather than argued: **the fix is upstream**
(anthropics/claude-code#86706, #74068). Locally, only `autoUpdates: false` changes the
operator's experience, by choosing the cadence of the bursts rather than preventing them.

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
| **Symlink** | Point `versions/<v>` at the bundle's main executable so the kernel resolves onto it | ~~REFUTED~~ **WITHDRAWN 2026-08-15** — that verdict measured `ps comm`, the accounting string, not code identity. See the amendment below. |

PR #2450 was held in draft and closed unmerged; nothing placebo-shaped landed. The probe is a
**ratchet on a negative result** — exit 0 while both refutations hold, exit 1 if macOS
behavior changes and the cures deserve a fresh look. It exists because an unrecorded negative
result decays into folklore and gets re-derived at full cost: this estate has already shipped
five cures against one false premise (IF-GATEKEEPER-INERT), which is the same failure this
entry is refusing to repeat.

Standing conclusion, now measured rather than argued: **the fix is upstream**
(anthropics/claude-code#86706, #74068). Locally, only `autoUpdates: false` changes the
operator's experience, by choosing the cadence of the bursts rather than preventing them.

## 2026-08-15 amendment — the symlink refutation measured the wrong quantity

The section above is amended, not replaced. Its **enclosure** refutation is independently
**confirmed**: a second probe reproduced it exactly — a binary nested one level below
`Contents/MacOS` resolves to its parent directory, never to the `.app`. Cure A is dead.

Its **symlink** refutation is **withdrawn**. `scripts/tcc-identity-attribution-probe.py`
measures with `ps -p <pid> -o comm=`, which returns the kernel's *accounting string*
(`p_comm`) — the path used at exec. That measurement is correct about that quantity. It is
not the quantity a TCC client identity derives from. Four reads, three layers:

| Measure | Layer | A symlink exec reports |
|---|---|---|
| `ps -o comm=` | accounting string (`p_comm`) | the **symlink's own path** |
| `proc_pidpath` | vnode path | the **target** |
| `lsof -a -d txt` | vnode | the **target** (their own probe: `/bin/sleep`) |
| launch-constraint evaluation | kernel code identity (AMFI) | the **target** — decisive |

The last row is decisive because its outcome is binary and externally visible rather than a
string to interpret. `/bin/sleep` is a platform binary constrained to its canonical path:

```text
cp    /bin/sleep $T/copy && $T/copy 0.3   ->  exit 137  (SIGKILL — constraint VIOLATED)
ln -s /bin/sleep $T/link && $T/link 0.3   ->  exit 0    (constraint SATISFIED)
```

A **copy** at the temp path is killed; a **symlink** at that same temp path runs. The
constraint can only be satisfied if the kernel evaluated it against `/bin/sleep` — that is,
it resolved the symlink *before* deciding code identity. The attribution probe's own output
already contains this evidence and reads past it: its symlink child ran to completion,
returning a `comm` and an `lsof` entry instead of `<defunct>`, which is possible only if the
constraint was satisfied through the link.

**Status of cure B: not refuted — unresolved, with the evidence leaning viable.** Two things
are still required before anything ships, and neither is done. **Owner: organvm/limen#2465** —
this paragraph is a description, not a home, and the work is not tracked by its being written
here:

1. **The end-to-end test.** Every measurement so far is a proxy. The decisive experiment is
   to trigger a TCC-protected access from a symlinked binary and read the resulting `client`
   column in the TCC db. Until that runs, "the code-identity layer resolves symlinks" is a
   strong *necessary* condition, not proof that TCC attributes the target.
2. **An effector on a cadence.** The vendor re-materializes the version store on start, so a
   hand-laid symlink is overwritten. A one-time `ln -s` cures nothing.

**Consequence for the ratchet — found, then fixed.** As first written,
`tcc-identity-attribution-probe.py` computed cure B's verdict as `recorded == str(link)`
against `p_comm`. That comparison holds regardless of what the code-identity layer does, so
the ratchet could never have detected the change it existed to watch for: it would have read
OK forever in either world. The cure-A arm was sound and is kept exactly as it was; the
cure-B arm now measures the code-identity discriminator and reports
`code_identity_resolves_target` (JSON schema bumped to **v2** — `recorded_executable_path`
became `accounting_string_p_comm`, so no reader mistakes an accounting string for an
identity). Exit 1 now means macOS genuinely changed.

**And the ratchet is wired to a cadence.** A predicate nothing runs decays exactly like the
prose it replaced — which is this probe's own stated rationale, so leaving it unscheduled
would have reproduced the defect it was written to prevent. It rides the hygiene beat as a
step of sensor **`0g8b`** (`institutio/governance/sensors.yaml`), advisory severity: a changed
verdict is a re-measure prompt, not a broken host.

**Registry correction.** Lineage prose (and the agent memory `tcc-prompts-upstream-blocked`)
cited `scripts/heal-claude-versions-enclosure.sh`, a `sensors.yaml` class-5 sensor, and a
valve `LIMEN_CLAUDE_VERSIONS_ENCLOSURE_HEAL`. **None of the three exist** — `git ls-files
scripts/` lists only `heal-claude-cask.sh`, `heal-claude-lsregister.sh` and
`heal-claude-update-marker.sh`, and `VERSIONS_ENCLOSURE` appears nowhere in
`institutio/governance/sensors.yaml`. Consistent with PR #2450 having been closed unmerged.
Do not cite the enclosure healer as an armed capability.

### The fixture trap — why this took three crashed runs to measure

A separate probe in this lineage built its fixtures from copies of `/bin/sleep` and
`/bin/echo`. Those are Apple **platform binaries** (`codesign -dv` → `Platform identifier=26`)
carrying a launch constraint pinning them to their canonical path, so the kernel SIGKILLed
every copy at exec:

```text
Exception Type:      EXC_CRASH (SIGKILL (Code Signature Invalid))
Termination Reason:  Namespace CODESIGNING, Code 4, Launch Constraint Violation
```

Three crash reports (`~/Library/Logs/DiagnosticReports/tool-2026-08-15-115647.000.ips`,
`-115822.000.ips`, `-120019.ips`) correspond one-to-one with three re-runs. Each read the
dead child's path as `None`/`<defunct>` and **misattributed it to `ctypes`/`proc_pidpath` not
binding**. The measuring API was never the problem; the fixture was. `/bin/sleep` reached by
**symlink** survives — which is exactly why it works as the discriminator above — but any
**copy** of it is a corpse before the first measurement.

A second fixture defect followed: linking every arm to one inode. `proc_pidpath` resolves a
vnode through the name cache, so a multiply-linked inode reports an *arbitrary* alias — all
arms, including the bundle's own executable, reported the hardlink's name. Isolating each arm
in its own root with its own inode reads clean.

Both defects fail identically: **a broken fixture that reads as a measurement.** Hence
`scripts/probe-exec-identity.py` asserts every child is alive before reading anything and
raises `FixtureError` otherwise — a dead child must never return a datum. Its arms:

| Arm | Layout | Exec'd via | `proc_pidpath` records |
|---|---|---|---|
| A | bundle only | bundle exec | `Test.app/Contents/MacOS/tool` |
| B | bundle + hardlink outside (**today**) | bundle exec | `Test.app/Contents/MacOS/tool` |
| C | bundle + hardlink outside (**today**) | the hardlink | `versions/2.1.233` |
| D | bundle + symlink outside (**proposed**) | the symlink | `Test.app/Contents/MacOS/tool` |
| E | platform binary, copy vs symlink | both | copy **killed**, symlink **runs** |

Arm C reproduces today's defect: the vendor materializes `versions/<v>` as a hardlink of the
bundle executable's inode, and exec'ing that name records the *versions* path — the rotating
client the operator sees as an app named "2.1.233". Arm E is the discriminator above.

## 2026-08-15 resolution — cure B is confirmed by the live TCC db, and the heal ships

Arm D above is *proposed*, not measured. It never needed to be provoked: the end-to-end evidence
was already standing in the operator's own `TCC.db`, which is stronger than a synthetic fixture
because it is the deciding subsystem answering about itself.

**Homebrew is the natural experiment.** `utils/ruby.sh:118` sets
`vendor_ruby_root="${vendor_dir}/portable-ruby/current"`, so brew *always* execs ruby through the
`current` **symlink**, never the versioned path. The resulting TCC client column reads
`/opt/homebrew/Library/Homebrew/vendor/portable-ruby/4.0.6/bin/ruby` — the **resolved target**.
Corroborated four times over by `python3.14`, `tmux`, `bash` and `op`, each invoked through the
`/opt/homebrew/bin` symlink farm and each recorded by its real Cellar path. **TCC code identity
follows the symlink target.** (Homebrew has the identical disease for the same reason: `python@3.14`
holds three separate grant rows — 3.14.2, 3.14.4, 3.14.5.)

Two further facts make the heal safe and sufficient:

| Fact | Measurement |
|---|---|
| A new build satisfies the existing grant | **One** distinct `csreq` blob across all 61 rows spanning 2.1.144 → 2.1.233. No per-version cdhash: only the *lookup* misses today, never the validation. |
| The vendor already ships the stable identity | `ClaudeCode.app/Contents/Info.plist` declares `CFBundleIdentifier = com.anthropic.claude-code` with AppleEvents/LocalNetwork/Microphone usage strings, and `Contents/MacOS/claude` is the **same inode** as the live `versions/<v>` (`st_nlink == 2`). Sessions simply do not exec it. |

So the heal is `ln -s`, not a TCC write: **`scripts/claude-bundle-identity-heal.py`** replaces the
live `versions/<v>` hardlink with a symlink to the bundle executable. Same bytes, second name;
nothing copied, nothing deleted. Sessions then resolve to a path that never changes, and the grant
survives updates the way a normal app's does.

Safety is carried by inode identity: only an entry sharing the bundle executable's inode is ever
touched — by construction the live build, where unlinking one of two names for a file destroys
nothing. A stale version is a distinct inode holding its own rollback bytes and is left alone.
Dry-run is the default, the healed path is exec-verified immediately and rolled back automatically
if it fails to run, and `--revert` restores the hardlink exactly.

This does **not** discharge upstream: anthropics/claude-code#86706 remains the correct fix, because
the vendor rematerializes `versions/<new>` as a real file on every update, so the heal must re-run
per update. It does mean the operator's dialog burst is a local, reversible, filesystem-level
problem rather than a wait on a vendor release.

**Superseded here:** the "no local ingress fix exists" conclusion of the earlier correction above,
and the enclosure/symlink refutation table. Enclosure stays refuted. Symlink was refuted on a
proc_pidpath measurement generalized to a subsystem that does not use it — a green predicate that
was wrong, which is the sharper form of the IF-GATEKEEPER-INERT lesson: a predicate is only worth
the subsystem it measures.

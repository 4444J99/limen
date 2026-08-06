# Stable macOS responsibility identity

`DomusAgentHost.app` is the fixed macOS responsibility identity for local agent
execution. Claude, Python, Homebrew, uv, Limen runtimes, PTY hosts, spares, and
their MCP descendants may update or rotate underneath it without becoming new
privacy clients.

The host is native Objective-C code owned by `domus-genoma`, installed at:

```text
~/Applications/DomusAgentHost.app
```

Its bundle identifier is `org.organvm.domus.agent-host`. It uses inherited
standard streams and terminal state, places the supervised command in a
dedicated child process group, forwards signals, returns the foreground
leader's exit status, and remains alive while group members, recursively tracked
descendants, or inherited lifetime-pipe holders remain alive. Pipeline siblings
outside that child group are deliberately excluded. It is an on-demand CLI; no
LaunchAgent is installed.

## Interfaces

```sh
domus-agent-host run -- <command> [args...]
domus-agent-host ensure -- <command> [args...]
domus-agent-host status --json
tcc-identity-audit [--baseline <path>] [--json] [--strict]
tcc-identity-audit --write-baseline <path>
python3 scripts/tcc-app-management-fixture.py --json
```

`ensure` is the boundary for managed GUI ingress. It executes the command
directly only when the native host proves that the current process already
inherits its lifetime-pipe identity; otherwise it enters the existing native
host through `run`. The wrapper change does not rebuild or replace the fixed
signed binary. Claude Desktop, Claude Code, Codex Desktop, and tracked editor
MCP registrations use this interface before any rotating `uvx`, `npx`, Node,
Python, or portable/Homebrew Ruby executable.

Every committed `com.limen.*` control-plane LaunchAgent, including the
generated heartbeat, enters `DomusAgentHost.app` before Bash, Python, dispatch,
or provider work. The generated heartbeat also preserves its selected host path
in `LIMEN_AGENT_HOST_BIN`, so descendants audit the same identity that owns the
job. An inherited `DOMUS_AGENT_HOST_ACTIVE=1` marker is trusted only after the
native host verifies that its lifetime descriptor is the expected pipe
identity; a reused descriptor cannot bypass wrapping. Strict audits always
query the installed host and LaunchServices live; fixture-backed
status/inventories are test-only and rejected by `--strict`.

`status --json` uses macOS Security APIs and reports the installed bundle path,
bundle identifier, signature validity, designated requirement, CDHash, and
supervision policy. Strict audit compares that requirement with the
installer-owned sibling receipt
`~/Applications/.DomusAgentHost.designated-requirement`; a newly signed
replacement cannot certify itself by merely occupying the stable path. Every
dispatch boundary validates the same receipt before launching a provider, so an
identity replacement is blocked before protected work starts rather than only
at the next audit. A host replacement is not an ordinary update: the Domus
installer refuses to replace the fixed ad-hoc identity unless a persistent
signing identity is explicitly supplied for a deliberate migration, and updates
the receipt transactionally with rollback. Routing configuration may update
without replacing the host.

## Audit contract

`tcc-identity-audit` opens the TCC databases read-only and emits schema
`limen.tcc_identity_audit.v2`. It does not use `last_modified` as a containment
boundary. Instead, an explicit pre-cutover baseline stores deterministic hashes
of managed client identities plus the normalized App Management grant map for
unrelated bundle-ID applications. No executable path is written to the
baseline or rendered in audit output.
Writing the baseline is a create-once operation: the audit refuses to replace
an existing cutover anchor, so a later leak cannot be normalized into green by
rerunning the writer.

Relevant clients are classified as:

- `stable_host`: the permanent host bundle or executable;
- `baseline_managed`: a managed path identity present before the cutover;
- `new_managed`: a managed path identity absent from that baseline;
- `managed_unbaselined`: a managed path identity when no valid baseline is
  available; and
- `unrelated`: an application or path outside the managed runtime families.

The audit reports four independent predicates:

1. **Active-leak containment:** no enabled managed App Management path row and
   no new managed TCC identity absent from the baseline.
2. **Visible App Management cleanliness:** exactly one enabled
   `org.organvm.domus.agent-host` bundle row and zero path clients in
   `SystemPolicyAppBundles`. A path row fails this predicate even when its
   switch or `auth_value` is disabled.
3. **Configured-ingress containment:** every tracked, managed local MCP command
   in a live GUI integration enters through `domus-agent-host ensure --`.
4. **Rotating-identity containment:** zero path-keyed clients matching a
   rotating-runtime pattern hold a live grant in **any** TCC service. Predicates
   1 and 2 are scoped to `SystemPolicyAppBundles`; the dialog the operator
   actually receives is `"<version>" would like to access files in your
   Documents folder` — `kTCCServiceSystemPolicyDocumentsFolder` against a client
   under `~/.local/share/claude/versions/<version>/`. Until 2026-08-05 nothing
   judged that service, so the inventory could read fully green while every
   vendor update minted a new identity and re-prompted. This predicate counts
   the sprawl directly and names the services still pinned to a rotating path.

A fifth preservation check requires the unrelated App Management bundle-grant
map to remain byte-for-byte equivalent after normalization. Strict mode also
fails if managed automatic updates are disabled, the host is absent or
invalidly signed, its stable identity is absent from the readable TCC inventory,
TCC cannot be read, the baseline is missing or invalid, or a malformed Claude
helper remains registered. The audit never edits TCC, unregisters an
application, pins a tool, or changes an updater.

**Unmeasured is a third verdict.** Every database-derived predicate above reads
an empty client list when TCC cannot be read, and emptiness otherwise reads as
evidence — asserting zero leaks having observed nothing, while naming a missing
grant and a changed bundle map nobody looked for. A blind run therefore reports
`status: "unmeasured"` with `measured.tcc_database: false`, emits only
`tcc_database_unavailable`, and still exits non-zero under `--strict` (fail
toward caution: unmeasured is never green).

**The instrument needs its own grant, under a different service.** Reading
`~/Library/Application Support/com.apple.TCC/TCC.db` is gated by
`kTCCServiceSystemPolicyAllFiles` (Full Disk Access) — not by the App Management
service every predicate above judges. Running beneath the host is necessary but
not sufficient: until `DomusAgentHost.app` itself appears under System Settings →
Privacy & Security → **Full Disk Access**, a hosted run reports `unmeasured`
exactly like a bare one (verified 2026-08-05). Grant it to the host bundle, never
to a versioned path, or the measurement acquires the sprawl it exists to detect.
`L-DOMUS-AGENT-HOST-TCC` owns both clicks.

**Automatic updates are read from `.claude.json`, not inferred.** The blocker
scan covers `DISABLE_*` environment keys, `settings.json` `env` blocks,
`~/.limen.env`, and the `autoUpdates` field in every `.claude.json` root
(`~/.claude.json`, the `LIMEN_ROOT` runtime copy, and any `CLAUDE_CONFIG_DIR`).
That last source is load-bearing: a session under `CLAUDE_CONFIG_DIR` never
reads the home file, so flipping only `~/.claude.json` leaves updates off where
the session actually runs — the state in which the 2026-08-05 discharge of
`L-DOMUS-AGENT-HOST-TCC` was produced against a version that could not advance.

## What the host cannot hold: a disclaimed identity

Claude Code re-execs itself once at startup with
`process.execve(..., {macDisclaimResponsibility: true})` —
`responsibility_spawnattrs_setdisclaim()` — guarded by `CLAUDE_BG_TCC_DISCLAIMED`
so it happens exactly once. This **deliberately severs inherited TCC
responsibility**, so a consent dialog names Claude Code rather than the terminal
that launched it. It is a correct design, and it is absolute: no wrapper, host,
or launcher can carry an identity across it. `domus-agent-host verify-lifetime`
exits non-zero downstream of the re-exec, exactly as this document's own
lifetime-pipe safeguard specifies. Do not read a process tree as evidence here —
the host tracks detached descendants by inherited pipe, so `PPID` proves nothing;
run the predicate.

The host therefore owns the **fleet** identity — every committed `com.limen.*`
LaunchAgent, the tracked GUI/MCP ingresses, dispatch boundaries — and never the
interactive Claude Code session's own consent prompts. Those are decided by one
expression in the vendor's code:

```js
let e = await _jb() ?? process.execPath;
```

`_jb()` materializes `<store>/ClaudeCode.app` (`CFBundleIdentifier`
`com.anthropic.claude-code`) and hardlinks the running binary into it, so the
disclaimed identity is a bundle that survives version rotation. It wraps `mkdir`,
`writeFile`, `stat`, `unlink`, and `link` in a single bare `catch { return null }`;
on any failure the identity falls back to `process.execPath` —
`<store>/versions/<version>`. TCC resolves a client by the bundle enclosing the
exec'd path, never by the bytes: the two paths are the **same inode**, but only
the bundled one has an identity to resolve, so the other is named by its own
filename. A dialog quoting a bare version number is a client with no bundle.

**What this does not explain (verified 2026-08-05).** A dialog quoting a bare
version number is *not* by itself evidence that `_jb()` failed. Observed with the
keeper reporting `at-ideal` and the bundle inode-correct:

```
30699  ~/.local/bin/claude daemon run ...                 (launchd-rooted)
  └─ 30721  ClaudeCode.app/…/claude --bg-pty-host … -- versions/2.1.222 …
       └─ 30826  versions/2.1.222 --session-id …          ← disclaims here
```

The daemon runs its pty host **from the bundle**, then passes the session process
its `versions/<version>` path as literal argv; that session is the one that
disclaims, so it becomes its own privacy client regardless of the bundle's state.
Four of five live processes ran from the versioned path. The argv is composed
inside the vendor binary, so nothing outside it redirects the session onto the
bundled path — this is an upstream defect, and the keeper below is a precondition
for the stable identity, not a cure for per-version prompts.

`_jb()` returns early when the hardlink already carries the running binary's
inode, skipping the `unlink`/`link` pair that concurrent session starts can
interleave into an `EEXIST`. `scripts/claude-identity-bundle.py` keeps the bundle
present and inode-correct so every start takes that early return; sensor `0g8d`
(`LIMEN_CLAUDE_IDENTITY_BUNDLE`) runs it each beat. The keeper writes exactly the
vendor's own bytes, is idempotent, and never signs, never edits TCC, and never
deletes a version — so more than one runnable version in the store stays a
**reported** race risk rather than a repaired one.

## One supported App Management transaction

The transaction is deliberately narrow:

1. Install the host and containment configuration. Record its designated
   requirement and CDHash before opening System Settings.
2. Immediately before the transaction, write the redacted identity baseline and
   capture the unrelated bundle-grant map.
3. In System Settings → Privacy & Security → App Management, add and enable
   **Domus Agent Host** once.
4. Use that pane's per-row minus control to remove only the path-based runtime
   rows reported by the audit. Preserve every bundle-ID application and its
   current authorization. If macOS requests authentication, approve this one
   transaction only.
5. Re-run the audit and compare the unrelated bundle-grant map and stable host
   signature to their pre-transaction receipts.

An Automation row whose executable no longer exists may lack an exact removal
surface. That separate observation does not justify ignoring a removable App
Management row. Supported command-line TCC resets accept bundle identifiers,
not these stored executable paths, so a whole-service reset is not an exact
substitute. If the App Management pane itself refuses to remove one exact row,
record only that redacted identity as unsupported historical residue and leave
visible cleanliness red.

Never use `tccutil reset All`, reset the entire App Management service, write to
`TCC.db`, disable updates, delete a real application, or broaden an exact path
cleanup into removal of unrelated grants.

## Live acceptance

Acceptance is simultaneous:

1. App Management contains one enabled Domus host bundle row, zero path rows,
   and the unchanged unrelated bundle-grant map.
2. The active-leak and configured-ingress predicates are green, automatic
   updates remain enabled, and the host designated requirement and CDHash match
   their pre-cutover receipts.
3. A cold start of Claude Desktop and its managed MCP servers creates no new
   path identity in any TCC service.
4. `scripts/tcc-app-management-fixture.py` creates one uniquely named
   disposable application outside the host, updates it through renamed `uvx`,
   Node, Python, and portable/Homebrew Ruby executable paths beneath `ensure`,
   and deletes only that marker-validated fixture through the same host. The
   before/after audit contains no new path identity.
5. When Claude's vendor updater offers an update, `claude --version` advances
   while the normalized TCC inventory remains unchanged.

`non_noop` means the version advances past the cutover baseline — not that
`claude update` exited zero. A no-op "up to date" result is wait evidence,
never completion. Executable owner:
`python3 scripts/tcc-track-c-closeout.py --beat` (formula:
`track_c_pass = non_noop_update AND normalized_inventory_green`).

The owning issue remains open until the real vendor-update predicate in item 5
passes. A passing test fixture, a toggled-off historical row, or an audit that
stops counting disabled rows is not completion evidence.

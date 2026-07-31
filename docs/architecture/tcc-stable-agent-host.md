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
standard streams and terminal state, forwards signals, returns the foreground
leader's exit status, and remains alive while the launched process group or
tracked descendants remain alive. An inherited lifetime pipe also keeps the
host alive across rapid detach/reparent sequences. It is an on-demand CLI; no
LaunchAgent is installed.

## Interfaces

```sh
domus-agent-host run -- <command> [args...]
domus-agent-host status --json
tcc-identity-audit [--json] [--strict]
```

Every committed `com.limen.*` control-plane LaunchAgent, including the
generated heartbeat, enters `DomusAgentHost.app` before Bash, Python, dispatch,
or provider work. An inherited `DOMUS_AGENT_HOST_ACTIVE=1` marker is trusted
only while its native lifetime descriptor remains open. Strict audits always
query the installed host live; fixture-backed status is test-only and rejected
by `--strict`.

`status --json` uses macOS Security APIs and reports the installed bundle path,
bundle identifier, signature validity, designated requirement, CDHash, and
supervision policy. A host replacement is not an ordinary update: the Domus
installer refuses to replace the fixed ad-hoc identity unless a persistent
signing identity is explicitly supplied for a deliberate migration. Routing
configuration may update without replacing the host.

`tcc-identity-audit` opens the user TCC database read-only and emits schema
`limen.tcc_identity_audit.v1`. Relevant clients are classified as:

- `stable_host`: the permanent bundle or installed host executable.
- `legacy_stale`: a managed, versioned client last changed before host deployment.
- `versioned_leak`: a Claude version, Homebrew Cellar, Python framework, uv
  interpreter, or Limen runtime client changed after host deployment.
- `unrelated`: counted but omitted from the client inventory.

Strict mode fails if managed automatic updates are disabled, the host is absent
or invalidly signed, a post-deployment versioned client exists, TCC cannot be
read, or a malformed Claude helper remains registered. The audit never edits
TCC, unregisters an application, pins a tool, or changes an updater.

## One supported System Settings transaction

The initial TCC database inventory itself requires Full Disk Access. Do not run
that read through a rotating interpreter to bootstrap the host; doing so would
create the client this design removes. The supported order is:

1. Install the host and verify `domus-agent-host status --json` without opening
   TCC.
2. Trigger the harmless protected-resource fixture through
   `domus-agent-host run -- ...`, then in System Settings → Privacy & Security
   grant only the requested categories, including Full Disk Access for the
   inventory, to **Domus Agent Host** (`~/Applications/DomusAgentHost.app`).
3. Run `tcc-identity-audit --json --strict` beneath the now-authorized host.
   Proceed only when automatic updates remain enabled, the host is valid, and
   `versioned_leak` is zero.
4. Use that audit's exact `legacy_stale` inventory to remove only dead/versioned
   Claude and Python clients through System Settings. Preserve all `unrelated`
   applications and grants.

Never use `tccutil reset All` and never write to `TCC.db`.

## Live acceptance

Use a harmless sentinel under a protected folder and record the before/after
JSON inventories. Run the same read through foreground Claude, a background
child, the Homebrew Python discovered at runtime, and every installed
Python.org interpreter. Then repeat through differently named fixture
executables. Acceptance is simultaneous:

1. every read succeeds and the second pass shows no permission prompt;
2. the TCC delta contains the stable Domus bundle identity and no
   `versioned_leak`;
3. when Claude's vendor updater offers an update, `claude --version` advances
   while the relevant TCC inventory remains unchanged.

If a detached child is ever attributed directly, keep its process group under
the native supervisor and treat the new row as a failing leak. If a component
cannot preserve responsibility ancestry, protected I/O must be moved behind a
native host-owned broker before that component is admitted. Disabling its
updater or background behavior is not an acceptance path.

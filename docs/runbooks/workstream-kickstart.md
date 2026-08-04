# Workstream Kickstart

Use this when a prompt has several real lanes and the right move is to split the work into a bounded,
resumable surface instead of holding everything in the chat.

For a closeout successor or a new autonomous initiative, use autonomous capsule mode:

```bash
workstream --autonomous --agent auto --conduct --runway 8h --prompt-file /path/to/next-session.md limen next-epoch
```

Autonomous mode refuses a missing prompt. Its thin README index is passed to the selected native
agent as the initial prompt and requires four cohesive Markdown modules (manifest, intent, runtime
decision contract, and closeout) plus a machine-readable `workstream.json`. `--agent auto` derives an available installed CLI from the
canonical Limen census; an explicit canonical lane such as `claude`, `opencode`, `agy`, `gemini`,
or `codex` preserves that native identity. Copilot is an issue-assignment lane: dispatch it by
assigning an existing GitHub issue to `copilot-swe-agent`, not through `workstream --agent`.
`--runway` accepts `Nm`, `Nh`, or `Nd` from 15 minutes
through 30 days and defaults to one day. The clock starts on first kickstart, subsequent sessions
inherit the same deadline, and an expired capsule fails closed instead of silently renewing.
Runtime evidence derives `continue`, `switch`, `wait_relay`, `settled`, or `invalid`.

To create a successor from a tracked receipt, point at its exact committed file:

```bash
workstream --predecessor-receipt /path/to/docs/continuations/prior/workstream.json \
  --prompt-file /path/to/next-session.md danse successor
```

The default `--runway-mode inherit` copies the predecessor's admitted start and absolute deadline
exactly; it refuses a new `--runway`. A deliberately distinct window uses
`--runway-mode renew --runway <duration>` and starts unadmitted. The source receipt must match its
checkout's committed `HEAD` bytes, that checkout must be on the receipt's declared branch, and its
exact HEAD must be the live `origin` branch head. The successor worktree is based on that exact
commit; an explicit `--from` is accepted only when it resolves to the same commit. Both successor
modes use the provider-neutral `workspace-write` authorization contract; an old provider-specific
launch profile is not inherited. The successor records only the predecessor slug, branch, and
receipt SHA-256 digest—never a machine-local path—and never rewrites the predecessor.

Re-rendering an existing successor must repeat the same exact `--predecessor-receipt` and
`--runway-mode` arguments (and the same `--runway` for a renewal). The receipt path is intentionally
not persisted, so omission or substitution fails the capsule identity check instead of guessing a
local source.

`--conduct` registers the direct session with the shared broker as `human_protected` before the
agent starts. The generated launcher passes only session, capsule, lineage, task, lease-generation,
and execution-hash context through environment variables. Broker credentials remain environment
owned for the registration call. When a plain shell has not already exported the broker pair, the
launcher imports only `LIMEN_CONDUCT_URL` and `LIMEN_CONDUCT_TOKEN` from the user-owned mode-`0600`
`~/.limen.env` cache; it does not expose the cache's other values. The launcher never writes or
prints broker values, and removes the conduct credential before the native agent process starts. If
the cache is unsafe or the broker cannot acknowledge registration, the agent does not start.

After the admitted receipt is published, a conductor-only background channel inherits the broker
credential while the provider still receives none. It refreshes the same protected session every
three minutes, retries a failed refresh within the five-minute liveness window, and stops without
signalling the provider when either the exact provider process identity disappears or the capsule
deadline arrives. The channel closes its inherited capsule-lock descriptor and overwrites one
bounded mode-`0600` private status object at
`.limen-workstream/conduct-keepalive.json`; it creates no second session or local campaign store.

Before admission or conduct registration, the launcher completes its bounded remote fetch and Git
status preflights. Either failure leaves the private contract and tracked receipt byte-identical and
starts no provider. After admission, a repository-backed non-Jules launcher commits only the synchronized public receipt
and fast-forward-pushes that exact head to its topic branch before provider `exec`. Unrelated dirty
state, remote branch drift, commit failure, or push failure denies provider launch. Re-entry at an
already published exact head is byte-idempotent. Local-only repositories without an `origin` retain
the legacy owner-native behavior; autonomous campaign repositories require the remote receipt.

The contract also carries the no-modal authorization boundary. Codex starts with
`--ask-for-approval never --sandbox workspace-write`: reversible work inside the packet proceeds
without confirmation, while destructive, credential, paid-spend, public-send, and runtime/host
mutations remain gated. The conductor derives healthy lanes live and routes independently bounded
packets; the capsule never pins a future provider or model.

```bash
/Users/4jp/Workspace/limen/scripts/start-worktree-session.sh --shell --prompt "short objective and constraints" limen my-workstream
```

After `install.sh`, the shortcut is:

```bash
workstream --agent auto --prompt "short objective and constraints" limen my-workstream
```

The command works from Terminal, Kitty, Ghostty, Warp, or any normal shell. It creates or reuses
`<repo>/.worktrees/<slug>` on `work/<slug>`, then writes a private modular capsule at:

```text
<repo>/.worktrees/<slug>/.limen-workstream/README.md
<repo>/.worktrees/<slug>/.limen-workstream/manifest.md
<repo>/.worktrees/<slug>/.limen-workstream/workstream.json
<repo>/.worktrees/<slug>/.limen-workstream/intent.md
<repo>/.worktrees/<slug>/.limen-workstream/runtime.md
<repo>/.worktrees/<slug>/.limen-workstream/closeout.md
```

It also writes:

```text
<repo>/.worktrees/<slug>/.limen-workstream/kickstart.sh
```

Run it from any terminal with:

```bash
bash <repo>/.worktrees/<slug>/.limen-workstream/kickstart.sh
```

For a capsule rendered before private-cache hydration shipped, use the tracked compatibility
wrapper. It validates and imports only the broker pair, then executes the identity-bound capsule
without rewriting it:

```bash
bash scripts/run-workstream-kickstart.sh .limen-workstream/kickstart.sh
```

The command is safe to repeat. If that capsule already has a fresh, live protected session, it
returns success with one plain message and starts no duplicate provider. Continue in the existing
session; never kill or reap it just to relaunch the command.

Autonomous Codex capsules preserve the interactive UI when standard input and output are attached
to a terminal. In a shell runner without a terminal, the same command uses Codex's noninteractive
`exec` transport instead of failing at provider handoff.

The README only defines module order and the launch command. Each module has one reason to change.
Identical reruns preserve `created_at` and an admitted runway, rewrite no bytes, and report
`unchanged`. The
`.limen-workstream/` directory is locally excluded so capsule creation does not dirty the repo.
Omitting `--agent` creates the capsule without launching an agent. The generated kickstart records
the lane selected from the canonical live registry through the same Auto resolver and permits a
login-shell fallback; no provider receives a privileged default.

## Current Leads

- Triptych video canon: keep the source commit pushed, use media atom manifests to classify the 2 GB
  payload, then offload or regenerate/delete generated lanes only after acceptance.
- Domus: continue from the clean `work/universal-entry-20260629` branch; do not blindly push or reset
  the polluted original branch without an explicit retire plan.
- Maddie texts: keep raw transcript outputs private; use the weekend assessment to set a bounded
  payment/scope boundary before taking more implementation work.
- Limen lifecycle: keep worktree pressure, remote receipts, and cleanup at session boundaries rather
  than relying on memory or manual reminders.

## Active Packets Created 2026-06-29

Triptych media offload:

```bash
bash /Users/4jp/Workspace/4444J99/portvs/.worktrees/triptych-media-offload-20260629/.limen-workstream/kickstart.sh
```

Domus quarantine retire:

```bash
bash /Users/4jp/Workspace/domus-genoma/.worktrees/domus-quarantine-retire-20260629/.limen-workstream/kickstart.sh
```

Maddie boundary:

```bash
bash /Users/4jp/Workspace/4444J99/relationship-pipeline/.worktrees/maddie-boundary-20260629/.limen-workstream/kickstart.sh
```

Current implementation lane:

```bash
bash /Users/4jp/Workspace/limen/.worktrees/workstream-kickstart-20260629/.limen-workstream/kickstart.sh
```

## Pattern

1. Create a worktree per logical lane.
2. Put intent in `intent.md`; keep README as the ordered module index.
3. Do the source work in the worktree.
4. Verify.
5. Commit and push.
6. For the first push from a new branch, use `git push -u origin HEAD`.
7. Report local/remote state and classify anything large or generated.

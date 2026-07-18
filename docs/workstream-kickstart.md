# Workstream Kickstart

Use this when a prompt has several real lanes and the right move is to split the work into a bounded,
resumable surface instead of holding everything in the chat.

For a closeout successor or a new autonomous initiative, use autonomous capsule mode:

```bash
workstream --autonomous --runway 8h --prompt-file /path/to/next-session.md limen next-epoch
```

Autonomous mode refuses a missing prompt. Its thin README index is passed to Codex as the initial
prompt and requires four cohesive Markdown modules (manifest, intent, runtime decision contract, and
closeout) plus a machine-readable `workstream.json`. `--runway` accepts `Nm`, `Nh`, or `Nd` from 15
minutes through 30 days and defaults to one day. The clock starts on first kickstart, subsequent
sessions inherit the same deadline, and an expired capsule fails closed instead of silently
renewing. Runtime evidence derives `continue`, `switch`, `wait_relay`, `settled`, or `invalid`.

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
workstream --prompt "short objective and constraints" limen my-workstream
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

The README only defines module order and the launch command. Each module has one reason to change.
Identical reruns preserve `created_at` and an admitted runway, rewrite no bytes, and report
`unchanged`. The
`.limen-workstream/` directory is locally excluded so capsule creation does not dirty the repo.

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
